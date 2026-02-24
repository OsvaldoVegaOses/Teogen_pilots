"""add domain_template to projects

Revision ID: 20260223_0001
Revises:
Create Date: 2026-02-23 14:20:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260223_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("projects")}
    if "domain_template" not in columns:
        op.add_column(
            "projects",
            sa.Column("domain_template", sa.String(length=50), nullable=False, server_default="generic"),
        )
        op.alter_column("projects", "domain_template", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("projects")}
    if "domain_template" in columns:
        op.drop_column("projects", "domain_template")
