import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ---- Enums ----


class PaymentMethod(str, enum.Enum):
    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    MANDATE = "MANDATE"


class DiagnosisSource(str, enum.Enum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"


class ActionStatus(str, enum.Enum):
    EXECUTED = "executed"
    SKIPPED = "skipped"


class VerificationOutcome(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class PolicyType(str, enum.Enum):
    BASELINE = "baseline"
    RECOVERAI = "recoverai"


# ---- Tables ----


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    segment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    account_age_days = Column(Integer)
    lifetime_tx_count = Column(Integer)
    successful_count = Column(Integer)
    failed_count = Column(Integer)
    avg_transaction_value = Column(Numeric)
    upi_usage_pct = Column(Float)
    card_usage_pct = Column(Float)
    preferred_language = Column(String)
    preferred_channel = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    amount = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    status = Column(String, nullable=False)
    failure_code = Column(String, nullable=True)
    source_event_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class RevenueEvent(Base):
    __tablename__ = "revenue_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_event_id = Column(String, unique=True, nullable=False)
    event_type = Column(String, nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True)
    amount = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    source = Column(String, nullable=False)
    metadata_ = Column("metadata", JSONB)
    processed_at = Column(DateTime)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    failure_code = Column(String, nullable=False)
    source = Column(Enum(DiagnosisSource, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    confidence = Column(Float, nullable=False)
    reason_codes = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    recovery_probability = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    action_type = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    delay_hours = Column(Integer, nullable=False)
    amount = Column(Numeric, nullable=False)
    confidence_llm = Column(Float)
    expected_value_llm = Column(Numeric)
    expected_value_verified = Column(Numeric)
    reason_codes = Column(JSONB)
    policy_context = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)


class PolicyEvaluation(Base):
    __tablename__ = "policy_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=False)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    check_name = Column(String, nullable=False)
    passed = Column(Boolean, nullable=False)
    reason_code = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Action(Base):
    __tablename__ = "actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=False)
    action_type = Column(String, nullable=False)
    status = Column(Enum(ActionStatus, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    executed_at = Column(DateTime)


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    action_id = Column(UUID(as_uuid=True), ForeignKey("actions.id"), nullable=False)
    outcome = Column(Enum(VerificationOutcome, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    simulated_amount_recovered = Column(Numeric)
    verified_at = Column(DateTime)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False)
    event_type = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    actor = Column(String, nullable=False)
    input_snapshot = Column(JSONB)
    output_snapshot = Column(JSONB)
    reason_codes = Column(JSONB)
    policy_result = Column(String)


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seed = Column(Integer, nullable=False)
    batch_size = Column(Integer, nullable=False)
    policy_type = Column(Enum(PolicyType, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    total_recovered = Column(Numeric)
    recovery_rate = Column(Float)
    incremental_recovered = Column(Numeric)
    run_at = Column(DateTime, default=datetime.utcnow)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    config = Column(JSONB)
    version = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
