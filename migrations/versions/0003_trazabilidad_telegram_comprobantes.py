"""Añade trazabilidad Telegram y URLs cloud para comprobantes.

Revision ID: 0003_trazabilidad_telegram_comprobantes
Revises: 0002_esquema_inicial
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_telegram_comprobantes"
down_revision = "0002_esquema_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("telegram_message_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "sales",
        sa.Column("telegram_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payments", sa.Column("receipt_url", sa.String(length=1024), nullable=True))
    op.add_column(
        "payments", sa.Column("receipt_public_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "payments",
        sa.Column(
            "receipt_review_status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.add_column(
        "payments", sa.Column("telegram_message_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "payments",
        sa.Column("receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "receipt_uploaded_at")
    op.drop_column("payments", "telegram_message_id")
    op.drop_column("payments", "receipt_review_status")
    op.drop_column("payments", "receipt_public_id")
    op.drop_column("payments", "receipt_url")
    op.drop_column("sales", "telegram_notified_at")
    op.drop_column("sales", "telegram_message_id")