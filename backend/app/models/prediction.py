"""
StockMind AI — Prediction & ML Models
Database models for predictions, explanations, outcomes, model versions, and training.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from app.models.compat import CompatUUID as UUID, CompatJSON as JSON
from sqlalchemy.sql import func

from app.database import Base


class ModelVersion(Base):
    """Versioned ML model metadata."""

    __tablename__ = "model_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False)
    model_type = Column(String(50), nullable=False)  # ensemble, lightgbm, xgboost, etc.

    # Training info
    training_start = Column(DateTime(timezone=True), nullable=True)
    training_end = Column(DateTime(timezone=True), nullable=True)
    training_data_start = Column(DateTime(timezone=True), nullable=True)
    training_data_end = Column(DateTime(timezone=True), nullable=True)
    feature_version = Column(String(20), nullable=True)
    features_used = Column(JSON, nullable=True)  # List of feature names
    target = Column(String(100), nullable=True)
    hyperparameters = Column(JSON, nullable=True)

    # Validation metrics
    accuracy = Column(Float, nullable=True)
    precision_score = Column(Float, nullable=True)
    recall_score = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    roc_auc = Column(Float, nullable=True)
    pr_auc = Column(Float, nullable=True)
    brier_score = Column(Float, nullable=True)
    log_loss_score = Column(Float, nullable=True)
    calibration_error = Column(Float, nullable=True)

    # Walk-forward metrics
    walkforward_sharpe = Column(Float, nullable=True)
    walkforward_cagr = Column(Float, nullable=True)
    walkforward_max_dd = Column(Float, nullable=True)

    # Model status
    status = Column(String(20), nullable=False, default="training")  # training, validating, champion, challenger, retired
    is_champion = Column(Boolean, default=False, nullable=False)
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    retired_at = Column(DateTime(timezone=True), nullable=True)

    # Artifact path
    artifact_path = Column(Text, nullable=True)
    model_card = Column(Text, nullable=True)  # Markdown model card

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_model_name_version", "model_name", "version", unique=True),
        Index("ix_model_champion", "model_name", "is_champion"),
    )


class Prediction(Base):
    """Individual prediction record with full audit trail."""

    __tablename__ = "predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instrument_key = Column(String(100), nullable=False, index=True)
    symbol = Column(String(50), nullable=True)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=True)

    # Prediction metadata
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    horizon = Column(String(10), nullable=False)  # 1D, 3D, 5D, 10D, 20D, intraday
    data_timestamp = Column(DateTime(timezone=True), nullable=False)  # When the input data was from

    # Direction probabilities
    prob_up = Column(Float, nullable=False)
    prob_flat = Column(Float, nullable=True)
    prob_down = Column(Float, nullable=False)

    # Expected return
    expected_return = Column(Float, nullable=True)
    prediction_interval_lower = Column(Float, nullable=True)
    prediction_interval_upper = Column(Float, nullable=True)

    # Scenarios
    bull_scenario = Column(Text, nullable=True)
    base_scenario = Column(Text, nullable=True)
    bear_scenario = Column(Text, nullable=True)

    # Meta
    confidence = Column(String(20), nullable=True)  # high, moderate, low
    risk = Column(String(20), nullable=True)  # low, medium, medium-high, high
    signal = Column(String(50), nullable=True)  # potential_upside, potential_downside, neutral, no_signal
    market_regime = Column(String(50), nullable=True)

    # Feature snapshot (compressed JSON)
    feature_snapshot = Column(JSON, nullable=True)

    # Outcome tracking
    outcome_recorded = Column(Boolean, default=False, nullable=False)
    actual_return = Column(Float, nullable=True)
    direction_correct = Column(Boolean, nullable=True)
    prediction_error = Column(Float, nullable=True)
    max_adverse_excursion = Column(Float, nullable=True)
    max_favorable_excursion = Column(Float, nullable=True)
    outcome_recorded_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_pred_inst_ts_horizon", "instrument_key", "timestamp", "horizon"),
        Index("ix_pred_outcome", "outcome_recorded", "timestamp"),
    )


class PredictionExplanation(Base):
    """SHAP-based explanation for a prediction."""

    __tablename__ = "prediction_explanations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    prediction_id = Column(UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Top contributing features
    positive_factors = Column(JSON, nullable=True)  # [{feature, value, contribution, description}]
    negative_factors = Column(JSON, nullable=True)
    shap_values = Column(JSON, nullable=True)  # Full SHAP value dict
    feature_importances = Column(JSON, nullable=True)

    # Human-readable explanation
    explanation_text = Column(Text, nullable=True)
    counterfactual = Column(Text, nullable=True)  # What would change the prediction

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TrainingRun(Base):
    """Training pipeline execution log."""

    __tablename__ = "training_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=True)
    run_type = Column(String(50), nullable=False)  # initial, retrain, challenger

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="running")  # running, completed, failed

    # Configuration
    config = Column(JSON, nullable=True)
    training_data_rows = Column(Integer, nullable=True)
    validation_data_rows = Column(Integer, nullable=True)
    test_data_rows = Column(Integer, nullable=True)

    # Results
    metrics = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    log_path = Column(Text, nullable=True)


class DriftMetric(Base):
    """Model and data drift tracking."""

    __tablename__ = "drift_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey("model_versions.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    metric_type = Column(String(50), nullable=False)  # feature_drift, target_drift, prediction_drift, calibration_drift

    feature_name = Column(String(100), nullable=True)
    psi_value = Column(Float, nullable=True)  # Population Stability Index
    ks_statistic = Column(Float, nullable=True)  # Kolmogorov-Smirnov
    js_divergence = Column(Float, nullable=True)  # Jensen-Shannon
    drift_detected = Column(Boolean, default=False)
    details = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_drift_model_ts", "model_version_id", "timestamp"),
    )


class AuditLog(Base):
    """Security and action audit trail."""

    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_audit_user_ts", "user_id", "timestamp"),
        Index("ix_audit_action_ts", "action", "timestamp"),
    )
