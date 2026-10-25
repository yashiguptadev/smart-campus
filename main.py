from flask import Blueprint, redirect, url_for, render_template
from flask_login import current_user, login_required

from models import Booking, Issue, Resource, User

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    role = current_user.role

    if role in ("student", "faculty"):
        mine = Booking.query.filter_by(user_id=current_user.id)
        stats = [
            ("Pending", mine.filter_by(status="pending").count()),
            ("Approved", mine.filter_by(status="approved").count()),
            ("Rejected", mine.filter_by(status="rejected").count()),
            ("Cancelled", mine.filter_by(status="cancelled").count()),
        ]
        rows = mine.order_by(Booking.created_at.desc()).limit(5).all()
        kind, heading = "bookings", "Your recent bookings"

    elif role == "admin":
        stats = [
            ("Pending requests", Booking.query.filter_by(status="pending").count()),
            ("Resources", Resource.query.count()),
            ("Users", User.query.count()),
            ("Open issues", Issue.query.filter(Issue.status != "resolved").count()),
        ]
        rows = (
            Booking.query.filter_by(status="pending")
            .order_by(Booking.created_at.desc())
            .limit(5)
            .all()
        )
        kind, heading = "bookings", "Booking requests waiting for a decision"

    else:  # maintenance
        stats = [
            ("Open", Issue.query.filter_by(status="open").count()),
            ("In progress", Issue.query.filter_by(status="in_progress").count()),
            ("Resolved", Issue.query.filter_by(status="resolved").count()),
        ]
        rows = (
            Issue.query.filter(Issue.status != "resolved")
            .order_by(Issue.created_at.desc())
            .limit(5)
            .all()
        )
        kind, heading = "issues", "Issues that need attention"

    return render_template("dashboard.html", stats=stats, rows=rows, kind=kind, heading=heading)


@bp.app_errorhandler(403)
def forbidden(_):
    return render_template("403.html"), 403


@bp.app_errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404
