"""add fragment anchors and code-fragment trace fields

Revision ID: 20260224_0002
Revises: 20260223_0001
Create Date: 2026-02-24 11:35:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_0002"
down_revision = "20260223_0001"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {c["name"] for c in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {i["name"] for i in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # code_fragment_links fields for provenance and text span.
    if not _has_column(inspector, "code_fragment_links", "char_start"):
        op.add_column("code_fragment_links", sa.Column("char_start", sa.Integer(), nullable=True))
    if not _has_column(inspector, "code_fragment_links", "char_end"):
        op.add_column("code_fragment_links", sa.Column("char_end", sa.Integer(), nullable=True))
    if not _has_column(inspector, "code_fragment_links", "source"):
        op.add_column("code_fragment_links", sa.Column("source", sa.String(length=20), nullable=True))
    if not _has_column(inspector, "code_fragment_links", "linked_at"):
        op.add_column(
            "code_fragment_links",
            sa.Column("linked_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
        )

    # fragment anchors for transcript navigation.
    if not _has_column(inspector, "fragments", "paragraph_index"):
        op.add_column("fragments", sa.Column("paragraph_index", sa.Integer(), nullable=True))
    if not _has_column(inspector, "fragments", "start_ms"):
        op.add_column("fragments", sa.Column("start_ms", sa.Integer(), nullable=True))
    if not _has_column(inspector, "fragments", "end_ms"):
        op.add_column("fragments", sa.Column("end_ms", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if not _has_index(inspector, "code_fragment_links", "idx_code_fragment_links_code_id"):
        op.create_index(
            "idx_code_fragment_links_code_id",
            "code_fragment_links",
            ["code_id"],
            unique=False,
        )
    if not _has_index(inspector, "code_fragment_links", "idx_code_fragment_links_fragment_id"):
        op.create_index(
            "idx_code_fragment_links_fragment_id",
            "code_fragment_links",
            ["fragment_id"],
            unique=False,
        )
    if not _has_index(inspector, "code_fragment_links", "idx_code_fragment_links_code_confidence"):
        op.create_index(
            "idx_code_fragment_links_code_confidence",
            "code_fragment_links",
            ["code_id", "confidence"],
            unique=False,
        )
    if not _has_index(inspector, "fragments", "idx_fragments_interview_paragraph"):
        op.create_index(
            "idx_fragments_interview_paragraph",
            "fragments",
            ["interview_id", "paragraph_index"],
            unique=False,
        )
    if not _has_index(inspector, "fragments", "idx_fragments_interview_created"):
        op.create_index(
            "idx_fragments_interview_created",
            "fragments",
            ["interview_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, index_name in [
        ("fragments", "idx_fragments_interview_created"),
        ("fragments", "idx_fragments_interview_paragraph"),
        ("code_fragment_links", "idx_code_fragment_links_code_confidence"),
        ("code_fragment_links", "idx_code_fragment_links_fragment_id"),
        ("code_fragment_links", "idx_code_fragment_links_code_id"),
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    if _has_column(inspector, "fragments", "end_ms"):
        op.drop_column("fragments", "end_ms")
    if _has_column(inspector, "fragments", "start_ms"):
        op.drop_column("fragments", "start_ms")
    if _has_column(inspector, "fragments", "paragraph_index"):
        op.drop_column("fragments", "paragraph_index")

    if _has_column(inspector, "code_fragment_links", "linked_at"):
        op.drop_column("code_fragment_links", "linked_at")
    if _has_column(inspector, "code_fragment_links", "source"):
        op.drop_column("code_fragment_links", "source")
    if _has_column(inspector, "code_fragment_links", "char_end"):
        op.drop_column("code_fragment_links", "char_end")
    if _has_column(inspector, "code_fragment_links", "char_start"):
        op.drop_column("code_fragment_links", "char_start")

