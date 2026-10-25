from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, request
from flask_login import current_user, login_required


def roles_required(*roles):
    """Restrict a route to logged-in users with one of the given roles."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator


def is_safe_url(target):
    """Only allow redirects back to this same site (prevents open redirects)."""
    if not target:
        return False
    host = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and host.netloc == test.netloc
