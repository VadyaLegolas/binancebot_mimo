from flask import Flask, Blueprint, render_template, jsonify
from src.core.capital import get_capital_info
from src.database.session import SessionLocal
from src.database.models import Trade
from sqlalchemy import func

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@bp.route("/api/capital")
def api_capital():
    info = get_capital_info()
    if not info:
        return jsonify({"error": "No session found. Run /init first."}), 404
    return jsonify(info)


@bp.route("/api/trades")
def api_trades():
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(-Trade.created_at).limit(100).all()
        return jsonify([{
            "id": t.id, "symbol": t.symbol, "side": t.side,
            "price": t.price, "quantity": t.quantity,
            "net_pnl": t.net_pnl, "fee_total": t.fee_total,
            "status": t.status, "strategy": t.strategy,
            "opened_at": str(t.opened_at), "closed_at": str(t.closed_at),
        } for t in trades])
    finally:
        db.close()


@bp.route("/api/positions")
def api_positions():
    db = SessionLocal()
    try:
        trades = db.query(Trade).filter(Trade.status == "OPEN").all()
        return jsonify([{
            "symbol": t.symbol, "quantity": t.quantity,
            "entry_price": t.price, "side": t.side,
            "strategy": t.strategy, "opened_at": str(t.opened_at),
        } for t in trades])
    finally:
        db.close()


@bp.route("/api/strategies")
def api_strategies():
    db = SessionLocal()
    try:
        stats = db.query(
            Trade.strategy,
            func.count(Trade.id).label("trades"),
            func.sum(Trade.net_pnl).label("net_pnl"),
            func.sum(Trade.fee_total).label("fees"),
        ).filter(Trade.status == "CLOSED").group_by(Trade.strategy).all()
        return jsonify([{
            "strategy": s.strategy or "manual",
            "trades": s.trades, "net_pnl": s.net_pnl or 0,
            "fees": s.fees or 0,
        } for s in stats])
    finally:
        db.close()


@bp.route("/api/stats")
def api_stats():
    db = SessionLocal()
    try:
        total = db.query(Trade).filter(Trade.status == "CLOSED").count()
        wins = db.query(Trade).filter(Trade.status == "CLOSED", Trade.net_pnl > 0).count()
        total_pnl = db.query(Trade.net_pnl).filter(Trade.status == "CLOSED").all()
        total_fees = db.query(Trade.fee_total).filter(Trade.status == "CLOSED").all()

        pnl_sum = sum(p[0] for p in total_pnl) if total_pnl else 0
        fees_sum = sum(f[0] for f in total_fees) if total_fees else 0
        win_rate = (wins / total * 100) if total > 0 else 0

        return jsonify({
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(pnl_sum, 2),
            "total_fees": round(fees_sum, 2),
        })
    finally:
        db.close()


def create_dash_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.register_blueprint(bp)
    return app


@bp.route("/api/learning")
def api_learning():
    from flask import current_app
    result = {}

    tuner = current_app.config.get("tuner")
    if tuner:
        result["tuner"] = tuner.get_status()

    weighter = current_app.config.get("weighter")
    if weighter:
        result["weighter"] = weighter.get_status()

    rl_agent = current_app.config.get("rl_agent")
    if rl_agent:
        result["rl_agent"] = rl_agent.get_status()

    guard = current_app.config.get("guard")
    if guard:
        result["anomalies"] = guard.check_all()

    return jsonify(result)


@bp.route("/api/learning/history/<strategy>")
def api_learning_history(strategy):
    from src.learning.model_store import get_param_history
    history = get_param_history(strategy)
    return jsonify(history)


@bp.route("/api/weights")
def api_weights():
    from flask import current_app
    weighter = current_app.config.get("weighter")
    if weighter:
        return jsonify(weighter.get_weights())
    return jsonify({"error": "Weighter not initialized"}), 503


@bp.route("/api/anomalies")
def api_anomalies():
    from flask import current_app
    guard = current_app.config.get("guard")
    if guard:
        return jsonify(guard.check_all())
    return jsonify([])
