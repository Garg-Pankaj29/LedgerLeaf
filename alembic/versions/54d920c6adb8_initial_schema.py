"""initial_schema

Revision ID: 54d920c6adb8
Revises: 
Create Date: 2026-10-15 00:28:49.095541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54d920c6adb8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.alter_column(
            'processing_status',
            existing_type=sa.VARCHAR(length=10),
            type_=sa.Enum('UPLOADED', 'PROCESSING', 'NEEDS_REVIEW', 'FAILED', 'APPROVED', name='processing_status_enum', native_enum=False),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.alter_column(
            'processing_status',
            existing_type=sa.Enum('UPLOADED', 'PROCESSING', 'NEEDS_REVIEW', 'FAILED', 'APPROVED', name='processing_status_enum', native_enum=False),
            type_=sa.VARCHAR(length=10),
            existing_nullable=False,
        )
