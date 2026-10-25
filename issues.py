from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Issue, Resource, User
from notifications import notify, notify_roles
from utils import roles_required

bp = Blueprint("issues", __name__, url_prefix="/issues")

REPORTER_ROLES = ("student", "faculty", "admin")
STAFF_ROLES = ("maintenance", "admin")
ISSUE_STATUSES = ("open", "in_progress", "resolved")
# Allowed moves: an issue can start work or be resolved, and never reopens.
TRANSITIONS = {"open": ("in_progress", "resolved"), "in_progress": ("resolved",)}


@bp.route("/")
@login_required
def list_issues():
    staff = current_user.role in STAFF_ROLES
    status = request.args.get("status", "active")
    query = Issue.query
    counts = None

    if staff:
        if status in ISSUE_STATUSES:
            query = query.filter_by(status=status)
        elif status == "active":
            query = query.filter(Issue.status != "resolved")
        else:
            status = "all"
        counts = {s: Issue.query.filter_by(status=s).count() for s in ISSUE_STATUSES}
        counts["active"] = counts["open"] + counts["in_progress"]
    else:
        query = query.filter_by(reported_by=current_user.id)

    rows = query.order_by(Issue.created_at.desc()).all()
    technicians = User.query.filter_by(role="maintenance").order_by(User.name).all()
    return render_template(
        "issues.html", rows=rows, staff=staff, status=status, counts=counts, technicians=technicians
    )


@bp.route("/new", methods=["GET", "POST"])
@roles_required(*REPORTER_ROLES)
def new():
    resources = Resource.query.order_by(Resource.name).all()
    form = {
        "resource_id": request.values.get("resource_id", type=int),
        "description": "",
    }

    if request.method == "POST":
        description = request.form.get("description", "").strip()
        form["description"] = description
        resource = db.session.get(Resource, form["resource_id"]) if form["resource_id"] else None

        if resource is None:
            flash("Choose the resource the problem is with.", "danger")
        elif len(description) < 5:
            flash("Describe the problem in a few words so maintenance knows what to look for.", "danger")
        else:
            issue = Issue(
                resource_id=resource.id,
                reported_by=current_user.id,
                description=description[:1000],
                status="open",
            )
            db.session.add(issue)
            db.session.flush()  # assigns the id so the issue code exists
            notify_roles(
                ("maintenance", "admin"),
                f"New issue {issue.code} on {resource.name}: {description[:120]}",
                exclude_id=current_user.id,
            )
            db.session.commit()
            flash(f"Issue {issue.code} reported. Maintenance staff can see it now.", "success")
            return redirect(url_for("issues.list_issues"))

    return render_template("issue_form.html", resources=resources, form=form)


@bp.route("/<int:issue_id>/status", methods=["POST"])
@roles_required(*STAFF_ROLES)
def update_status(issue_id):
    issue = db.get_or_404(Issue, issue_id)
    new_status = request.form.get("status", "")

    if new_status not in TRANSITIONS.get(issue.status, ()):
        flash(f"{issue.code} is {issue.status.replace('_', ' ')} and can't be changed that way.", "warning")
        return redirect(url_for("issues.list_issues"))

    issue.status = new_status
    if issue.assigned_to is None and current_user.role == "maintenance":
        issue.assigned_to = current_user.id

    resource = issue.resource
    message = None
    if new_status == "in_progress":
        resource.status = "under_maintenance"  # blocks new bookings while work is done
        message = f"Work started on {issue.code}. {resource.name} is now under maintenance."
    else:  # resolved
        issue.resolved_at = datetime.utcnow()
        others = Issue.query.filter(
            Issue.resource_id == issue.resource_id,
            Issue.id != issue.id,
            Issue.status != "resolved",
        ).count()
        if others == 0:
            resource.status = "available"
            message = f"Issue {issue.code} resolved. {resource.name} is available again."
        else:
            message = (
                f"Issue {issue.code} resolved. {resource.name} stays under maintenance "
                f"until its other open issues are resolved."
            )

    if issue.reported_by != current_user.id:
        if new_status == "in_progress":
            notify(issue.reported_by, f"Work has started on your issue {issue.code} ({resource.name}).")
        else:
            notify(issue.reported_by, f"Your issue {issue.code} ({resource.name}) was resolved.")
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("issues.list_issues"))


@bp.route("/<int:issue_id>/assign", methods=["POST"])
@roles_required("admin")
def assign(issue_id):
    issue = db.get_or_404(Issue, issue_id)
    assignee_id = request.form.get("assignee", type=int)
    user = db.session.get(User, assignee_id) if assignee_id else None

    if issue.status == "resolved":
        flash(f"{issue.code} is already resolved.", "warning")
    elif user is None or user.role != "maintenance":
        flash("Choose a maintenance staff member.", "danger")
    else:
        issue.assigned_to = user.id
        notify(user.id, f"Issue {issue.code} ({issue.resource.name}) was assigned to you.")
        db.session.commit()
        flash(f"{issue.code} assigned to {user.name}.", "success")
    return redirect(url_for("issues.list_issues"))
