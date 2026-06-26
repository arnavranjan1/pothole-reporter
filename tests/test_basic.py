# test_basic.py — first test suite. pytest discovers this file by its `test_` name,
# and runs each `test_*` function inside it. fixtures (client, make_user) are injected by name.

from app import db, Report                                 # Report for the model-logic test; db to seed inside a context
from flask import url_for                                  # not strictly needed, but handy if you extend


def test_home_loads(client):                               # SMOKE TEST: does the homepage even answer?
    response = client.get("/")                              # simulate GET / — same path a browser hits
    assert response.status_code == 200                     # 200 = OK. if this fails, something's broken at the most basic level


def test_reports_page_loads(client):                       # the public list page should load for anyone, logged in or not
    response = client.get("/reports")
    assert response.status_code == 200


def test_my_reports_requires_login(client):                # AUTH GUARD: a logged-out visitor must NOT see /my-reports
    response = client.get("/my-reports")                   # no login performed → we're anonymous
    assert response.status_code == 302                     # 302 = redirect. @login_required bounces us toward /login instead of serving the page
    assert "/login" in response.headers["Location"]        # and confirm WHERE it bounced us — the Location header points at the login route


def test_filer_visible_to(app):                            # MODEL LOGIC: test the privacy rule directly, no HTTP needed
    with app.app_context():                                # model methods touch instance attrs → safest inside a context
        # three players: the owner, an admin, a stranger. we fake them as lightweight stand-ins.
        owner = User(id=1, username="owner", role="citizen")
        admin = User(id=2, username="admin", role="admin")
        stranger = User(id=3, username="stranger", role="citizen")

        report = Report(hazard_type="pothole", location="Main St", user_id=1)  # filed by owner (user_id=1)

        assert report.filer_visible_to(owner) is True      # owner sees their own filer → True
        assert report.filer_visible_to(admin) is True      # admin sees every filer → True
        assert report.filer_visible_to(stranger) is False  # a different citizen → False


from app import User                                       # imported down here only to keep the model-test readable; move to the top with the others if you prefer