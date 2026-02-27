"""create assistant tables

Revision ID: 20260227_0001
Revises:
Create Date: 2026-02-27 10:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260227_0001"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "assistant_message_logs"):
        op.create_table(
            "assistant_message_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False, server_default="public"),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("user_message", sa.Text(), nullable=False),
            sa.Column("assistant_reply", sa.Text(), nullable=False),
            sa.Column("intent", sa.String(length=64), nullable=False, server_default="general"),
            sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("client_ip", sa.String(length=128), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "assistant_message_logs", "idx_assistant_message_logs_session_id"):
        op.create_index(
            "idx_assistant_message_logs_session_id",
            "assistant_message_logs",
            ["session_id"],
            unique=False,
        )

    if not _has_table(inspector, "assistant_contact_leads"):
        op.create_table(
            "assistant_contact_leads",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("source_mode", sa.String(length=20), nullable=False, server_default="public"),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("company", sa.String(length=255), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("client_ip", sa.String(length=128), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "assistant_contact_leads", "idx_assistant_contact_leads_session_id"):
        op.create_index(
            "idx_assistant_contact_leads_session_id",
            "assistant_contact_leads",
            ["session_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "assistant_contact_leads"):
        if _has_index(inspector, "assistant_contact_leads", "idx_assistant_contact_leads_session_id"):
            op.drop_index("idx_assistant_contact_leads_session_id", table_name="assistant_contact_leads")
        op.drop_table("assistant_contact_leads")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "assistant_message_logs"):
        if _has_index(inspector, "assistant_message_logs", "idx_assistant_message_logs_session_id"):
            op.drop_index("idx_assistant_message_logs_session_id", table_name="assistant_message_logs")
        op.drop_table("assistant_message_logs")
