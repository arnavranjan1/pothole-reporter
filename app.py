from flask import Flask, render_template, request, redirect, url_for, flash   # core Flask: app, templating, request data, redirects, URL building, flash messages
from flask_sqlalchemy import SQLAlchemy                    # the ORM extension — gives db.Model, db.session etc.
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # base class, type-hints, column definer, + relationship for FK convenience
from sqlalchemy import ForeignKey                          # column-level constraint: value must match a PK in another table
from datetime import datetime, timezone                    # for the created_at timestamp

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user  # full Flask-Login toolkit
from flask_migrate import Migrate                          # wraps Alembic → the `flask db ...` commands
from werkzeug.security import generate_password_hash, check_password_hash      # one-way password hashing (ships with Flask)

import os                                                  # filesystem paths — building the save location, ensuring the folder exists
from uuid import uuid4                                     # random token to prefix filenames → kills collisions
from werkzeug.utils import secure_filename                 # sanitizes the client's filename → kills path traversal


class Base(DeclarativeBase):                               # the declarative base every model inherits from — holds the table catalogue
    pass


db = SQLAlchemy(model_class=Base)                          # the ORM gateway. not bound to an app yet (create-then-init pattern)
login_manager = LoginManager()                             # central coordinator for login state. bound to app below
migrate = Migrate()                                        # the migration engine. bound to app below

app = Flask(__name__)                                      # the application object
app.secret_key = "dev-secret-change-me"                    # signs the session cookie — now load-bearing for auth security
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://localhost:5432/pothole_db"  # which Postgres db to talk to
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False       # silences an unused memory-leaking feature
app.config["UPLOAD_FOLDER"] = "static/uploads"             # where photos land. under static/ so Flask serves them for free
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024         # 5 MB ceiling on the whole request body. server-side → client can't bypass it

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif"}         # allow-list of accepted image types. a set → fast membership check
ALLOWED_STATUSES = {"Reported", "In Progress", "Fixed"}    # allow-list of valid lifecycle states. a set → fast membership check. same defense as ALLOWED_EXTENSIONS

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)    # create the uploads folder on startup if missing. exist_ok=True → no crash if it already exists

db.init_app(app)                                           # bind db to this app
login_manager.init_app(app)                                # bind the login manager to this app
migrate.init_app(app, db)                                  # bind migrate — needs both app and db (it inspects models)

login_manager.login_view = "login"                         # when @login_required blocks someone, redirect to the route named "login"


def allowed_file(filename):                                # is this a file type we accept?
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS  # split off extension, lowercase, check allow-list


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

    def __repr__(self):
        return f"<Report {self.id} {self.hazard_type} @ {self.location}>"


@app.route("/")                                            # homepage
def home():
    return render_template("index.html")


@app.route("/report", methods=["GET", "POST"])
@login_required                                            # must be logged in to file a report
def report():
    if request.method == "POST":
        hazard_type = request.form.get("hazard_type", "").strip()           # pull + clean form fields
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        latitude = request.form.get("latitude", "").strip()    # arrives as a STRING from the hidden input (or "" if user never clicked)
        longitude = request.form.get("longitude", "").strip()

        if not hazard_type or not location:                # required-field validation
            flash("Please choose a hazard type and enter a location.")
            return redirect(url_for("report"))

        lat = lng = None                                   # default: no coordinate
        if latitude and longitude:                         # both present → user dropped a pin
            try:
                lat = float(latitude)                      # form values are strings; coords need to be real floats
                lng = float(longitude)
            except ValueError:                             # someone tampered with the hidden input — don't trust the client
                flash("Invalid coordinates.")
                return redirect(url_for("report"))

        file = request.files.get("photo")                  # files arrive in request.files, NOT request.form. key = the input's name attribute
        image_filename = None                              # default: no photo. stays None if nothing was uploaded

        if file and file.filename:                         # a file object AND a non-empty filename → user actually chose something
            if not allowed_file(file.filename):            # reject non-images BEFORE touching disk. server-side, don't trust the client
                flash("Photo must be a JPG, PNG, or GIF.")
                return redirect(url_for("report"))

            safe_name = secure_filename(file.filename)     # strip slashes/.. → defuses path traversal
            unique_name = f"{uuid4().hex}_{safe_name}"     # prepend a random token → two uploads can't collide
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))  # stream the bytes to disk (≈ Java's transferTo)
            image_filename = unique_name                   # store ONLY the filename in the DB

        new_report = Report(
            hazard_type=hazard_type,
            location=location,
            description=description,
            image_filename=image_filename,                 # None if no photo, else the saved unique filename
            latitude=lat,                                  # None if no pin dropped, else the clicked latitude
            longitude=lng,
            author=current_user,                           # stamp the logged-in user. relationship fills user_id automatically
        )
        db.session.add(new_report)                         # stage (like git add)
        db.session.commit()                                # write to Postgres (like git commit)

        flash("Thanks! Your report has been submitted.")
        return redirect(url_for("home"))

    return render_template("report.html")


@app.route("/reports")                                     # public list of all reports
def reports():
    stmt = db.select(Report).order_by(Report.created_at.desc())   # all reports, newest first
    all_reports = db.session.execute(stmt).scalars().all()        # .scalars() → bare Report objects, not 1-tuples
    return render_template("reports.html", reports=all_reports)

@app.route("/my-reports")                                  # a citizen's own reports — private, login-gated
@login_required                                            # precondition: guarantees a real current_user.id exists before the query runs
def my_reports():
    stmt = db.select(Report).where(                        # the ownership filter — the whole point of this session
        Report.user_id == current_user.id                  # == builds a SQL expression, not a Python bool. "rows whose owner is me"
    ).order_by(Report.created_at.desc())                   # newest first, matching /reports and /admin
    my = db.session.execute(stmt).scalars().all()          # .scalars() → bare Report objects, not 1-tuples. same idiom as your other list routes
    return render_template("my_reports.html", reports=my)  # pass as `reports` so the template loop reads identically to reports.html

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")        # don't strip passwords — spaces may be intentional

        if not username or not password:                   # presence check
            flash("Username and password are required.")
            return redirect(url_for("register"))

        existing = db.session.scalar(                      # is this username taken?
            db.select(User).where(User.username == username)
        )
        if existing:
            flash("That username is already taken.")
            return redirect(url_for("register"))

        user = User(username=username)                     # role defaults to "citizen"
        user.set_password(password)                        # hash + store, never the raw password
        db.session.add(user)
        db.session.commit()

        flash("Account created — please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db.session.scalar(                          # look up user by name
            db.select(User).where(User.username == username)
        )

        if user is None or not user.check_password(password):    # combined check — deliberately vague for security
            flash("Invalid username or password.")
            return redirect(url_for("login"))

        login_user(user)                                   # writes user id into the signed session cookie
        flash(f"Welcome back, {user.username}!")
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
@login_required                                            # can't log out if not logged in
def logout():
    logout_user()                                          # clears the user id from the cookie
    flash("You've been logged out.")
    return redirect(url_for("home"))


@app.route("/admin")
@login_required                                            # must be logged in...
def admin():
    if current_user.role != "admin":                       # ...AND an admin. citizens bounced
        flash("Admins only.")
        return redirect(url_for("home"))

    stmt = db.select(Report).order_by(Report.created_at.desc())
    all_reports = db.session.execute(stmt).scalars().all()
    return render_template("admin.html", reports=all_reports)


@app.route("/admin/report/<int:report_id>/status", methods=["POST"])  # state-changing → POST only. <int:..> validates+coerces the id at the routing layer
@login_required                                            # must be logged in (gives us a real current_user)
def update_status(report_id):                              # report_id arrives as a real int, courtesy of the <int:> converter
    if current_user.role != "admin":                       # THE function-level auth check — the route defends itself, not relying on the hidden button
        flash("Admins only.")                              # a forged citizen POST dies right here
        return redirect(url_for("home"))

    new_status = request.form.get("status", "").strip()    # the submitted target state, cleaned. arrives in request.form from the clicked button's value
    if new_status not in ALLOWED_STATUSES:                 # allow-list wall — rejects status=banana and any other forged value
        flash("Invalid status.")
        return redirect(url_for("admin"))

    report = db.session.get(Report, report_id)             # load the existing row by PK. same getter as load_user. None if no such id
    if report is None:                                     # the id was a valid int but no such report exists (e.g. deleted) → don't crash
        flash("Report not found.")
        return redirect(url_for("admin"))

    report.status = new_status                             # mutate the managed object — the ONE line that is the actual UPDATE. dirty-tracking notes it
    db.session.commit()                                    # flush → ORM emits UPDATE reports SET status=... WHERE id=report_id

    flash(f"Report #{report.id} marked '{new_status}'.")   # confirmation to the admin
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


if __name__ == "__main__":
    app.run(debug=True)                                    # dev server: auto-reload + detailed error pages