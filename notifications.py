from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Notification, User

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


# ---- helpers used by the other modules. They add rows to the current
# ---- transaction; the caller commits together with its own change.
def notify(user_id, message):
    """Queue a notification for one user."""
    db.session.add(Notification(user_id=user_id, message=message[:255]))


def notify_roles(roles, message, exclude_id=None):
    """Queue a notification for every user holding one of the roles."""
    for user in User.query.filter(User.role.in_(roles)).all():
        if user.id != exclude_id:
            notify(user.id, message)


# ------------------------------------------------------------------ pages
@bp.route("/")
@login_required
def list_notifications():
    rows = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
        .all()
    )
    unread = sum(1 for n in rows if not n.is_read)
    return render_template("notifications.html", rows=rows, unread=unread)


@bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    note = db.get_or_404(Notification, notification_id)
    if note.user_id != current_user.id:
        abort(403)
    note.is_read = True
    db.session.commit()
    return redirect(url_for("notifications.list_notifications"))


@bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(url_for("notifications.list_notifications"))
