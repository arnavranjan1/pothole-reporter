# Smart Pothole & Road Hazard Reporter

A crowd-sourced civic web application that lets citizens report road hazards — potholes, broken streetlights, garbage, and flooding — pin them to an interactive map with a photo, and lets municipal admins triage and resolve them through a clear status lifecycle.

> **Status:** In active development. Core application complete (auth, reporting, map, admin dashboard, search/pagination, tests). Cloud deployment in progress.

---

## Why this exists

Reporting a pothole to a local authority usually means a phone call, a form buried three pages deep on a municipal site, or nothing at all — and once reported, citizens have no visibility into whether anything happened. This project closes that loop: anyone can file a geotagged, photo-backed report in under a minute, see every hazard in their area on a map, and follow each report as it moves from **Reported → In Progress → Fixed**.

---

## Features

**For citizens**
- Register, log in, and file hazard reports with a location, hazard type, description, and photo upload
- Interactive Leaflet map (OpenStreetMap tiles) showing all reported hazards as map markers
- Per-report detail pages with status, photo, and metadata
- "My Reports" page to track everything you've personally filed
- Reports respect a per-filer privacy rule so reporter identity is only revealed where appropriate

**For admins**
- Dedicated admin dashboard listing all reports
- One-click status changes through the report lifecycle
- Filtering by status and hazard type
- Full-text search and pagination across large report sets

**Throughout**
- CSRF protection on every state-changing form
- Role-based access (citizen vs. admin)
- Consistent "clean govtech" design system with reusable Jinja components
- Friendly 404 / 500 error pages (the 500 handler rolls back the active DB session)

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | Flask |
| ORM / database | SQLAlchemy 2.0 style + PostgreSQL |
| Migrations | Flask-Migrate (Alembic) |
| Authentication | Flask-Login |
| Forms / security | Flask-WTF + WTForms (CSRF protection) |
| Templating | Jinja2 (with reusable macros & partials) |
| Mapping | Leaflet.js + OpenStreetMap |
| Testing | pytest (against a dedicated test database) |
| WSGI server (prod) | Gunicorn |
| Hosting (planned) | Render (app) · Neon (Postgres) · Cloudinary (image storage) |

---

## Architecture at a glance

The app follows a standard server-rendered Flask layout. Configuration is centralized in `config.py` (including the single source of truth for allowed hazard types). Forms are defined in `forms.py`. Templates share a base layout and a set of reusable partials and macros — a status badge macro, a flex navigation bar that highlights the active link, and an endpoint-agnostic pagination partial that works on any paginated route without modification.

```
pothole-reporter/
├── app.py                 # application factory, models, routes, error handlers
├── config.py              # configuration + ALLOWED_HAZARDS (value→label dict)
├── forms.py               # LoginForm, RegistrationForm, ReportForm
├── requirements.txt
├── pytest.ini             # pythonpath = .
├── conftest.py            # test fixtures; points to the test database via env var
├── migrations/            # Alembic migration history
├── static/
│   └── css/style.css      # design system (CSS custom properties at :root)
├── templates/
│   ├── base.html
│   ├── _macros.html       # status badge macro, etc.
│   ├── _pagination.html   # reusable, endpoint-agnostic pagination partial
│   ├── login.html / register.html
│   ├── report_form.html
│   ├── report_detail.html
│   ├── my_reports.html
│   └── admin/...          # admin dashboard
└── tests/
```

---

## Getting started (local)

### Prerequisites
- Python 3.12+
- PostgreSQL running locally
- `git`

### 1. Clone and set up the environment
```bash
git clone <your-repo-url>
cd pothole-reporter

python3 -m venv venv
source venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
```

### 2. Create the databases
```bash
createdb pothole_db
createdb pothole_test_db         # used by the test suite
```

### 3. Configure environment variables
Create a `.env` (or export these in your shell). **Never commit secrets.**
```bash
export SECRET_KEY="a-long-random-string"
export DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/pothole_db"
export TEST_DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/pothole_test_db"
```

### 4. Apply migrations
```bash
flask db upgrade
```

### 5. Run the app
```bash
flask run --port 5001
```
> Port **5001** is used instead of 5000 because macOS reserves port 5000 for AirPlay Receiver.

Open <http://localhost:5001>.

---

## Running tests

The suite runs against a separate `pothole_test_db` so it never touches development data.

```bash
pytest
```
