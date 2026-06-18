from flask import Flask, render_template, request, redirect, url_for, flash   # core Flask: app, templating, request data, redirects, URL building, flash messages
from flask_sqlalchemy import SQLAlchemy                    # the ORM extension — gives db.Model, db.session etc.
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # base class, type-hints, column definer, + relationship for FK convenience
from sqlalchemy import ForeignKey                          # column-level constraint: value must match a PK in another table
from datetime import datetime, timezone                    # for the created_at timestamp

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user  # full Flask-Login toolkit
from flask_migrate import Migrate                          # wraps Alembic → the `flask db ...` commands
from werkzeug.security import generate_password_hash, check_password_hash      # one-way password hashing (ships with Flask)


class Base(DeclarativeBase):                               # the declarative base every model inherits from — holds the table catalogue
    pass


db = SQLAlchemy(model_class=Base)                          # the ORM gateway. not bound to an app yet (create-then-init pattern)
login_manager = LoginManager()                             # central coordinator for login state. bound to app below
migrate = Migrate()                                        # the migration engine. bound to app below

app = Flask(__name__)                                      # the application object
app.secret_key = "dev-secret-change-me"                    # signs the session cookie — now load-bearing for auth security
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://localhost:5432/pothole_db"  # which Postgres db to talk to
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False       # silences an unused memory-leaking feature

db.init_app(app)                                           # bind db to this app
login_manager.init_app(app)                                # bind the login manager to this app
migrate.init_app(app, db)                                  # bind migrate — needs both app and db (it inspects models)

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

        if not hazard_type or not location:                # required-field validation
            flash("Please choose a hazard type and enter a location.")
            return redirect(url_for("report"))

        new_report = Report(
            hazard_type=hazard_type,
            location=location,
            description=description,
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


if __name__ == "__main__":
    app.run(debug=True)                                    # dev server: auto-reload + detailed error pages