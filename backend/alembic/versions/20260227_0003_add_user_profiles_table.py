"""add user_profiles table

Revision ID: 20260227_0003
Revises: 20260224_0002
Create Date: 2026-02-27 18:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260227_0003"
down_revision = "20260224_0002"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "user_profiles"):
        op.create_table(
            "user_profiles",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("organization", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "user_profiles", "uq_user_profiles_user_id"):
        op.create_index("uq_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, "user_profiles"):
        if _has_index(inspector, "user_profiles", "uq_user_profiles_user_id"):
            op.drop_index("uq_user_profiles_user_id", table_name="user_profiles")
        op.drop_table("user_profiles")
