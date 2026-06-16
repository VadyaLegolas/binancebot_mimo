from flask import Flask, render_template, jsonify
from src.core.capital import get_capital_info
from src.database.session import SessionLocal
from src.database.models import Trade
from loguru import logger


def create_dash_app() -> Flask:
    app = Flask(__name__, template_folder="templates")

    @app.route("/")
    def index():
        info = get_capital_info()
        return render_template("index.html", capital=info)

    @app.route("/api/capital")
    def api_capital():
        info = get_capital_info()
        if info is None:
            return jsonify({"error": "No session"}), 404
        return jsonify(info)

    @app.route("/api/trades")
    def api_trades():
        db = SessionLocal()
        try:
            trades = db.query(Trade).order_by(-Trade.id).limit(50).all()
            return jsonify([{
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "type": t.type,
                "strategy": t.strategy,
                "quantity": t.quantity,
                "price": t.price,
                "total_usdt": t.total_usdt,
                "fee_total": t.fee_total,
                "net_pnl": t.net_pnl,
                "net_pnl_pct": t.net_pnl_pct,
                "status": t.status,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            } for t in trades])
        finally:
            db.close()

    @app.route("/api/stats")
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

    return app
