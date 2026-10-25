from datetime import date, datetime, time

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.exceptions import NotFound

from extensions import db
from models import Booking, Resource
from resources import ACTIVE_STATUSES, DAY_END, DAY_START, parse_date
from notifications import notify_roles
from utils import roles_required

bp = Blueprint("bookings", __name__, url_prefix="/bookings")
BOOKER_ROLES = ("student", "faculty")


def parse_hour(value):
    """'10:00' -> time(10, 0). Only whole hours are accepted."""
    try:
        t = datetime.strptime(value or "", "%H:%M").time()
    except ValueError:
        return None
    return t if t.minute == 0 else None


def find_conflict(resource_id, day, start, end):
    """Return an existing active booking that overlaps the requested time, if any.

    Two bookings overlap when: existing_start < new_end AND existing_end > new_start.
    Back-to-back bookings (10-11 and 11-12) do not overlap.
    """
    return Booking.query.filter(
        Booking.resource_id == resource_id,
        Booking.date == day,
        Booking.status.in_(ACTIVE_STATUSES),
        Booking.start_time < end,
        Booking.end_time > start,
    ).first()


def validate_booking(resource, day, start, end, purpose):
    """Return an error message, or None when the request is valid."""
    if resource.status != "available":
        return "This resource is under maintenance and can't be booked right now."
    if day is None:
        return "Choose a valid date."
    if start is None or end is None:
        return "Choose a start and end time."
    if not (DAY_START <= start.hour < end.hour <= DAY_END):
        return f"The end time must be after the start time, between {DAY_START:02d}:00 and {DAY_END:02d}:00."
    if day < date.today():
        return "That date has passed. Choose today or a later date."
    if day == date.today() and start <= datetime.now().time():
        return "That start time has already passed. Choose a later slot."
    if not purpose:
        return "Enter the purpose of the booking."
    clash = find_conflict(resource.id, day, start, end)
    if clash:
        return (
            f"This slot is unavailable. {resource.name} is already booked "
            f"{clash.start_time.strftime('%H:%M')}–{clash.end_time.strftime('%H:%M')} on "
            f"{day.strftime('%d %b %Y')}. Choose another time or date."
        )
    return None


def hour_options(first, last):
    return [f"{h:02d}:00" for h in range(first, last + 1)]


@bp.route("/new", methods=["GET", "POST"])
@roles_required(*BOOKER_ROLES)
def new():
    resource_id = request.values.get("resource_id", type=int)
    if resource_id is None:
        raise NotFound()
    resource = db.get_or_404(Resource, resource_id)

    if request.method == "POST":
        day = parse_date(request.form.get("date"))
        start = parse_hour(request.form.get("start"))
        end = parse_hour(request.form.get("end"))
        purpose = request.form.get("purpose", "").strip()

        error = validate_booking(resource, day, start, end, purpose)
        if error:
            flash(error, "danger")
        else:
            booking = Booking(
                user_id=current_user.id,
                resource_id=resource.id,
                date=day,
                start_time=start,
                end_time=end,
                purpose=purpose[:255],
                status="pending",
            )
            db.session.add(booking)
            db.session.flush()  # assigns the id so the booking code exists
            notify_roles(
                ("admin",),
                f"New booking request {booking.code}: {resource.name} on {day.strftime('%d %b %Y')}, "
                f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} from {current_user.name}.",
            )
            db.session.commit()
            flash(
                f"Booking request {booking.code} sent. An administrator will review it.",
                "success",
            )
            return redirect(url_for("bookings.mine"))

        form = {
            "date": request.form.get("date", ""),
            "start": request.form.get("start", ""),
            "end": request.form.get("end", ""),
            "purpose": purpose,
        }
    else:
        day = parse_date(request.args.get("date")) or date.today()
        start = parse_hour(request.args.get("start")) or time(DAY_START)
        end = time(min(start.hour + 1, DAY_END))
        form = {
            "date": day.isoformat(),
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M"),
            "purpose": "",
        }

    return render_template(
        "book.html",
        resource=resource,
        form=form,
        today=date.today(),
        start_options=hour_options(DAY_START, DAY_END - 1),
        end_options=hour_options(DAY_START + 1, DAY_END),
    )


@bp.route("/")
@roles_required(*BOOKER_ROLES)
def mine():
    bookings = (
        Booking.query.filter_by(user_id=current_user.id)
        .order_by(Booking.date.desc(), Booking.start_time.desc())
        .all()
    )
    return render_template("my_bookings.html", bookings=bookings, today=date.today())


@bp.route("/<int:booking_id>/cancel", methods=["POST"])
@roles_required(*BOOKER_ROLES)
def cancel(booking_id):
    booking = db.get_or_404(Booking, booking_id)
    if booking.user_id != current_user.id:
        abort(403)

    if booking.status not in ACTIVE_STATUSES:
        flash("Only pending or approved bookings can be cancelled.", "warning")
    elif booking.date < date.today():
        flash("This booking is in the past and can't be cancelled.", "warning")
    else:
        booking.status = "cancelled"  # frees the slot: only pending/approved hold one
        db.session.commit()
        flash(f"Booking {booking.code} cancelled. The slot is free again.", "success")
    return redirect(url_for("bookings.mine"))
