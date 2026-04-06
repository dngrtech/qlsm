from functools import wraps
from ui import create_app

def with_app_context(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app = create_app()
        with app.app_context():
            return f(*args, **kwargs)
    return decorated_function