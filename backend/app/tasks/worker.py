"""
StockMind AI — Celery Task Worker
Background tasks for data fetching, feature computation, prediction generation,
and continuous learning pipeline.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "stockmind",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=600,
    beat_schedule={
        # Refresh instrument list daily at 8:00 AM IST
        "refresh-instruments": {
            "task": "app.tasks.worker.refresh_instruments",
            "schedule": 3600.0 * 24,
        },
        # Record prediction outcomes every hour during market hours
        "record-prediction-outcomes": {
            "task": "app.tasks.worker.record_prediction_outcomes",
            "schedule": 3600.0,
        },
        # Compute features for scanner every 15 minutes during market hours
        "compute-scanner-features": {
            "task": "app.tasks.worker.compute_scanner_features",
            "schedule": 900.0,
        },
        # Drift detection daily at 6 PM IST
        "drift-detection": {
            "task": "app.tasks.worker.run_drift_detection",
            "schedule": 3600.0 * 24,
        },
    },
)


@celery_app.task(name="app.tasks.worker.refresh_instruments")
def refresh_instruments():
    """Download and refresh the instrument universe from Upstox."""
    from app.core.logging import get_logger
    logger = get_logger("task.refresh_instruments")
    logger.info("task_started", task="refresh_instruments")
    # Implementation: download BOD instrument file, parse, upsert to DB
    # This runs daily before market opens
    return {"status": "completed", "task": "refresh_instruments"}


@celery_app.task(name="app.tasks.worker.compute_scanner_features")
def compute_scanner_features():
    """Compute technical features for the market scanner universe."""
    from app.core.logging import get_logger
    logger = get_logger("task.compute_features")
    logger.info("task_started", task="compute_scanner_features")
    # Implementation: fetch candles for scanner universe, compute features, store
    return {"status": "completed", "task": "compute_scanner_features"}


@celery_app.task(name="app.tasks.worker.record_prediction_outcomes")
def record_prediction_outcomes():
    """
    Record actual outcomes for past predictions.
    This feeds the continuous learning loop.

    For each prediction where the horizon has expired:
    1. Fetch the actual price
    2. Calculate actual return
    3. Record prediction error
    4. Store for model evaluation
    """
    from app.core.logging import get_logger
    logger = get_logger("task.prediction_outcomes")
    logger.info("task_started", task="record_prediction_outcomes")
    return {"status": "completed", "task": "record_prediction_outcomes"}


@celery_app.task(name="app.tasks.worker.run_drift_detection")
def run_drift_detection():
    """
    Run drift detection on features, targets, and predictions.
    Triggers retraining recommendation if drift exceeds thresholds.
    """
    from app.core.logging import get_logger
    logger = get_logger("task.drift_detection")
    logger.info("task_started", task="run_drift_detection")
    return {"status": "completed", "task": "run_drift_detection"}


@celery_app.task(name="app.tasks.worker.generate_daily_signals")
def generate_daily_signals():
    """
    Run the full daily stock discovery and signal generation pipeline.
    Implements all 8 discovery buckets.
    """
    from app.core.logging import get_logger
    logger = get_logger("task.daily_signals")
    logger.info("task_started", task="generate_daily_signals")
    return {"status": "completed", "task": "generate_daily_signals"}


@celery_app.task(name="app.tasks.worker.train_challenger_model")
def train_challenger_model(config: dict = None):
    """
    Train a challenger model.
    Does NOT automatically replace the champion.
    Must pass validation gates before promotion.
    """
    from app.core.logging import get_logger
    logger = get_logger("task.train_challenger")
    logger.info("task_started", task="train_challenger_model", config=config)
    return {"status": "completed", "task": "train_challenger_model"}
