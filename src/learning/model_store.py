import json
from datetime import datetime
from loguru import logger
from src.database.session import SessionLocal
from src.database.models import ModelHistory


def save_params(strategy: str, model_type: str, params_before: dict,
                params_after: dict, metrics: dict) -> None:
    db = SessionLocal()
    try:
        record = ModelHistory(
            strategy=strategy,
            model_type=model_type,
            params_before=json.dumps(params_before),
            params_after=json.dumps(params_after),
            sharpe_before=metrics.get("sharpe_before"),
            sharpe_after=metrics.get("sharpe_after"),
            win_rate_before=metrics.get("win_rate_before"),
            win_rate_after=metrics.get("win_rate_after"),
            trades_count=metrics.get("trades_count"),
            applied=metrics.get("applied", True),
        )
        db.add(record)
        db.commit()
        logger.info(f"ModelStore: saved {model_type} params for {strategy}")
    finally:
        db.close()


def load_latest_params(strategy: str, model_type: str = "params") -> dict | None:
    db = SessionLocal()
    try:
        record = db.query(ModelHistory).filter(
            ModelHistory.strategy == strategy,
            ModelHistory.model_type == model_type,
            ModelHistory.applied == True,
        ).order_by(-ModelHistory.created_at).first()
        if record and record.params_after:
            return json.loads(record.params_after)
        return None
    finally:
        db.close()


def get_param_history(strategy: str, model_type: str = "params", limit: int = 10) -> list:
    db = SessionLocal()
    try:
        records = db.query(ModelHistory).filter(
            ModelHistory.strategy == strategy,
            ModelHistory.model_type == model_type,
        ).order_by(-ModelHistory.created_at).limit(limit).all()
        return [{
            "id": r.id,
            "params_before": json.loads(r.params_before) if r.params_before else None,
            "params_after": json.loads(r.params_after) if r.params_after else None,
            "sharpe_before": r.sharpe_before,
            "sharpe_after": r.sharpe_after,
            "win_rate_before": r.win_rate_before,
            "win_rate_after": r.win_rate_after,
            "applied": r.applied,
            "created_at": str(r.created_at),
        } for r in records]
    finally:
        db.close()
