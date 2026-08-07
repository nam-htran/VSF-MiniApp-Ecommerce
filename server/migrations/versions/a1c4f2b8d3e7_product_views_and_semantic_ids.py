"""product views and semantic ids

Two things the recommender needs and the schema had no room for.

`product_views` is the browsing history — the `prev_items` sequence every
sequential recommender takes as input. Orders were the only behaviour the
database recorded, and a shopper looks at far more than they buy.

The `sid_*` columns carry each product's Semantic ID from the RQ-VAE. They
are nullable because they come from the model pipeline, not from the seller:
a product listed by hand simply has none, and drops out of SID recall.

Revision ID: a1c4f2b8d3e7
Revises: 9e273ea45236
Create Date: 2026-08-07 04:12:03.881204
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4f2b8d3e7'
down_revision: Union[str, None] = '9e273ea45236'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_views',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('product_id', sa.String(), nullable=False),
        sa.Column(
            'viewed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # The only read this table serves: one user's latest views, newest first.
    op.create_index(
        'ix_product_views_user_recent',
        'product_views',
        ['user_id', sa.text('viewed_at DESC')],
        unique=False,
    )

    op.add_column('products', sa.Column('sid_0', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('sid_1', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('sid_2', sa.Integer(), nullable=True))
    # Recall matches on a prefix — (sid_0), then (sid_0, sid_1), then all
    # three — so one composite index in that order serves every step.
    op.create_index(
        'ix_products_semantic_id',
        'products',
        ['sid_0', 'sid_1', 'sid_2'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_products_semantic_id', table_name='products')
    op.drop_column('products', 'sid_2')
    op.drop_column('products', 'sid_1')
    op.drop_column('products', 'sid_0')
    op.drop_index('ix_product_views_user_recent', table_name='product_views')
    op.drop_table('product_views')
