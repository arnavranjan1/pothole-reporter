import os                                                  # to read environment variables (os.environ) — the seam between code and secrets

# the valid hazard types — ONE authoritative home, now a value→label dict (Option B).
# keys = the stored/filtered values (what lands in Report.hazard_type and what /admin filters on).
# values = the human labels for the dropdown. ONE structure → the form's choices and the filter's allow-list literally cannot drift.
# imported by forms.py (builds ReportForm choices from .items()) AND app.py (the /admin filter tests membership — `x in dict` checks keys).
ALLOWED_HAZARDS = {
    "pothole": "Pothole",
    "streetlight": "Broken streetlight",
    "garbage": "Garbage",
    "flooding": "Flooding",
}

# the valid lifecycle states — same single-source-of-truth treatment. guards the /admin status filter AND update_status.
# stays a set: no labels needed (the values ARE the display text — "Reported", "In Progress", "Fixed").
ALLOWED_STATUSES = {"Reported", "In Progress", "Fixed"}


class Config:                                              # Flask reads this via app.config.from_object(Config). only UPPERCASE attributes get copied into app.config.
    # signs the session cookie AND CSRF tokens. read from the environment; the second arg is a DEV-ONLY fallback so the app still boots without a .env.
    # in production this MUST be overridden with a real secret env var — the fallback is published in the repo and is not safe for prod.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # which Postgres db to talk to. env-driven with a local fallback. SQLAlchemy reads this when db.init_app(app) binds the engine, so it must exist by then.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://localhost:5432/pothole_db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False                 # silences an unused memory-leaking feature
    UPLOAD_FOLDER = "static/uploads"                       # where photos land. under static/ so Flask serves them for free
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024                   # 5 MB ceiling on the whole request body. server-side → client can't bypass it