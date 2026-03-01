"""add tenant_id to projects

Revision ID: 20260301_0004
Revises: 20260227_0003
Create Date: 2026-03-01 10:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260301_0004"
down_revision = "20260227_0003"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "projects"):
        return

    if not _has_column(inspector, "projects", "tenant_id"):
        op.add_column("projects", sa.Column("tenant_id", sa.String(length=128), nullable=True))

    # Backfill tenant scope:
    # 1) Legacy rows with owner_id -> synthetic user tenant.
    # 2) Any remaining nulls -> deterministic project scope.
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET tenant_id = CONCAT('user:', owner_id::text)
            WHERE tenant_id IS NULL
              AND owner_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE projects
            SET tenant_id = CONCAT('project:', id::text)
            WHERE tenant_id IS NULL
            """
        )
    )

    op.alter_column("projects", "tenant_id", existing_type=sa.String(length=128), nullable=False)

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "projects", "ix_projects_tenant_id"):
        op.create_index("ix_projects_tenant_id", "projects", ["tenant_id"], unique=False)
    if not _has_index(inspector, "projects", "ix_projects_tenant_id_created_at"):
        op.create_index(
            "ix_projects_tenant_id_created_at",
            "projects",
            ["tenant_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "projects"):
        return

    if _has_index(inspector, "projects", "ix_projects_tenant_id_created_at"):
        op.drop_index("ix_projects_tenant_id_created_at", table_name="projects")
    if _has_index(inspector, "projects", "ix_projects_tenant_id"):
        op.drop_index("ix_projects_tenant_id", table_name="projects")
    if _has_column(inspector, "projects", "tenant_id"):
        op.drop_column("projects", "tenant_id")
