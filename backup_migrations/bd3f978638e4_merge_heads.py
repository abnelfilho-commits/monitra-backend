"""merge heads

Revision ID: bd3f978638e4
Revises: 0847577a7792, 55057b1ff304
Create Date: 2026-03-24 19:55:31.053047

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd3f978638e4'
down_revision: Union[str, Sequence[str], None] = ('0847577a7792', '55057b1ff304')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
