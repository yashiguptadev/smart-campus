# Deploying to Render (free)

## 1. Put the project on GitHub
Run inside the project folder (the one containing app.py):

    git init
    git add .
    git commit -m "Smart Campus Resource Optimizer"
    git branch -M main
    git remote add origin https://github.com/YOUR_USERNAME/smart-campus.git
    git push -u origin main

Create the empty repository on github.com first (no README). `.env` and `campus.db`
are in `.gitignore`, so they are not uploaded.

## 2. Create the database on Render
New + > PostgreSQL > Instance type: Free. Copy its *Internal Database URL*.

## 3. Create the web service
New + > Web Service > connect the GitHub repository, then:

- Language: Python 3
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn "app:create_app()" --workers 1 --threads 4 --timeout 120`
- Instance type: Free

Environment variables:

| Name | Value |
|---|---|
| DATABASE_URL | the Internal Database URL from step 2 |
| SECRET_KEY | output of `python -c "import secrets; print(secrets.token_hex(32))"` |
| SEED_DEMO | 1 |
| ADMIN_PASSWORD | a strong password of your choice |
| MAINT_PASSWORD | a strong password of your choice |
| APP_TIMEZONE | Asia/Kolkata |
| PYTHON_VERSION | 3.12.3 |

Create the service. Your link will be https://YOUR-SERVICE-NAME.onrender.com

## 4. Run the Selenium tests against the public link
    $env:ADMIN_PASSWORD="your admin password"
    $env:MAINT_PASSWORD="your maintenance password"
    python tests\run_campus_tests.py --base-url https://YOUR-SERVICE-NAME.onrender.com
