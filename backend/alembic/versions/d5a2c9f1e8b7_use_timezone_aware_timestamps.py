"""use timezone-aware timestamps for PostgreSQL"""

from alembic import op
import sqlalchemy as sa


revision = "d5a2c9f1e8b7"
down_revision = "372ad44c8005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, columns in {
        "exam_papers": ["created_at", "updated_at"],
        "paper_derivatives": ["created_at"],
        "metadata_resolutions": ["created_at", "updated_at"],
        "processing_logs": ["started_at", "completed_at", "last_retry_at"],
        "paper_reports": ["created_at"],
    }.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    for table, columns in {
        "exam_papers": ["created_at", "updated_at"],
        "paper_derivatives": ["created_at"],
        "metadata_resolutions": ["created_at", "updated_at"],
        "processing_logs": ["started_at", "completed_at", "last_retry_at"],
        "paper_reports": ["created_at"],
    }.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
