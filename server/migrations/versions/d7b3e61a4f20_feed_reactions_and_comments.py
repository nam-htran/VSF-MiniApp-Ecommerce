"""feed reactions and comments

Revision ID: d7b3e61a4f20
Revises: a1c4f2b8d3e7
Create Date: 2026-08-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7b3e61a4f20"
down_revision: Union[str, None] = "a1c4f2b8d3e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feed_reactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("reaction_type", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reaction_type IN ('LIKE', 'LOVE', 'HAHA', 'WOW', 'SAD')",
            name="ck_feed_reactions_type",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "user_id", name="uq_feed_reactions_product_user"
        ),
    )
    op.create_index(
        "ix_feed_reactions_product_id", "feed_reactions", ["product_id"]
    )
    op.create_index("ix_feed_reactions_user_id", "feed_reactions", ["user_id"])

    op.create_table(
        "feed_comments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feed_comments_product_id", "feed_comments", ["product_id"]
    )
    op.create_index("ix_feed_comments_user_id", "feed_comments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feed_comments_user_id", table_name="feed_comments")
    op.drop_index("ix_feed_comments_product_id", table_name="feed_comments")
    op.drop_table("feed_comments")
    op.drop_index("ix_feed_reactions_user_id", table_name="feed_reactions")
    op.drop_index("ix_feed_reactions_product_id", table_name="feed_reactions")
    op.drop_table("feed_reactions")
