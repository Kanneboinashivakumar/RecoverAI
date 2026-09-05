"""Initial schema - all 13 tables

Revision ID: 001_initial
Revises:
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum types
paymentmethod_enum = sa.Enum("UPI", "CARD", "NETBANKING", "MANDATE", name="paymentmethod")
diagnosissource_enum = sa.Enum("deterministic", "llm", name="diagnosissource")
actionstatus_enum = sa.Enum("executed", "skipped", name="actionstatus")
verificationoutcome_enum = sa.Enum("success", "failure", name="verificationoutcome")
policytype_enum = sa.Enum("baseline", "recoverai", name="policytype")


def upgrade() -> None:
    # -- merchants --
    op.create_table(
        "merchants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("segment", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- customers --
    op.create_table(
        "customers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("account_age_days", sa.Integer()),
        sa.Column("lifetime_tx_count", sa.Integer()),
        sa.Column("successful_count", sa.Integer()),
        sa.Column("failed_count", sa.Integer()),
        sa.Column("avg_transaction_value", sa.Numeric()),
        sa.Column("upi_usage_pct", sa.Float()),
        sa.Column("card_usage_pct", sa.Float()),
        sa.Column("preferred_language", sa.String()),
        sa.Column("preferred_channel", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- transactions --
    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("merchant_id", UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("payment_method", paymentmethod_enum, nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("failure_code", sa.String(), nullable=True),
        sa.Column("source_event_id", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- revenue_events --
    op.create_table(
        "revenue_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("external_event_id", sa.String(), unique=True, nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("merchant_id", UUID(as_uuid=True), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("metadata", JSONB()),
        sa.Column("processed_at", sa.DateTime()),
    )

    # -- diagnoses --
    op.create_table(
        "diagnoses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("failure_code", sa.String(), nullable=False),
        sa.Column("source", diagnosissource_enum, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason_codes", JSONB()),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- predictions --
    op.create_table(
        "predictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("recovery_probability", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- decisions --
    op.create_table(
        "decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("delay_hours", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("confidence_llm", sa.Float()),
        sa.Column("expected_value_llm", sa.Numeric()),
        sa.Column("expected_value_verified", sa.Numeric()),
        sa.Column("reason_codes", JSONB()),
        sa.Column("policy_context", JSONB()),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- policy_evaluations --
    op.create_table(
        "policy_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("check_name", sa.String(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason_code", sa.String()),
        sa.Column("created_at", sa.DateTime()),
    )

    # -- actions --
    op.create_table(
        "actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("status", actionstatus_enum, nullable=False),
        sa.Column("executed_at", sa.DateTime()),
    )

    # -- verification_results --
    op.create_table(
        "verification_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("action_id", UUID(as_uuid=True), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("outcome", verificationoutcome_enum, nullable=False),
        sa.Column("simulated_amount_recovered", sa.Numeric()),
        sa.Column("verified_at", sa.DateTime()),
    )

    # -- audit_events --
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", UUID(as_uuid=True), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("input_snapshot", JSONB()),
        sa.Column("output_snapshot", JSONB()),
        sa.Column("reason_codes", JSONB()),
        sa.Column("policy_result", sa.String()),
    )

    # -- experiments --
    op.create_table(
        "experiments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("policy_type", policytype_enum, nullable=False),
        sa.Column("total_recovered", sa.Numeric()),
        sa.Column("recovery_rate", sa.Float()),
        sa.Column("incremental_recovered", sa.Numeric()),
        sa.Column("run_at", sa.DateTime()),
    )

    # -- policies --
    op.create_table(
        "policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("config", JSONB()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("policies")
    op.drop_table("experiments")
    op.drop_table("audit_events")
    op.drop_table("verification_results")
    op.drop_table("actions")
    op.drop_table("policy_evaluations")
    op.drop_table("decisions")
    op.drop_table("predictions")
    op.drop_table("diagnoses")
    op.drop_table("revenue_events")
    op.drop_table("transactions")
    op.drop_table("customers")
    op.drop_table("merchants")

    policytype_enum.drop(op.get_bind(), checkfirst=True)
    verificationoutcome_enum.drop(op.get_bind(), checkfirst=True)
    actionstatus_enum.drop(op.get_bind(), checkfirst=True)
    diagnosissource_enum.drop(op.get_bind(), checkfirst=True)
    paymentmethod_enum.drop(op.get_bind(), checkfirst=True)
