import os
from datetime import timezone

from flask import Flask

from config import Config
from extensions import csrf, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if os.environ.get("RENDER") and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("Set the SECRET_KEY environment variable before deploying.")

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Log in to continue."
    login_manager.login_message_category = "info"

    import models  # noqa: F401  (registers tables before create_all)
    from auth import bp as auth_bp
    from main import bp as main_bp
    from resources import bp as resources_bp
    from bookings import bp as bookings_bp
    from admin import bp as admin_bp
    from issues import bp as issues_bp
    from notifications import bp as notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(notifications_bp)

    @app.context_processor
    def inject_unread_count():
        from flask_login import current_user

        if current_user.is_authenticated:
            count = models.Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            return {"unread_count": count}
        return {"unread_count": 0}

    @app.template_filter("localtime")
    def localtime(value):
        """Stored times are UTC. Show them in APP_TIMEZONE (for example Asia/Kolkata)
        when it is set, otherwise in the computer's own time zone."""
        if value is None:
            return ""
        aware = value.replace(tzinfo=timezone.utc)
        zone = os.environ.get("APP_TIMEZONE")
        if zone:
            from zoneinfo import ZoneInfo

            aware = aware.astimezone(ZoneInfo(zone))
        else:
            aware = aware.astimezone()
        return aware.strftime("%d %b %Y, %H:%M")

    with app.app_context():
        db.create_all()
        if os.environ.get("SEED_DEMO") == "1":  # used on hosts without a shell (Render free)
            from seed import seed_data

            seed_data()

    return app


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
