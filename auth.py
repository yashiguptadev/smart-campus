from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required

from extensions import db
from models import User
from utils import is_safe_url

bp = Blueprint("auth", __name__)

SELF_REGISTER_ROLES = ("student", "faculty")  # admin/maintenance are created by an admin


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next")
            if is_safe_url(next_url):
                return redirect(next_url)
            return redirect(url_for("main.dashboard"))

        # Same message for unknown email and wrong password.
        flash("Incorrect email or password.", "danger")

    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        role = request.form.get("role", "student")

        error = None
        if not name or not email or not password:
            error = "Fill in your name, email and password."
        elif role not in SELF_REGISTER_ROLES:
            error = "Choose Student or Faculty."
        elif len(password) < 8:
            error = "Use a password with at least 8 characters."
        elif password != confirm:
            error = "The two passwords don't match."
        elif User.query.filter_by(email=email).first():
            error = "An account with this email already exists. Log in instead."

        if error:
            flash(error, "danger")
        else:
            user = User(name=name, email=email, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can log in now.", "success")
            return redirect(url_for("auth.login"))

    return render_template("register.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
