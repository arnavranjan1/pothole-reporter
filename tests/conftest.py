# conftest.py — shared pytest fixtures, auto-discovered by pytest (no import needed in test files).
# pytest finds this file by its exact name, the same way it finds test_*.py files.

import os                                                  # to set DATABASE_URL before app is imported

# THE SEAM. This MUST run before `from app import ...` below.
# Why: config.py reads DATABASE_URL out of the environment, and the SQLAlchemy engine binds to
# that URL once, at import time, inside app.py. Set it here first → the engine is born pointing
# at the TEST database, never your dev one. (load_dotenv in app.py leaves already-set vars alone,
# so this wins.) This line is why we need ZERO changes to app.py.
os.environ["DATABASE_URL"] = "postgresql://localhost:5432/pothole_test_db"

import pytest                                              # the framework — gives @pytest.fixture
from app import app as flask_app, db, User, Report         # import AFTER the env var is set, so the engine binds to the test DB
                                                           # `app as flask_app` → avoid shadowing; pull db + the two models we'll need to seed/assert


@pytest.fixture
def app():                                                 # the app fixture — every other fixture and test builds on this
    flask_app.config["TESTING"] = True                     # Flask test mode: real exceptions propagate instead of being swallowed into a 500 page
    flask_app.config["WTF_CSRF_ENABLED"] = False           # turn CSRF OFF for tests — no browser to issue tokens, so posts would 400 otherwise. safe: we're testing logic, not the token
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]  # belt-and-suspenders: assert the test DB even if something re-read config

    with flask_app.app_context():                          # push an app context — db.create_all needs to know WHICH app's engine to talk to
        db.create_all()                                    # build every table fresh in the test DB (setup)
        yield flask_app                                    # hand the configured app to whoever asked. pause here while the test runs
        db.session.remove()                                # close the session cleanly
        db.drop_all()                                      # tear every table back down (teardown) → next test starts from empty. runs even if the test failed


@pytest.fixture
def client(app):                                           # the test client — depends on `app` (pytest resolves the chain). lets us fire client.get/post
    return app.test_client()                               # in-process HTTP simulator — same routing→view→response path a browser hits, no server, no port


@pytest.fixture
def make_user(app):                                        # a FACTORY fixture: returns a function so a test can mint users on demand with chosen role
    def _make(username, password="pw12345", role="citizen"):  # defaults keep call sites short; override role for an admin
        with app.app_context():                            # need a context to touch the DB
            user = User(username=username, role=role)      # build the row
            user.set_password(password)                    # hash + store (never the raw password)
            db.session.add(user)
            db.session.commit()                            # write it so login can find it
            return user.id                                 # return the PK, not the object — the object would be detached once the context closes
    return _make                                           # the test receives THIS function and calls it as many times as it likes