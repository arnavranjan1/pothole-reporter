from flask import Flask, render_template, request, redirect, url_for, flash            #for importing the framework, pulls Flask class from flask lib 
app = Flask(__name__)                               #creating the application ("waiter" as per analogy) Flask blueprint hands us an app
app.secret_key = "dev-secret-change-me"

reports_store = []                                  #temporary in-memory store — resets every time the server restarts. Placeholder for the PostgreSQL table coming later. Named reports_store (not reports) to avoid colliding with the reports() view function below.

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
    
        reports_store.append({
            "hazard_type" : hazard_type,
            "location" : location,
            "description" : description,
        })

        flash("Thanks! Your report has been submitted.")
        return redirect(url_for("home"))

    return render_template("report.html")

@app.route("/reports")
def reports():
    return render_template("reports.html")

if __name__ == "__main__":
    app.run(debug=True)  
    
    #app.run starts the web server it boots up the loop that listens for incoming requests and dispatches them to your routes. Without this line, you'd have defined an app but never turned it on.
    
    #debug=True switches on development mode, which does two helpful things: it auto-reloads the server when you save changes to the file (so you don't restart manually after every edit), and it shows detailed error pages in the browser when something breaks, which makes debugging far easier. You turn this off in real deployment, but during development it's exactly what you want.
    
    #__name__ is: a built-in variable Python automatically sets to tell you how a file is being used. If you run the file directly, __name__ becomes the string "__main__". If the file is imported by another file, __name__ becomes the file's name instead. app = Flask(__name__) Here you're handing Flask your file's name so it knows where your app lives on disk — its starting point for finding related folders later (templates, static files, photos).  if __name__ == "__main__": this checks "am I being run directly?" If yes (__name__ is "__main__"), start the server. If the file were imported elsewhere instead, this would be skipped and the server wouldn't auto-start. 

    #http:// — the protocol, i.e. the language the browser and server use to talk. HTTP is the standard request/response system of the web. (Real sites use https://, the encrypted version; local development uses plain http since there's nothing to protect on your own machine.) 127.0.0.1 — the address of the computer to talk to. This is a special reserved IP called localhost or the "loopback" address: it always points back to this very machine. So the request loops straight back into your own Mac and finds your Flask app — it never goes out to the internet, and nobody else can reach it. That's why it's ideal for private testing. (localhost is just a nickname for the same thing.) :5000 — the port number. One computer runs many network programs at once, and ports keep them separate — think of the IP as a building's address and the port as the specific apartment number.. / — the path, and the only part your code controls. It points to the root, the homepage.