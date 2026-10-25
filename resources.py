from datetime import date, datetime, time

from flask import Blueprint, flash, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from extensions import db
from models import Booking, Resource

bp = Blueprint("resources", __name__, url_prefix="/resources")

DAY_START, DAY_END = 8, 18  # one-hour slots from 08:00 to 18:00
ACTIVE_STATUSES = ("pending", "approved")  # these hold a slot; rejected/cancelled free it


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_slots(resource, day):
    """Return the hourly slots for a resource on a date with their state."""
    taken = Booking.query.filter(
        Booking.resource_id == resource.id,
        Booking.date == day,
        Booking.status.in_(ACTIVE_STATUSES),
    ).all()

    slots = []
    for hour in range(DAY_START, DAY_END):
        start, end = time(hour), time(hour + 1)
        if resource.status != "available":
            state = "maintenance"
        elif day < date.today():
            state = "past"
        elif any(b.start_time < end and b.end_time > start for b in taken):
            state = "booked"
        else:
            state = "free"
        slots.append({"start": start, "end": end, "state": state})
    return slots


@bp.route("/")
@login_required
def list_resources():
    q = request.args.get("q", "").strip()
    query = Resource.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Resource.name.ilike(like),
                Resource.type.ilike(like),
                Resource.location.ilike(like),
            )
        )
    resources = query.order_by(Resource.name).all()
    return render_template("resources.html", resources=resources, q=q)


@bp.route("/<int:resource_id>")
@login_required
def detail(resource_id):
    resource = db.get_or_404(Resource, resource_id)

    day = parse_date(request.args.get("date"))
    if request.args.get("date") and day is None:
        flash("That date isn't valid. Showing today instead.", "warning")
    day = day or date.today()

    slots = build_slots(resource, day)
    free_count = sum(1 for s in slots if s["state"] == "free")
    return render_template(
        "resource_detail.html",
        resource=resource,
        day=day,
        slots=slots,
        free_count=free_count,
        today=date.today(),
    )
