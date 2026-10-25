"""Create demo data. Run once:  python seed.py   (safe to re-run).

Also runs automatically at startup when the SEED_DEMO=1 environment variable is set.
ADMIN_PASSWORD and MAINT_PASSWORD override the default passwords of those two
accounts (applied only when the accounts are first created).
"""
import os
from datetime import date, time

from extensions import db
from models import Booking, Issue, Resource, User

USERS = [
    ("Demo Student", "student@muj.edu", "Stu@123", "student"),
    ("Demo Faculty", "faculty@muj.edu", "Fac@123", "faculty"),
    ("Campus Admin", "admin@muj.edu", os.environ.get("ADMIN_PASSWORD", "Admin@123"), "admin"),
    ("Maintenance Staff", "maintenance@muj.edu", os.environ.get("MAINT_PASSWORD", "Maint@123"), "maintenance"),
]

RESOURCES = [
    ("Computer Lab", "lab", "Block 1, Room 204", 60),
    ("Seminar Hall", "hall", "Academic Block 2", 120),
    ("Projector", "equipment", "Store Room, Block 1", 1),
    ("Auditorium", "hall", "Main Building", 400),
    ("Meeting Room", "room", "Admin Block, 2nd floor", 12),
]


def seed_data():
    """Add demo users, resources and sample rows. Needs an active app context."""
    for name, email, pwd, role in USERS:
        if not User.query.filter_by(email=email).first():
            u = User(name=name, email=email, role=role)
            u.set_password(pwd)
            db.session.add(u)
    for name, rtype, loc, cap in RESOURCES:
        if not Resource.query.filter_by(name=name).first():
            db.session.add(Resource(name=name, type=rtype, location=loc, capacity=cap))
    db.session.commit()

    lab = Resource.query.filter_by(name="Computer Lab").first()
    hall = Resource.query.filter_by(name="Seminar Hall").first()
    proj = Resource.query.filter_by(name="Projector").first()
    student = User.query.filter_by(email="student@muj.edu").first()
    faculty = User.query.filter_by(email="faculty@muj.edu").first()

    # Sample rows so the IDs match your test cases (B101-B103, I101).
    if Booking.query.count() == 0:
        db.session.add_all([
            Booking(user_id=student.id, resource_id=lab.id, date=date(2026, 11, 2),
                    start_time=time(14), end_time=time(15), purpose="Project work"),
            Booking(user_id=student.id, resource_id=hall.id, date=date(2026, 11, 3),
                    start_time=time(10), end_time=time(12), purpose="Club session"),
            Booking(user_id=student.id, resource_id=proj.id, date=date(2026, 11, 4),
                    start_time=time(9), end_time=time(10), purpose="Presentation"),
        ])
        db.session.add(Issue(resource_id=proj.id, reported_by=student.id,
                             description="Projector not working"))
        db.session.commit()

    # Occupied slot for TC06: Computer Lab 10:00-11:00 on 5 Nov 2026 (approved, faculty).
    if not Booking.query.filter_by(resource_id=lab.id, date=date(2026, 11, 5),
                                   start_time=time(10)).first():
        db.session.add(Booking(user_id=faculty.id, resource_id=lab.id, date=date(2026, 11, 5),
                               start_time=time(10), end_time=time(11),
                               purpose="Faculty lecture", status="approved"))
        db.session.commit()


def main():
    from app import create_app

    app = create_app()
    with app.app_context():
        seed_data()
    print("Seed complete.")


if __name__ == "__main__":
    main()
