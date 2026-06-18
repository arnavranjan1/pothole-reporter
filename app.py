from flask import Flask, render_template, request, redirect, url_for, flash            #for importing the framework, pulls Flask class from flask lib
from flask_sqlalchemy import SQLAlchemy                  #the Flask-SQLAlchemy extension class — gives us db.Model, db.session etc. wires the ORM into Flask
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column      #from sqlalchemy core (not flask): base class for models, the Mapped[] type-hint wrapper, and the column-definer function
from datetime import datetime, timezone                  #for the created_at timestamp; timezone.utc replaces the deprecated datetime.utcnow() in py 3.12

class Base(DeclarativeBase):                              #the declarative base every model inherits from. holds the metadata registry (the catalogue of all tables). like Object being the root in Java
    pass                                                  #just tells class exists

db = SQLAlchemy(model_class=Base)                         #the extension object built on our Base. this 'db' is the single gateway to everything: db.Model, db.session, db.String, db.select. NOT connected to the app yet — that's deliberate, see init_app

app = Flask(__name__)                               #creating the application ("waiter" as per analogy) Flask blueprint hands us an app
app.secret_key = "dev-secret-change-me"
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://localhost:5432/pothole_db"   #the one required key — tells db which server/db to talk to. scheme://host:port/dbname. add YOURNAME@ before localhost if it complains about the role
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False      #switches off a change-tracking feature nobody uses that leaks memory. silences a warning too

db.init_app(app)                                          #step 2: now bind db to this app. create-then-init pattern exists so db can live in its own file in bigger projects without circular imports

class Report(db.Model):                                   #subclassing db.Model (which traces back to Base) is what makes this class a TABLE, not just a class
    __tablename__ = "reports"                             #force the table name to 'reports' (plural) to match the SDD. without this it'd auto-name it 'report' (singular, lowercased class name)

    id: Mapped[int] = mapped_column(primary_key=True)                  #the primary key. Postgres auto-assigns an incrementing int on insert, you never set it yourself
    hazard_type: Mapped[str] = mapped_column(db.String(50))            #not nullable by default #VARCHAR(50), matches the form's hazard_type field. Mapped[str] without None = NOT NULL (matches our validation)
    location: Mapped[str] = mapped_column(db.String(255))              #VARCHAR(255), matches the form's location field. also NOT NULL
    description: Mapped[str | None] = mapped_column(db.Text, nullable=True)   #Text = no length cap (free-form). | None + nullable=True = optional, matches the form
    status: Mapped[str] = mapped_column(db.String(20), default="Reported")    #not in the form — the lifecycle field from the SDD. default fills it in so every new report starts as "Reported"
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),                       #timezone-aware timestamp
        default=lambda: datetime.now(timezone.utc),       #lambda is key: called fresh at EACH insert. without it, it'd evaluate once at startup and stamp every report the same frozen time
    )

    def __repr__(self):                                   #defines what a Report looks like when printed — Java's toString(). shows <Report 1 pothole @ ...> instead of an unhelpful memory address
        return f"<Report {self.id} {self.hazard_type} @ {self.location}>"

@app.route("/")                                     #decorator, pythons way of attaching extra behavior, when req comes in for URL / run the fn below, / is the root, the homepage what you get after this url with nothing after slash http://127.0.0.1:5000/
def home():                                         #just a normal python function named home nothing special on its own, it could be named anything. What makes it a web function is the line above it.
    return render_template("index.html")     #the return line is the response side, whatever the function returns becomes the content sent back to the browser, rn it returns a plain string, so the browser shows that text, later this same return will hand back a full HTML page instead but the mechanism is identical i.e. the function returns, that's what the browser receives.

@app.route("/report", methods = ["GET", "POST"])
def report():
    if request.method == "POST":
        hazard_type = request.form.get("hazard_type", "").strip()      #strip removes trailing or starting spaces
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()

        if not hazard_type or not location:
            flash("Please choose a hazard type and enter a location.")
            return redirect(url_for("report"))

        new_report = Report(
            hazard_type=hazard_type,
            location=location,
            description=description,
        )
        db.session.add(new_report)                    #stage it in the session — like git add. queued, not permanent
        db.session.commit()                           #flush to Postgres in one transaction — like git commit. NOW it's on disk and survives. after this new_report.id is even populated

        flash("Thanks! Your report has been submitted.")
        return redirect(url_for("home"))

    return render_template("report.html")

@app.route("/reports")
def reports():
    stmt = db.select(Report).order_by(Report.created_at.desc())   #build the query: all Reports, newest first. only DESCRIBES it — nothing has hit Postgres yet
    all_reports = db.session.execute(stmt).scalars().all()        #run it. execute = send to Postgres, .scalars() = unwrap each row to a real Report object (else you'd get 1-element tuples), .all() = collect into a list
    return render_template("reports.html", reports=all_reports)   #pass the list to the template under the name 'reports' so the Jinja loop can iterate it

if __name__ == "__main__":
    app.run(debug=True)

    #app.run starts the web server it boots up the loop that listens for incoming requests and dispatches them to your routes. Without this line, you'd have defined an app but never turned it on.

    #debug=True switches on development mode, which does two helpful things: it auto-reloads the server when you save changes to the file (so you don't restart manually after every edit), and it shows detailed error pages in the browser when something breaks, which makes debugging far easier. You turn this off in real deployment, but during development it's exactly what you want.

    #__name__ is: a built-in variable Python automatically sets to tell you how a file is being used. If you run the file directly, __name__ becomes the string "__main__". If the file is imported by another file, __name__ becomes the file's name instead. app = Flask(__name__) Here you're handing Flask your file's name so it knows where your app lives on disk — its starting point for finding related folders later (templates, static files, photos).  if __name__ == "__main__": this checks "am I being run directly?" If yes (__name__ is "__main__"), start the server. If the file were imported elsewhere instead, this would be skipped and the server wouldn't auto-start.

    #http:// — the protocol, i.e. the language the browser and server use to talk. HTTP is the standard request/response system of the web. (Real sites use https://, the encrypted version; local development uses plain http since there's nothing to protect on your own machine.) 127.0.0.1 — the address of the computer to talk to. This is a special reserved IP called localhost or the "loopback" address: it always points back to this very machine. So the request loops straight back into your own Mac and finds your Flask app — it never goes out to the internet, and nobody else can reach it. That's why it's ideal for private testing. (localhost is just a nickname for the same thing.) :5000 — the port number. One computer runs many network programs at once, and ports keep them separate — think of the IP as a building's address and the port as the specific apartment number.. / — the path, and the only part your code controls. It points to the root, the homepage.