from flask import Flask, render_template, request, redirect, url_for, flash, abort   # + abort → emit a clean HTTP error (404) instead of rendering a blank page
from flask_sqlalchemy import SQLAlchemy                    # the ORM extension — gives db.Model, db.session etc.
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # base class, type-hints, column definer, + relationship for FK convenience
from sqlalchemy import ForeignKey, or_                     # ForeignKey: FK constraint. or_: combine conditions with SQL OR (for searching ACROSS two columns)
from datetime import datetime, timezone                    # for the created_at timestamp

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user  # full Flask-Login toolkit
from flask_migrate import Migrate                          # wraps Alembic → the `flask db ...` commands
from flask_wtf import CSRFProtect                          # CSRF defense — issues + verifies the per-form token signed by secret_key
from werkzeug.security import generate_password_hash, check_password_hash      # one-way password hashing (ships with Flask)

from dotenv import load_dotenv                             # reads .env into os.environ. MUST run before Config is imported — Config's class body reads os.environ at import time
load_dotenv()                                              # populate the environment NOW, so the os.environ.get(...) calls inside Config see the real values
from config import Config, ALLOWED_HAZARDS, ALLOWED_STATUSES  # the single home for settings + the two allow-lists. import AFTER load_dotenv so env vars are already loaded

from forms import LoginForm, RegistrationForm, ReportForm  # the declarative form classes (forms.py)

import os                                                  # filesystem paths — building the save location, ensuring the folder exists
from uuid import uuid4                                     # random token to prefix filenames → kills collisions
from werkzeug.utils import secure_filename                 # sanitizes the client's filename → kills path traversal


class Base(DeclarativeBase):                               # the declarative base every model inherits from — holds the table catalogue
    pass


db = SQLAlchemy(model_class=Base)                          # the ORM gateway. not bound to an app yet (create-then-init pattern)
login_manager = LoginManager()                             # central coordinator for login state. bound to app below
migrate = Migrate()                                        # the migration engine. bound to app below
csrf = CSRFProtect()                                       # CSRF guard. create-then-init like the others — bound to app below

app = Flask(__name__)                                      # the application object
app.config.from_object(Config)                             # load ALL settings in one shot — copies every UPPERCASE attr off Config into app.config (SECRET_KEY, DB URI, UPLOAD_FOLDER, etc). must run before db.init_app reads the URI

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)    # create the uploads folder on startup if missing. exist_ok=True → no crash if it already exists. reads the path Config just loaded

db.init_app(app)                                           # bind db to this app — reads SQLALCHEMY_DATABASE_URI NOW, so from_object above had to run first
login_manager.init_app(app)                                # bind the login manager to this app
migrate.init_app(app, db)                                  # bind migrate — needs both app and db (it inspects models)
csrf.init_app(app)                                         # bind CSRF — now every POST/PUT/PATCH/DELETE must carry a valid token; GET stays exempt

login_manager.login_view = "login"                         # when @login_required blocks someone, redirect to the route named "login"


@login_manager.user_loader                                 # registers THE callback Flask-Login calls on every request
def load_user(user_id):                                    # receives the user id (string) from the signed cookie
    return db.session.get(User, int(user_id))              # rehydrate the full User by primary key. None if not found → treated as logged-out


class User(db.Model, UserMixin):                           # db.Model = a table. UserMixin = inherits the 4 methods Flask-Login expects, for free
    __tablename__ = "users"                                # explicit plural table name

    id: Mapped[int] = mapped_column(primary_key=True)                       # PK, auto-incremented by Postgres
    username: Mapped[str] = mapped_column(db.String(80), unique=True)       # unique → no two users share a name. NOT NULL by default
    password_hash: Mapped[str] = mapped_column(db.String(255))              # the hash, never the password. 255 fits the format + salt
    role: Mapped[str] = mapped_column(db.String(20), default="citizen")     # "citizen" or "admin". default → signups are citizens automatically

    reports: Mapped[list["Report"]] = relationship(back_populates="author") # one-to-many: user.reports = all reports this user filed

    def set_password(self, raw_password):                  # hash a plaintext password and store it
        self.password_hash = generate_password_hash(raw_password)           # salting + slowness handled inside

    def check_password(self, raw_password):                # verify a login attempt
        return check_password_hash(self.password_hash, raw_password)        # re-hashes the attempt, compares to stored hash. True/False

    def __repr__(self):
        return f"<User {self.id} {self.username} ({self.role})>"


class Report(db.Model):                                    # the reports table
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)                       # PK
    hazard_type: Mapped[str] = mapped_column(db.String(50))                 # matches form's hazard_type field. NOT NULL
    location: Mapped[str] = mapped_column(db.String(255))                   # matches form's location field. NOT NULL
    description: Mapped[str | None] = mapped_column(db.Text, nullable=True)  # optional free-form text
    status: Mapped[str] = mapped_column(db.String(20), default="Reported")  # lifecycle field, defaults to "Reported"
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),                        # timezone-aware timestamp
        default=lambda: datetime.now(timezone.utc),        # lambda → fresh time at EACH insert, not frozen at startup
    )
    image_filename: Mapped[str | None] = mapped_column(    # the SAVED photo's filename (not the bytes). nullable → photo is optional
        db.String(255), nullable=True
    )

    latitude: Mapped[float | None] = mapped_column(db.Float, nullable=True)   # decimal coord. Float = Postgres double precision
    longitude: Mapped[float | None] = mapped_column(db.Float, nullable=True)  # nullable → old rows (no coords) survive the migration

    user_id: Mapped[int | None] = mapped_column(           # which user filed this. nullable because old reports predate this column
        ForeignKey("users.id"), nullable=True              # FK → value must match a users.id. DB enforces real-owner integrity
    )
    author: Mapped["User | None"] = relationship(back_populates="reports")  # many-to-one: report.author = the User object (or None)

    def filer_visible_to(self, viewer):                    # WHO filed this is private — only the owner or an admin may see it. lives on the model so every template asks the same question
        if not viewer.is_authenticated:                    # logged-out visitors never see the filer
            return False
        if viewer.role == "admin":                         # admins see every filer
            return True
        return self.user_id == viewer.id                   # otherwise: only if THIS report is the viewer's own. self.user_id is None for old reports → False for non-admins

    def __repr__(self):
        return f"<Report {self.id} {self.hazard_type} @ {self.location}>"


@app.route("/")                                            # homepage
def home():
    return render_template("index.html")


@app.route("/report", methods=["GET", "POST"])
@login_required                                            # must be logged in to file a report
def report():
    form = ReportForm()                                    # bind to request data automatically (reads request.form + request.files)
    if form.validate_on_submit():                          # True only when: POST + CSRF valid + all validators pass
        lat = lng = None                                   # default: no coordinate
        if form.latitude.data and form.longitude.data:     # both present → user dropped a pin (HiddenField gives strings)
            try:
                lat = float(form.latitude.data)            # strings → real floats. still a server-side tamper check
                lng = float(form.longitude.data)
            except ValueError:                             # someone forged the hidden input — don't trust the client
                flash("Invalid coordinates.", "error")     # CATEGORY: bad input → red
                return redirect(url_for("report"))

        file = form.photo.data                             # FileStorage object (or None) — WTForms already validated the extension
        image_filename = None                              # default: no photo
        if file and file.filename:                         # a real upload happened
            safe_name = secure_filename(file.filename)     # strip slashes/.. → defuses path traversal
            unique_name = f"{uuid4().hex}_{safe_name}"     # prepend a random token → two uploads can't collide
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))  # stream the bytes to disk
            image_filename = unique_name                   # store ONLY the filename in the DB

        new_report = Report(
            hazard_type=form.hazard_type.data,             # .data = the validated, filtered value off the field
            location=form.location.data,
            description=form.description.data,
            image_filename=image_filename,                 # None if no photo, else the saved unique filename
            latitude=lat,                                  # None if no pin dropped, else the clicked latitude
            longitude=lng,
            author=current_user,                           # stamp the logged-in user. relationship fills user_id automatically
        )
        db.session.add(new_report)                         # stage (like git add)
        db.session.commit()                                # write to Postgres (like git commit)

        flash("Thanks! Your report has been submitted.", "success")  # CATEGORY: success → green
        return redirect(url_for("home"))                   # PRG on SUCCESS

    return render_template("report.html", form=form)       # GET or failed POST → re-render WITH the form (errors + values intact)


@app.route("/reports")                                     # public list of all reports
def reports():
    page = request.args.get("page", 1, type=int)                  # which page to show. type=int coerces "3"→3 AND falls back to 1 on junk like ?page=abc — same idiom as /admin
    stmt = db.select(Report).order_by(Report.created_at.desc())   # all reports, newest first
    pagination = db.paginate(                                      # the swap: instead of .execute(stmt).scalars().all() (every row), slice in the DB
        stmt,                                                     # the statement — no filters on this route, just the order_by
        page=page,                                                # which slice
        per_page=10,                                              # 10 rows per page → LIMIT 10 OFFSET (page-1)*10, plus a COUNT(*) for total page math
        error_out=False,                                          # ?page=999 → empty page object, NOT a 404. graceful instead of crashing
    )
    return render_template(
        "reports.html",
        reports=pagination.items,                                 # ONLY this page's slice (≤10 Report objects) — the .items list off the Pagination object
        pagination=pagination,                                    # the whole Pagination object → the partial reads .has_prev / .pages / .iter_pages() etc
    )


@app.route("/my-reports")                                  # a citizen's own reports — private, login-gated
@login_required                                            # precondition: guarantees a real current_user.id exists before the query runs
def my_reports():
    page = request.args.get("page", 1, type=int)           # which page to show. same coercion + fallback as /reports and /admin
    stmt = db.select(Report).where(                        # the ownership filter — the whole point of this session
        Report.user_id == current_user.id                  # == builds a SQL expression, not a Python bool. "rows whose owner is me"
    ).order_by(Report.created_at.desc())                   # newest first, matching /reports and /admin
    pagination = db.paginate(                              # same swap as /reports — slice in the DB instead of fetching every row
        stmt,                                              # the ownership-filtered statement
        page=page,                                         # which slice
        per_page=10,                                       # 10 rows per page — same per_page as /reports and /admin
        error_out=False,                                   # ?page=999 → empty page object, NOT a 404
    )
    return render_template(
        "my_reports.html",
        reports=pagination.items,                          # ONLY this page's slice (≤10 Report objects)
        pagination=pagination,                             # the whole Pagination object → the partial reads .has_prev / .pages / etc
    )


@app.route("/report/<int:report_id>")                      # GET — view ONE report in full. <int:..> validates+coerces the id, same converter as update_status
def report_detail(report_id):                              # report_id arrives as a real int. no POST, no mutation → no CSRF token needed on the links pointing here
    report = db.session.get(Report, report_id)             # load the row by PK. same getter as load_user / update_status. None if no such id
    if report is None:                                     # valid int but no such report → the user navigated to a URL with nothing behind it
        abort(404)                                         # honest HTTP answer: "nothing exists here". routes through the @app.errorhandler(404) below
    return render_template("report_detail.html", report=report)  # one object (not a list). the template asks report.filer_visible_to(current_user) itself


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():                          # includes validate_username → "taken" check lives on the form now
        user = User(username=form.username.data)           # role defaults to "citizen"
        user.set_password(form.password.data)              # hash + store, never the raw password
        db.session.add(user)
        db.session.commit()
        flash("Account created — please log in.", "success")  # CATEGORY: success → green
        return redirect(url_for("login"))
    return render_template("register.html", form=form)     # re-render on failure: "username taken" / "too short" shown inline


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():                          # only checks both fields present + CSRF valid
        user = db.session.scalar(                          # look up user by name
            db.select(User).where(User.username == form.username.data)
        )
        if user is None or not user.check_password(form.password.data):   # AUTH check — stays on route, deliberately vague
            flash("Invalid username or password.", "error")   # CATEGORY: failed auth → red
            return redirect(url_for("login"))

        login_user(user)                                   # writes user id into the signed session cookie
        flash(f"Welcome back, {user.username}!", "success")  # CATEGORY: success → green
        return redirect(url_for("home"))
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required                                            # can't log out if not logged in
def logout():
    logout_user()                                          # clears the user id from the cookie
    flash("You've been logged out.", "info")               # CATEGORY: neutral notice → blue/grey. not success, not failure
    return redirect(url_for("home"))
@app.route("/admin")
@login_required                                            # must be logged in...
def admin():
    if current_user.role != "admin":                       # ...AND an admin. citizens bounced
        flash("Admins only.", "error")                     # CATEGORY: access denied → red
        return redirect(url_for("home"))

    status_filter = request.args.get("status", "").strip()  # read the status filter from the QUERY STRING (?status=...), NOT the form body. "" if absent. same .get(key, default) as request.form
    hazard_filter = request.args.get("hazard_type", "").strip()  # read the hazard filter from the query string too (?hazard_type=...). second independent optional filter
    search_query = request.args.get("q", "").strip()        # the SEARCH term off the query string (?q=...). "" if absent. third independent narrowing
    page = request.args.get("page", 1, type=int)            # which page to show. type=int coerces "3"→3 AND falls back to 1 on junk like ?page=abc — same allow-list spirit as the filters

    stmt = db.select(Report).order_by(Report.created_at.desc())  # base query — every report, newest first. the unchanged default when no valid filter is present

    if status_filter in ALLOWED_STATUSES:                  # allow-list wall — the SAME set that guards update_status. junk like ?status=banana fails here. now imported from config
        stmt = stmt.where(Report.status == status_filter)  # .where() returns a NEW stmt with the WHERE bolted on (immutable, like String.trim()) → reassign, don't mutate
    else:
        status_filter = ""                                 # normalise junk/empty → "" so the template treats "no valid filter" as "All selected"

    if hazard_filter in ALLOWED_HAZARDS:                   # second independent if — NOT elif. both filters can apply at once. now imported from config — same list the form uses
        stmt = stmt.where(Report.hazard_type == hazard_filter)  # chaining a second .where() → SQL ANDs the conditions: WHERE status=... AND hazard_type=...
    else:
        hazard_filter = ""                                 # same normalise → "" means "All" for the hazard bar

    if search_query:                                       # only narrow if a term was actually typed — empty search = no WHERE added (show everything)
        pattern = f"%{search_query}%"                      # % = SQL wildcard either side → substring match anywhere in the column, not exact equality
        stmt = stmt.where(or_(                             # one .where() holding an OR → match in EITHER column. (chained .where()s would AND, which we DON'T want here)
            Report.description.ilike(pattern),             # ILIKE = case-insensitive LIKE. NULL descriptions simply don't match — no error, no crash
            Report.location.ilike(pattern),                # same term, second column. a hit in either is enough
        ))                                                 # the whole or_(...) becomes one bracketed condition, AND-ed onto any status/hazard WHERE already present

    pagination = db.paginate(                              # the swap: instead of .execute(stmt).scalars().all() (every row), slice in the DB
        stmt,                                              # the fully-composed statement — all filters already baked in
        page=page,                                         # which slice
        per_page=10,                                       # 10 rows per page → emits LIMIT 10 OFFSET (page-1)*10, plus a COUNT(*) for total page math
        error_out=False,                                   # ?page=999 → empty page object, NOT a 404. graceful instead of crashing
    )

    return render_template(
        "admin.html",
        reports=pagination.items,                          # ONLY this page's slice (≤10 Report objects) — the .items list off the Pagination object
        pagination=pagination,                             # the whole Pagination object → the partial reads .has_prev / .pages / .iter_pages() etc
        active_status=status_filter,                       # which status filter is live (or "") → status bar highlights it
        active_hazard=hazard_filter,                       # which hazard filter is live (or "") → hazard bar highlights it
        active_q=search_query,                             # echo the search term back → fills the box AND rides along in every filter link
    )

@app.route("/admin/report/<int:report_id>/status", methods=["POST"])  # state-changing → POST only. <int:..> validates+coerces the id at the routing layer
@login_required                                            # must be logged in (gives us a real current_user)
def update_status(report_id):                              # report_id arrives as a real int, courtesy of the <int:> converter
    if current_user.role != "admin":                       # THE function-level auth check — the route defends itself, not relying on the hidden button
        flash("Admins only.", "error")                     # CATEGORY: a forged citizen POST dies right here → red
        return redirect(url_for("home"))

    new_status = request.form.get("status", "").strip()    # the submitted target state, cleaned. arrives in request.form from the clicked button's value
    if new_status not in ALLOWED_STATUSES:                 # allow-list wall — rejects status=banana and any other forged value. now imported from config
        flash("Invalid status.", "error")                  # CATEGORY: forged/bad value → red
        return redirect(url_for("admin"))

    report = db.session.get(Report, report_id)             # load the existing row by PK. same getter as load_user. None if no such id
    if report is None:                                     # the id was a valid int but no such report exists (e.g. deleted) → don't crash
        flash("Report not found.", "error")                # CATEGORY: target gone → red
        return redirect(url_for("admin"))

    report.status = new_status                             # mutate the managed object — the ONE line that is the actual UPDATE. dirty-tracking notes it
    db.session.commit()                                    # flush → ORM emits UPDATE reports SET status=... WHERE id=report_id

    flash(f"Report #{report.id} marked '{new_status}'.", "success")  # CATEGORY: state change succeeded → green
    return redirect(url_for("admin"))                       # PRG: redirect after POST so a refresh doesn't re-submit


@app.route("/map")                                         # the interactive map page — public, no login needed (like /reports)
def map_view():                                            # named map_view, NOT map — `map` is a Python builtin; shadowing it is the same class of bug as your old reports/reports_store collision
    stmt = db.select(Report).where(                        # only reports that HAVE coords — the rest can't be placed on a map
        Report.latitude.is_not(None),                      # .is_not(None) = SQL `IS NOT NULL`. filter in the DB, not in Python
        Report.longitude.is_not(None),
    )
    reports_with_coords = db.session.execute(stmt).scalars().all()

    markers = [                                            # flatten ORM objects → plain dicts, ready for tojson in the template
        {
            "lat": r.latitude,
            "lng": r.longitude,
            "hazard_type": r.hazard_type,
            "status": r.status,
        }
        for r in reports_with_coords
    ]
    return render_template("map.html", markers=markers)    # pass the list; template serializes it with the tojson filter


# ===== error handlers — app-wide, registered once. catch a whole CLASS of error across every route =====

@app.errorhandler(404)                                     # fires on any 404 anywhere: a bad URL, or your explicit abort(404) in report_detail
def not_found(error):                                      # Flask passes the error object in (unused here, but it's part of the signature)
    return render_template("404.html"), 404                # the TUPLE: (body, status_code). the , 404 keeps the HTTP status honest — page says "not found" AND the status agrees

@app.errorhandler(500)                                     # fires when an unhandled exception kills a request mid-flight
def server_error(error):                                   # the crash happened somewhere in a view; we clean up after it
    db.session.rollback()                                  # CRITICAL: a mid-request crash may have left a half-done transaction. discard it so the NEXT request gets a clean session
    return render_template("500.html"), 500                # same tuple discipline: honest 500 status alongside the friendly page


if __name__ == "__main__":
    app.run(debug=True)                                    # dev server: auto-reload + detailed error pages