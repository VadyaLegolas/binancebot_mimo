import logging
from src.dashboard.routes import create_dash_app

# Suppress Flask access logs
logging.getLogger('werkzeug').setLevel(logging.WARNING)


def run_dashboard():
    app = create_dash_app()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
