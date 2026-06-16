from src.dashboard.routes import create_dash_app


def run_dashboard():
    app = create_dash_app()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
