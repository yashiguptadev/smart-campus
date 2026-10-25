from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from extensions import db
from models import ROLE_LABELS, ROLES, Booking, Resource, User
from notifications import notify
from utils import roles_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

BOOKING_STATUSES = ("pending", "approved", "rejected", "cancelled")
RESOURCE_STATUSES = ("available", "under_maintenance")


# ---------------------------------------------------------------- bookings
@bp.route("/bookings")
@roles_required("admin")
def bookings():
    status = request.args.get("status", "pending")
    query = Booking.query
    if status in BOOKING_STATUSES:
        query = query.filter_by(status=status)
    else:
        status = "all"
    rows = query.order_by(Booking.date, Booking.start_time).all()
    counts = {s: Booking.query.filter_by(status=s).count() for s in BOOKING_STATUSES}
    return render_template("admin_bookings.html", rows=rows, status=status, counts=counts)


@bp.route("/bookings/<int:booking_id>/<action>", methods=["POST"])
@roles_required("admin")
def decide(booking_id, action):
    if action not in ("approve", "reject"):
        abort(404)
    booking = db.get_or_404(Booking, booking_id)

    if booking.status != "pending":
        flash(f"{booking.code} is already {booking.status}. Only pending requests can be decided.", "warning")
    elif action == "approve" and booking.date < date.today():
        flash(f"{booking.code} is for a date that has passed, so it can't be approved. Reject it instead.", "warning")
    else:
        booking.status = "approved" if action == "approve" else "rejected"
        notify(
            booking.user_id,
            f"Your booking {booking.code} for {booking.resource.name} on "
            f"{booking.date.strftime('%d %b %Y')}, {booking.start_time.strftime('%H:%M')}–"
            f"{booking.end_time.strftime('%H:%M')} was {booking.status}.",
        )
        db.session.commit()
        flash(f"Booking {booking.code} {booking.status}.", "success")

    back = request.form.get("status")
    return redirect(url_for("admin.bookings", status=back if back in BOOKING_STATUSES else "pending"))


# --------------------------------------------------------------- resources
@bp.route("/resources")
@roles_required("admin")
def resources():
    rows = Resource.query.order_by(Resource.name).all()
    return render_template("admin_resources.html", rows=rows)


def _read_resource_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "type": request.form.get("type", "").strip().lower(),
        "location": request.form.get("location", "").strip(),
        "capacity": request.form.get("capacity", "").strip(),
        "status": request.form.get("status", "available"),
    }
    error = None
    if not data["name"] or not data["type"]:
        error = "Enter a name and a type."
    else:
        try:
            capacity = int(data["capacity"])
        except ValueError:
            capacity = 0
        if capacity < 1:
            error = "Capacity must be a whole number of 1 or more."
        elif data["status"] not in RESOURCE_STATUSES:
            error = "Choose a valid status."
    return data, error


@bp.route("/resources/new", methods=["GET", "POST"])
@bp.route("/resources/<int:resource_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def resource_form(resource_id=None):
    resource = db.get_or_404(Resource, resource_id) if resource_id else None

    if request.method == "POST":
        data, error = _read_resource_form()
        if not error:
            dup = Resource.query.filter(db.func.lower(Resource.name) == data["name"].lower())
            if resource:
                dup = dup.filter(Resource.id != resource.id)
            if dup.first():
                error = "A resource with this name already exists."
        if error:
            flash(error, "danger")
        else:
            is_new = resource is None
            if is_new:
                resource = Resource()
                db.session.add(resource)
            resource.name = data["name"]
            resource.type = data["type"]
            resource.location = data["location"] or None
            resource.capacity = int(data["capacity"])
            resource.status = data["status"]
            db.session.commit()
            flash(f"{resource.name} {'added' if is_new else 'updated'}.", "success")
            return redirect(url_for("admin.resources"))
    elif resource:
        data = {
            "name": resource.name,
            "type": resource.type,
            "location": resource.location or "",
            "capacity": resource.capacity,
            "status": resource.status,
        }
    else:
        data = {"name": "", "type": "", "location": "", "capacity": 1, "status": "available"}

    return render_template("resource_form.html", resource=resource, data=data, statuses=RESOURCE_STATUSES)


@bp.route("/resources/<int:resource_id>/delete", methods=["POST"])
@roles_required("admin")
def resource_delete(resource_id):
    resource = db.get_or_404(Resource, resource_id)
    if resource.bookings or resource.issues:
        flash(
            f"{resource.name} has bookings or issues on record, so it can't be deleted. "
            "Set it to under maintenance to stop new bookings.",
            "warning",
        )
    else:
        name = resource.name
        db.session.delete(resource)
        db.session.commit()
        flash(f"{name} deleted.", "success")
    return redirect(url_for("admin.resources"))


# ------------------------------------------------------------------- users
@bp.route("/users")
@roles_required("admin")
def users():
    rows = User.query.order_by(User.role, User.name).all()
    return render_template("admin_users.html", rows=rows, roles=ROLES, labels=ROLE_LABELS)


@bp.route("/users/new", methods=["GET", "POST"])
@roles_required("admin")
def user_new():
    data = {"name": "", "email": "", "role": "student"}
    if request.method == "POST":
        data = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "role": request.form.get("role", ""),
        }
        password = request.form.get("password", "")

        error = None
        if not data["name"] or not data["email"]:
            error = "Enter a name and an email."
        elif data["role"] not in ROLES:
            error = "Choose a valid role."
        elif len(password) < 8:
            error = "Use a password with at least 8 characters."
        elif User.query.filter_by(email=data["email"]).first():
            error = "An account with this email already exists."

        if error:
            flash(error, "danger")
        else:
            user = User(name=data["name"], email=data["email"], role=data["role"])
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Account created for {user.name} ({user.role_label}).", "success")
            return redirect(url_for("admin.users"))

    return render_template("user_form.html", data=data, roles=ROLES, labels=ROLE_LABELS)


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@roles_required("admin")
def user_role(user_id):
    from flask_login import current_user

    user = db.get_or_404(User, user_id)
    role = request.form.get("role", "")
    if user.id == current_user.id:
        flash("You can't change your own role. Ask another administrator.", "warning")
    elif role not in ROLES:
        flash("Choose a valid role.", "danger")
    else:
        user.role = role
        db.session.commit()
        flash(f"{user.name} is now {user.role_label}.", "success")
    return redirect(url_for("admin.users"))
