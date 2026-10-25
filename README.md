# Smart Campus Resource Optimizer

A web app for booking shared campus resources (labs, halls and equipment) without clashes. Built for a Software Engineering lab.

**Live demo:** https://smart-campus-9cia.onrender.com (free hosting, so the first visit after a quiet spell takes about a minute)

## Features

- Login and registration with four roles: student, faculty, administrator and maintenance staff
- Resource search and hourly availability by date
- Booking with a conflict check, cancellation, and admin approval or rejection
- Issue reporting and a maintenance workflow (a resource is under maintenance while work is done)
- In-app notifications

## Tech stack

Python, Flask, SQLAlchemy, Jinja2 and Bootstrap. Works with MySQL, Postgres or SQLite. Selenium for automated tests.

## Demo accounts

- Student: student@muj.edu / Stu@123
- Faculty: faculty@muj.edu / Fac@123
- Administrator and maintenance accounts are created by the seed script. Their passwords come from the ADMIN_PASSWORD and MAINT_PASSWORD settings.

## Run locally (Windows)

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    copy .env.example .env
    python seed.py
    python app.py

Then open http://127.0.0.1:5000

## Tests

With the app running, in a second terminal:

    pip install -r tests\requirements-test.txt
    python tests\run_campus_tests.py

## Deployment

See DEPLOY.md for the Render steps.
