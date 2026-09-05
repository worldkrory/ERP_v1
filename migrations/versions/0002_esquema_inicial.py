"""Esquema inicial: las 50 tablas del ERD logico v1.0.

Generada desde app/models con generar_migracion_inicial.py, no a mano.
Para regenerarla: borra este archivo y vuelve a correr ese script.

Las tres claves foraneas del final cierran los ciclos del esquema y por eso van
separadas del CREATE TABLE:
  users.party_id -> parties
  parties.default_price_list_id -> price_lists
  batches.purchase_item_id -> purchase_items

Revision ID: 0002_esquema_inicial
Revises: 0001_extensiones
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_esquema_inicial"
down_revision = "0001_extensiones"
branch_labels = None
depends_on = None

# Las tres FK que cierran ciclos: se crean despues de todas las tablas y se
# eliminan antes de todas ellas.
FK_CICLICAS = [
    ('fk_batches_purchase_item_id_purchase_items', 'batches', 'purchase_items', 'purchase_item_id', 'id', 'SET NULL'),
    ('fk_parties_default_price_list_id_price_lists', 'parties', 'price_lists', 'default_price_list_id', 'id', 'SET NULL'),
    ('fk_users_party_id_parties', 'users', 'parties', 'party_id', 'id', 'SET NULL'),
]


def upgrade() -> None:
    op.create_table('product_categories',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('parent_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint('parent_id IS NULL OR parent_id <> id', name=op.f('ck_product_categories_no_self_parent')),
    sa.ForeignKeyConstraint(['parent_id'], ['product_categories.id'], name=op.f('fk_product_categories_parent_id_product_categories'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_product_categories')),
    sa.UniqueConstraint('code', name='uq_product_categories_code')
    )
    op.create_index('ix_product_categories_parent_id', 'product_categories', ['parent_id'], unique=False)
    op.create_table('roles',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('is_system', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('code', name='uq_roles_code')
    )
    op.create_table('taxes',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('tax_type', sa.String(length=20), nullable=False),
    sa.Column('rate', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('dian_code', sa.String(length=10), nullable=True),
    sa.Column('is_withholding', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint("tax_type IN ('INC', 'IVA', 'NONE', 'RETEFUENTE', 'RETEICA', 'RETEIVA')", name=op.f('ck_taxes_tax_type_valid')),
    sa.CheckConstraint('rate >= 0', name=op.f('ck_taxes_rate_non_negative')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_taxes_validity_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_taxes')),
    sa.UniqueConstraint('code', name='uq_taxes_code')
    )
    op.create_index('ix_taxes_tax_type', 'taxes', ['tax_type', 'valid_to'], unique=False)
    op.create_table('units_of_measure',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=15), nullable=False),
    sa.Column('name', sa.String(length=60), nullable=False),
    sa.Column('dimension', sa.String(length=20), nullable=False),
    sa.Column('is_base_for_dimension', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('decimal_places', sa.SmallInteger(), server_default='3', nullable=False),
    sa.Column('dian_code', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("dimension IN ('COUNT', 'MASS', 'TIME', 'VOLUME')", name=op.f('ck_units_of_measure_dimension_valid')),
    sa.CheckConstraint('decimal_places >= 0 AND decimal_places <= 6', name=op.f('ck_units_of_measure_decimal_places_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_units_of_measure')),
    sa.UniqueConstraint('code', name='uq_units_of_measure_code')
    )
    op.create_index('ix_units_of_measure_dimension', 'units_of_measure', ['dimension'], unique=False)
    op.create_index('uq_uom_one_base_per_dimension', 'units_of_measure', ['dimension'], unique=True, postgresql_where=sa.text('is_base_for_dimension'))
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_superuser', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_count', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name='uq_users_email')
    )
    op.create_index('ix_users_is_active', 'users', ['is_active'], unique=False)
    op.create_table('app_settings',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.Column('value_type', sa.String(length=20), nullable=False),
    sa.Column('group_name', sa.String(length=40), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_editable', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("value_type IN ('BOOLEAN', 'DATE', 'DECIMAL', 'INTEGER', 'JSON', 'STRING')", name=op.f('ck_app_settings_value_type_valid')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_app_settings_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_app_settings_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_settings')),
    sa.UniqueConstraint('key', name='uq_app_settings_key')
    )
    op.create_index('ix_app_settings_group_name', 'app_settings', ['group_name'], unique=False)
    op.create_table('cost_categories',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('parent_id', sa.BigInteger(), nullable=True),
    sa.Column('nature', sa.String(length=20), nullable=False),
    sa.Column('affects_inventory', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('allocation_basis', sa.String(length=25), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("allocation_basis IS NULL OR allocation_basis IN ('MANUAL','QUANTITY','TIME','VALUE')", name=op.f('ck_cost_categories_allocation_basis_valid')),
    sa.CheckConstraint("nature IN ('DIRECT', 'INDIRECT')", name=op.f('ck_cost_categories_nature_valid')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_cost_categories_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id'], ['cost_categories.id'], name=op.f('fk_cost_categories_parent_id_cost_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_cost_categories_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cost_categories')),
    sa.UniqueConstraint('code', name='uq_cost_categories_code')
    )
    op.create_index('ix_cost_categories_nature', 'cost_categories', ['nature'], unique=False)
    op.create_index('ix_cost_categories_parent_id', 'cost_categories', ['parent_id'], unique=False)
    op.create_table('document_sequences',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('prefix', sa.String(length=10), nullable=True),
    sa.Column('pattern', sa.String(length=40), nullable=False),
    sa.Column('next_number', sa.BigInteger(), server_default='1', nullable=False),
    sa.Column('resets_yearly', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('current_year', sa.SmallInteger(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("code IN ('EXPENSE', 'PAYMENT', 'PRODUCTION_ORDER', 'PURCHASE', 'SALE', 'SHIPMENT')", name=op.f('ck_document_sequences_code_valid')),
    sa.CheckConstraint('current_year IS NULL OR current_year >= 2000', name=op.f('ck_document_sequences_current_year_range')),
    sa.CheckConstraint('next_number >= 1', name=op.f('ck_document_sequences_next_number_min')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_document_sequences_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_document_sequences_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_document_sequences')),
    sa.UniqueConstraint('code', name='uq_document_sequences_code')
    )
    op.create_table('fiscal_resolutions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('resolution_number', sa.String(length=40), nullable=False),
    sa.Column('document_type', sa.String(length=30), nullable=False),
    sa.Column('prefix', sa.String(length=10), nullable=False),
    sa.Column('range_from', sa.BigInteger(), nullable=False),
    sa.Column('range_to', sa.BigInteger(), nullable=False),
    sa.Column('current_number', sa.BigInteger(), nullable=False),
    sa.Column('technical_key', sa.String(length=255), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=False),
    sa.Column('environment', sa.String(length=15), server_default='HABILITACION', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("document_type IN ('DOCUMENTO_SOPORTE', 'FACTURA_VENTA', 'NOMINA', 'NOTA_CREDITO', 'NOTA_DEBITO')", name=op.f('ck_fiscal_resolutions_document_type_valid')),
    sa.CheckConstraint("environment IN ('HABILITACION', 'PRODUCCION')", name=op.f('ck_fiscal_resolutions_environment_valid')),
    sa.CheckConstraint('current_number >= range_from - 1 AND current_number <= range_to', name=op.f('ck_fiscal_resolutions_current_number_in_range')),
    sa.CheckConstraint('range_to > range_from', name=op.f('ck_fiscal_resolutions_range_order')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_fiscal_resolutions_validity_range')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_fiscal_resolutions_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_fiscal_resolutions_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_fiscal_resolutions')),
    sa.UniqueConstraint('prefix', 'document_type', 'resolution_number', name='uq_fiscal_resolutions_prefix')
    )
    op.create_table('parties',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_type', sa.String(length=20), nullable=False),
    sa.Column('document_type', sa.String(length=10), nullable=False),
    sa.Column('document_number', sa.String(length=30), nullable=False),
    sa.Column('verification_digit', sa.SmallInteger(), nullable=True),
    sa.Column('legal_name', sa.String(length=200), nullable=False),
    sa.Column('trade_name', sa.String(length=200), nullable=True),
    sa.Column('first_name', sa.String(length=100), nullable=True),
    sa.Column('last_name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('whatsapp', sa.String(length=30), nullable=True),
    sa.Column('tax_regime', sa.String(length=30), nullable=True),
    sa.Column('tax_responsibilities', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('is_vat_withholding_agent', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('municipality_code', sa.String(length=5), nullable=True),
    sa.Column('department_code', sa.String(length=2), nullable=True),
    sa.Column('country_code', sa.CHAR(length=2), server_default='CO', nullable=False),
    sa.Column('credit_limit', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('payment_term_days', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('default_price_list_id', sa.BigInteger(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("document_type <> 'NIT' OR verification_digit IS NOT NULL", name=op.f('ck_parties_nit_requires_dv')),
    sa.CheckConstraint("document_type IN ('CC', 'CE', 'NIT', 'NIT_EXT', 'PAS', 'PEP', 'RC', 'TI')", name=op.f('ck_parties_document_type_valid')),
    sa.CheckConstraint("party_type <> 'NATURAL' OR (first_name IS NOT NULL AND last_name IS NOT NULL)", name=op.f('ck_parties_natural_requires_names')),
    sa.CheckConstraint("party_type IN ('JURIDICA', 'NATURAL')", name=op.f('ck_parties_party_type_valid')),
    sa.CheckConstraint("tax_regime IS NULL OR tax_regime IN ('COMUN','GRAN_CONTRIBUYENTE','NO_RESPONSABLE_IVA','REGIMEN_SIMPLE','SIMPLIFICADO')", name=op.f('ck_parties_tax_regime_valid')),
    sa.CheckConstraint('credit_limit IS NULL OR credit_limit >= 0', name=op.f('ck_parties_credit_limit_non_negative')),
    sa.CheckConstraint('payment_term_days >= 0', name=op.f('ck_parties_payment_term_non_negative')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_parties_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_parties_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parties')),
    sa.UniqueConstraint('document_type', 'document_number', name='uq_parties_document_type')
    )
    op.create_index('ix_parties_document_number', 'parties', ['document_number'], unique=False)
    op.create_index('ix_parties_is_active', 'parties', ['is_active'], unique=False)
    op.create_index('ix_parties_legal_name', 'parties', ['legal_name'], unique=False)
    op.create_table('price_lists',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('channel', sa.String(length=25), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('includes_tax', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_default', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint("channel IN ('CAFETERIA', 'EXPORT', 'INTERMEDIARY', 'INTERNAL', 'RETAIL', 'WHOLESALE')", name=op.f('ck_price_lists_channel_valid')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_price_lists_validity_range')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_price_lists_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_price_lists_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_price_lists')),
    sa.UniqueConstraint('code', name='uq_price_lists_code')
    )
    op.create_index('uq_price_lists_one_default', 'price_lists', ['channel'], unique=True, postgresql_where=sa.text('is_default AND is_active'))
    op.create_table('production_processes',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('default_sequence', sa.SmallInteger(), nullable=False),
    sa.Column('default_unit_id', sa.BigInteger(), nullable=False),
    sa.Column('yields_new_batch', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('changes_product', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('expected_yield_pct', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint('default_sequence > 0', name=op.f('ck_production_processes_sequence_positive')),
    sa.CheckConstraint('expected_yield_pct IS NULL OR (expected_yield_pct > 0 AND expected_yield_pct <= 1)', name=op.f('ck_production_processes_expected_yield_fraction')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_production_processes_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['default_unit_id'], ['units_of_measure.id'], name=op.f('fk_production_processes_default_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_production_processes_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_processes')),
    sa.UniqueConstraint('code', name='uq_production_processes_code')
    )
    op.create_index('ix_production_processes_default_sequence', 'production_processes', ['default_sequence'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('sku', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('product_kind', sa.String(length=25), nullable=False),
    sa.Column('category_id', sa.BigInteger(), nullable=True),
    sa.Column('base_unit_id', sa.BigInteger(), nullable=False),
    sa.Column('sales_unit_id', sa.BigInteger(), nullable=True),
    sa.Column('purchase_unit_id', sa.BigInteger(), nullable=True),
    sa.Column('tax_id', sa.BigInteger(), nullable=True),
    sa.Column('tracks_batches', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('costing_method', sa.String(length=25), server_default='SYSTEM_DEFAULT', nullable=False),
    sa.Column('is_sellable', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_purchasable', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_produced', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('min_stock', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('weight_kg', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('barcode', sa.String(length=50), nullable=True),
    sa.Column('image_path', sa.String(length=255), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("costing_method IN ('SPECIFIC_BATCH', 'SYSTEM_DEFAULT', 'WEIGHTED_AVERAGE')", name=op.f('ck_products_costing_method_valid')),
    sa.CheckConstraint("product_kind IN ('FINISHED', 'RAW_MATERIAL', 'SEMI_FINISHED', 'SERVICE', 'SUPPLY')", name=op.f('ck_products_product_kind_valid')),
    sa.CheckConstraint("tracks_batches = FALSE OR product_kind <> 'SERVICE'", name=op.f('ck_products_service_without_batches')),
    sa.CheckConstraint('is_sellable OR is_purchasable OR is_produced', name=op.f('ck_products_at_least_one_usage')),
    sa.CheckConstraint('min_stock IS NULL OR min_stock >= 0', name=op.f('ck_products_min_stock_non_negative')),
    sa.CheckConstraint('weight_kg IS NULL OR weight_kg >= 0', name=op.f('ck_products_weight_non_negative')),
    sa.ForeignKeyConstraint(['base_unit_id'], ['units_of_measure.id'], name=op.f('fk_products_base_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_id'], ['product_categories.id'], name=op.f('fk_products_category_id_product_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_products_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['purchase_unit_id'], ['units_of_measure.id'], name=op.f('fk_products_purchase_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sales_unit_id'], ['units_of_measure.id'], name=op.f('fk_products_sales_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['tax_id'], ['taxes.id'], name=op.f('fk_products_tax_id_taxes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_products_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_products')),
    sa.UniqueConstraint('sku', name='uq_products_sku')
    )
    op.create_index('ix_products_is_active', 'products', ['is_active'], unique=False)
    op.create_index('ix_products_product_kind', 'products', ['product_kind'], unique=False)
    op.create_index('ix_products_sku', 'products', ['sku'], unique=False)
    op.create_index('uq_products_barcode', 'products', ['barcode'], unique=True, postgresql_where=sa.text('barcode IS NOT NULL'))
    op.create_table('user_roles',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('role_id', sa.BigInteger(), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('assigned_by_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['assigned_by_id'], ['users.id'], name=op.f('fk_user_roles_assigned_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_user_roles_role_id_roles'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_roles_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_roles')),
    sa.UniqueConstraint('user_id', 'role_id', name='uq_user_roles_user_id')
    )
    op.create_table('addresses',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('label', sa.String(length=60), nullable=True),
    sa.Column('address_type', sa.String(length=20), server_default='BOTH', nullable=False),
    sa.Column('address_line', sa.String(length=255), nullable=False),
    sa.Column('address_line_2', sa.String(length=255), nullable=True),
    sa.Column('municipality_code', sa.String(length=5), nullable=True),
    sa.Column('municipality_name', sa.String(length=100), nullable=False),
    sa.Column('department_code', sa.String(length=2), nullable=True),
    sa.Column('department_name', sa.String(length=100), nullable=False),
    sa.Column('country_code', sa.CHAR(length=2), server_default='CO', nullable=False),
    sa.Column('postal_code', sa.String(length=10), nullable=True),
    sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("address_type IN ('BILLING', 'BOTH', 'FARM', 'SHIPPING')", name=op.f('ck_addresses_address_type_valid')),
    sa.CheckConstraint('latitude IS NULL OR (latitude >= -90 AND latitude <= 90)', name=op.f('ck_addresses_latitude_range')),
    sa.CheckConstraint('longitude IS NULL OR (longitude >= -180 AND longitude <= 180)', name=op.f('ck_addresses_longitude_range')),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_addresses_party_id_parties'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_addresses'))
    )
    op.create_index('ix_addresses_party_id', 'addresses', ['party_id'], unique=False)
    op.create_index('uq_addresses_one_primary', 'addresses', ['party_id'], unique=True, postgresql_where=sa.text('is_primary'))
    op.create_table('coffee_profiles',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('variety', sa.String(length=80), nullable=True),
    sa.Column('process_method', sa.String(length=30), nullable=True),
    sa.Column('roast_level', sa.String(length=20), nullable=True),
    sa.Column('grind_type', sa.String(length=20), nullable=True),
    sa.Column('altitude_min_masl', sa.Integer(), nullable=True),
    sa.Column('altitude_max_masl', sa.Integer(), nullable=True),
    sa.Column('cupping_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('sensory_notes', sa.Text(), nullable=True),
    sa.Column('packaging_grams', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("grind_type IS NULL OR grind_type IN ('EXPRESO','FINO','GRANO','GRUESO','MEDIO')", name=op.f('ck_coffee_profiles_grind_type_valid')),
    sa.CheckConstraint("process_method IS NULL OR process_method IN ('ANAEROBICO','HONEY','LAVADO','NATURAL','OTRO')", name=op.f('ck_coffee_profiles_process_method_valid')),
    sa.CheckConstraint("roast_level IS NULL OR roast_level IN ('CLARO','MEDIO','MEDIO_OSCURO','OSCURO')", name=op.f('ck_coffee_profiles_roast_level_valid')),
    sa.CheckConstraint('altitude_min_masl IS NULL OR altitude_max_masl IS NULL OR altitude_max_masl >= altitude_min_masl', name=op.f('ck_coffee_profiles_altitude_range')),
    sa.CheckConstraint('cupping_score IS NULL OR (cupping_score >= 0 AND cupping_score <= 100)', name=op.f('ck_coffee_profiles_cupping_score_range')),
    sa.CheckConstraint('packaging_grams IS NULL OR packaging_grams > 0', name=op.f('ck_coffee_profiles_packaging_positive')),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_coffee_profiles_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_coffee_profiles')),
    sa.UniqueConstraint('product_id', name='uq_coffee_profiles_product_id')
    )
    op.create_table('cost_rules',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('cost_category_id', sa.BigInteger(), nullable=False),
    sa.Column('applies_to', sa.String(length=30), nullable=False),
    sa.Column('process_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('executor_type', sa.String(length=20), nullable=True),
    sa.Column('executor_party_id', sa.BigInteger(), nullable=True),
    sa.Column('calculation_basis', sa.String(length=30), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=True),
    sa.Column('rate', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('min_charge', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('max_charge', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('min_quantity', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('priority', sa.SmallInteger(), server_default='100', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    postgresql.ExcludeConstraint((sa.column('process_id'), '='), (sa.column('executor_party_id'), '='), (sa.column('product_id'), '='), (sa.text("daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]')"), '&&'), using='gist', name='cost_rules_no_overlap'),
    sa.CheckConstraint("applies_to <> 'PROCESS' OR process_id IS NOT NULL", name=op.f('ck_cost_rules_process_required')),
    sa.CheckConstraint("applies_to IN ('ORDER', 'PROCESS', 'PRODUCT', 'SALE', 'SHIPMENT')", name=op.f('ck_cost_rules_applies_to_valid')),
    sa.CheckConstraint("calculation_basis IN ('FLAT', 'PCT_OF_INPUT_COST', 'PER_HOUR', 'PER_UNIT_INPUT', 'PER_UNIT_OUTPUT')", name=op.f('ck_cost_rules_calculation_basis_valid')),
    sa.CheckConstraint("calculation_basis IN ('FLAT','PCT_OF_INPUT_COST') OR unit_id IS NOT NULL", name=op.f('ck_cost_rules_unit_required')),
    sa.CheckConstraint("executor_type IS NULL OR executor_type IN ('EXTERNAL','INTERNAL')", name=op.f('ck_cost_rules_executor_type_valid')),
    sa.CheckConstraint('max_charge IS NULL OR min_charge IS NULL OR max_charge >= min_charge', name=op.f('ck_cost_rules_charge_range')),
    sa.CheckConstraint('min_quantity IS NULL OR min_quantity > 0', name=op.f('ck_cost_rules_min_quantity_positive')),
    sa.CheckConstraint('rate >= 0', name=op.f('ck_cost_rules_rate_non_negative')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_cost_rules_validity_range')),
    sa.ForeignKeyConstraint(['cost_category_id'], ['cost_categories.id'], name=op.f('fk_cost_rules_cost_category_id_cost_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_cost_rules_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['executor_party_id'], ['parties.id'], name=op.f('fk_cost_rules_executor_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['process_id'], ['production_processes.id'], name=op.f('fk_cost_rules_process_id_production_processes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_cost_rules_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_cost_rules_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_cost_rules_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cost_rules')),
    sa.UniqueConstraint('code', name='uq_cost_rules_code')
    )
    op.create_index('ix_cost_rules_executor', 'cost_rules', ['executor_party_id'], unique=False)
    op.create_index('ix_cost_rules_lookup', 'cost_rules', ['applies_to', 'process_id', 'valid_from', 'valid_to'], unique=False)
    op.create_table('expense_categories',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('parent_id', sa.BigInteger(), nullable=True),
    sa.Column('expense_nature', sa.String(length=25), nullable=False),
    sa.Column('is_cost_of_sales', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('default_cost_category_id', sa.BigInteger(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("expense_nature IN ('ADMINISTRATIVE', 'FINANCIAL', 'OPERATIONAL', 'OTHER', 'SALES', 'TAX')", name=op.f('ck_expense_categories_expense_nature_valid')),
    sa.CheckConstraint('parent_id IS NULL OR parent_id <> id', name=op.f('ck_expense_categories_no_self_parent')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_expense_categories_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['default_cost_category_id'], ['cost_categories.id'], name=op.f('fk_expense_categories_default_cost_category_id_cost_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id'], ['expense_categories.id'], name=op.f('fk_expense_categories_parent_id_expense_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_expense_categories_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_expense_categories')),
    sa.UniqueConstraint('code', name='uq_expense_categories_code')
    )
    op.create_index('ix_expense_categories_parent_id', 'expense_categories', ['parent_id'], unique=False)
    op.create_table('intermediary_fee_rules',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('calculation_basis', sa.String(length=25), nullable=False),
    sa.Column('value', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('category_id', sa.BigInteger(), nullable=True),
    sa.Column('min_fee_amount', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('max_fee_amount', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('priority', sa.SmallInteger(), server_default='100', nullable=False),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint("calculation_basis <> 'PER_UNIT' OR unit_id IS NOT NULL", name=op.f('ck_intermediary_fee_rules_per_unit_requires_unit')),
    sa.CheckConstraint("calculation_basis IN ('FLAT_PER_SALE', 'PCT_OF_MARGIN', 'PCT_OF_SALE_TOTAL', 'PER_UNIT')", name=op.f('ck_intermediary_fee_rules_calculation_basis_valid')),
    sa.CheckConstraint("calculation_basis NOT LIKE 'PCT%%' OR value <= 1", name=op.f('ck_intermediary_fee_rules_pct_fraction')),
    sa.CheckConstraint('max_fee_amount IS NULL OR min_fee_amount IS NULL OR max_fee_amount >= min_fee_amount', name=op.f('ck_intermediary_fee_rules_fee_amount_range')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_intermediary_fee_rules_validity_range')),
    sa.CheckConstraint('value >= 0', name=op.f('ck_intermediary_fee_rules_value_non_negative')),
    sa.ForeignKeyConstraint(['category_id'], ['product_categories.id'], name=op.f('fk_intermediary_fee_rules_category_id_product_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_intermediary_fee_rules_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_intermediary_fee_rules_party_id_parties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_intermediary_fee_rules_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_intermediary_fee_rules_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_intermediary_fee_rules_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intermediary_fee_rules'))
    )
    op.create_index('ix_intermediary_fee_rules_party_id', 'intermediary_fee_rules', ['party_id', 'priority', 'valid_to'], unique=False)
    op.create_table('party_contacts',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('position', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_party_contacts_party_id_parties'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_party_contacts'))
    )
    op.create_index('ix_party_contacts_party_id', 'party_contacts', ['party_id'], unique=False)
    op.create_index('uq_party_contacts_one_primary', 'party_contacts', ['party_id'], unique=True, postgresql_where=sa.text('is_primary'))
    op.create_table('party_price_rules',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('rule_type', sa.String(length=25), nullable=False),
    sa.Column('price_list_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('category_id', sa.BigInteger(), nullable=True),
    sa.Column('unit_id', sa.BigInteger(), nullable=True),
    sa.Column('value', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('min_quantity', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('priority', sa.SmallInteger(), server_default='100', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint("rule_type <> 'DISCOUNT_PCT' OR (value >= 0 AND value <= 1)", name=op.f('ck_party_price_rules_discount_pct_fraction')),
    sa.CheckConstraint("rule_type <> 'FIXED_PRICE' OR (value IS NOT NULL AND unit_id IS NOT NULL)", name=op.f('ck_party_price_rules_fixed_price_requires_value_unit')),
    sa.CheckConstraint("rule_type <> 'LIST_ASSIGNMENT' OR price_list_id IS NOT NULL", name=op.f('ck_party_price_rules_list_assignment_requires_list')),
    sa.CheckConstraint("rule_type IN ('DISCOUNT_AMOUNT', 'DISCOUNT_PCT', 'FIXED_PRICE', 'LIST_ASSIGNMENT')", name=op.f('ck_party_price_rules_rule_type_valid')),
    sa.CheckConstraint("rule_type NOT IN ('DISCOUNT_PCT','DISCOUNT_AMOUNT') OR value IS NOT NULL", name=op.f('ck_party_price_rules_discount_requires_value')),
    sa.CheckConstraint('min_quantity >= 0', name=op.f('ck_party_price_rules_min_quantity_non_negative')),
    sa.CheckConstraint('product_id IS NULL OR category_id IS NULL', name=op.f('ck_party_price_rules_product_xor_category')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_party_price_rules_validity_range')),
    sa.ForeignKeyConstraint(['category_id'], ['product_categories.id'], name=op.f('fk_party_price_rules_category_id_product_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_party_price_rules_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_party_price_rules_party_id_parties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['price_list_id'], ['price_lists.id'], name=op.f('fk_party_price_rules_price_list_id_price_lists'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_party_price_rules_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_party_price_rules_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_party_price_rules_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_party_price_rules'))
    )
    op.create_index('ix_party_price_rules_party_id', 'party_price_rules', ['party_id', 'rule_type', 'priority'], unique=False)
    op.create_table('party_roles',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('role_code', sa.String(length=30), nullable=False),
    sa.Column('valid_from', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.CheckConstraint("role_code IN ('CAFETERIA', 'CARRIER', 'COFFEE_GROWER', 'CUSTOMER', 'EMPLOYEE', 'INTERMEDIARY', 'PROCESSOR', 'SUPPLIER')", name=op.f('ck_party_roles_role_code_valid')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_party_roles_validity_range')),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_party_roles_party_id_parties'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_party_roles')),
    sa.UniqueConstraint('party_id', 'role_code', 'valid_from', name='uq_party_roles_party_id')
    )
    op.create_index('ix_party_roles_role_code', 'party_roles', ['role_code', 'valid_to'], unique=False)
    op.create_table('payments',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('payment_number', sa.String(length=30), nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('direction', sa.String(length=15), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=False),
    sa.Column('method', sa.String(length=25), nullable=False),
    sa.Column('amount', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('allocated_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('unallocated_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='CONFIRMED', nullable=False),
    sa.Column('reference', sa.String(length=80), nullable=True),
    sa.Column('bank_account', sa.String(length=60), nullable=True),
    sa.Column('receipt_path', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("direction IN ('INBOUND', 'OUTBOUND')", name=op.f('ck_payments_direction_valid')),
    sa.CheckConstraint("method IN ('CHEQUE', 'CREDITO', 'DAVIPLATA', 'EFECTIVO', 'NEQUI', 'OTRO', 'PSE', 'TARJETA', 'TRANSFERENCIA')", name=op.f('ck_payments_method_valid')),
    sa.CheckConstraint("status IN ('CONFIRMED', 'PENDING', 'REVERSED')", name=op.f('ck_payments_status_valid')),
    sa.CheckConstraint('allocated_amount >= 0', name=op.f('ck_payments_allocated_non_negative')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_payments_amount_positive')),
    sa.CheckConstraint('unallocated_amount >= 0', name=op.f('ck_payments_unallocated_non_negative')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_payments_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_payments_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_payments_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('payment_number', name='uq_payments_payment_number')
    )
    op.create_index('ix_payments_party', 'payments', ['party_id', sa.literal_column('payment_date DESC')], unique=False)
    op.create_index('ix_payments_status', 'payments', ['status'], unique=False)
    op.create_table('price_list_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('price_list_id', sa.BigInteger(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('min_quantity', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('max_quantity', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True),
    postgresql.ExcludeConstraint((sa.column('price_list_id'), '='), (sa.column('product_id'), '='), (sa.column('unit_id'), '='), (sa.text("numrange(min_quantity, COALESCE(max_quantity, 'infinity'::numeric), '[]')"), '&&'), (sa.text("daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]')"), '&&'), using='gist', name='price_list_items_no_overlap'),
    sa.CheckConstraint('max_quantity IS NULL OR max_quantity >= min_quantity', name=op.f('ck_price_list_items_quantity_range')),
    sa.CheckConstraint('min_quantity >= 0', name=op.f('ck_price_list_items_min_quantity_non_negative')),
    sa.CheckConstraint('unit_price >= 0', name=op.f('ck_price_list_items_unit_price_non_negative')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_price_list_items_validity_range')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_price_list_items_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['price_list_id'], ['price_lists.id'], name=op.f('fk_price_list_items_price_list_id_price_lists'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_price_list_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_price_list_items_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_price_list_items_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_price_list_items'))
    )
    op.create_index('ix_price_list_items_lookup', 'price_list_items', ['price_list_id', 'product_id', 'valid_from', 'valid_to'], unique=False)
    op.create_table('production_orders',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('order_number', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='DRAFT', nullable=False),
    sa.Column('target_product_id', sa.BigInteger(), nullable=True),
    sa.Column('planned_quantity', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('unit_id', sa.BigInteger(), nullable=True),
    sa.Column('planned_start_date', sa.Date(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('total_input_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total_process_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total_overhead_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('output_quantity_base', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('waste_quantity_base', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('yield_pct', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('CANCELLED', 'CLOSED', 'COMPLETED', 'DRAFT', 'IN_PROGRESS', 'RELEASED')", name=op.f('ck_production_orders_status_valid')),
    sa.CheckConstraint('completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at', name=op.f('ck_production_orders_dates_order')),
    sa.CheckConstraint('output_quantity_base >= 0', name=op.f('ck_production_orders_output_quantity_base_non_negative')),
    sa.CheckConstraint('planned_quantity IS NULL OR planned_quantity > 0', name=op.f('ck_production_orders_planned_quantity_positive')),
    sa.CheckConstraint('total_cost >= 0', name=op.f('ck_production_orders_total_cost_non_negative')),
    sa.CheckConstraint('total_input_cost >= 0', name=op.f('ck_production_orders_total_input_cost_non_negative')),
    sa.CheckConstraint('total_overhead_cost >= 0', name=op.f('ck_production_orders_total_overhead_cost_non_negative')),
    sa.CheckConstraint('total_process_cost >= 0', name=op.f('ck_production_orders_total_process_cost_non_negative')),
    sa.CheckConstraint('waste_quantity_base >= 0', name=op.f('ck_production_orders_waste_quantity_base_non_negative')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_production_orders_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['target_product_id'], ['products.id'], name=op.f('fk_production_orders_target_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_production_orders_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_production_orders_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_orders')),
    sa.UniqueConstraint('order_number', name='uq_production_orders_order_number')
    )
    op.create_index('ix_production_orders_dates', 'production_orders', ['started_at', 'completed_at'], unique=False)
    op.create_index('ix_production_orders_status', 'production_orders', ['status'], unique=False)
    op.create_table('unit_conversions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('from_unit_id', sa.BigInteger(), nullable=False),
    sa.Column('to_unit_id', sa.BigInteger(), nullable=False),
    sa.Column('factor', sa.Numeric(precision=20, scale=10), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint('factor > 0', name=op.f('ck_unit_conversions_factor_positive')),
    sa.CheckConstraint('from_unit_id <> to_unit_id', name=op.f('ck_unit_conversions_distinct_units')),
    sa.ForeignKeyConstraint(['from_unit_id'], ['units_of_measure.id'], name=op.f('fk_unit_conversions_from_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_unit_conversions_product_id_products'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['to_unit_id'], ['units_of_measure.id'], name=op.f('fk_unit_conversions_to_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_unit_conversions')),
    sa.UniqueConstraint('from_unit_id', 'to_unit_id', 'product_id', name='uq_unit_conversions_from_unit_id')
    )
    op.create_index('ix_unit_conversions_product_id', 'unit_conversions', ['product_id'], unique=False)
    op.create_index('uq_unit_conversions_universal', 'unit_conversions', ['from_unit_id', 'to_unit_id'], unique=True, postgresql_where=sa.text('product_id IS NULL'))
    op.create_table('batches',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('batch_code', sa.String(length=40), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_type', sa.String(length=25), nullable=False),
    sa.Column('origin_party_id', sa.BigInteger(), nullable=True),
    sa.Column('origin_address_id', sa.BigInteger(), nullable=True),
    sa.Column('farm_name', sa.String(length=150), nullable=True),
    sa.Column('municipality_name', sa.String(length=100), nullable=True),
    sa.Column('harvest_year', sa.SmallInteger(), nullable=True),
    sa.Column('harvest_period', sa.String(length=20), nullable=True),
    sa.Column('production_order_id', sa.BigInteger(), nullable=True),
    sa.Column('purchase_item_id', sa.BigInteger(), nullable=True),
    sa.Column('initial_quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('humidity_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('defect_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('cupping_score', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('received_date', sa.Date(), nullable=True),
    sa.Column('production_date', sa.Date(), nullable=True),
    sa.Column('expiry_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
    sa.Column('quality_notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("batch_type <> 'PRODUCED' OR production_order_id IS NOT NULL", name=op.f('ck_batches_produced_requires_order')),
    sa.CheckConstraint("batch_type IN ('ADJUSTED', 'PRODUCED', 'PURCHASED')", name=op.f('ck_batches_batch_type_valid')),
    sa.CheckConstraint("harvest_period IS NULL OR harvest_period IN ('PRINCIPAL','TRAVIESA')", name=op.f('ck_batches_harvest_period_valid')),
    sa.CheckConstraint("status IN ('ACTIVE', 'BLOCKED', 'DEPLETED', 'EXPIRED')", name=op.f('ck_batches_status_valid')),
    sa.CheckConstraint('defect_pct IS NULL OR (defect_pct >= 0 AND defect_pct <= 100)', name=op.f('ck_batches_defect_pct_range')),
    sa.CheckConstraint('expiry_date IS NULL OR production_date IS NULL OR expiry_date >= production_date', name=op.f('ck_batches_expiry_after_production')),
    sa.CheckConstraint('humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)', name=op.f('ck_batches_humidity_pct_range')),
    sa.CheckConstraint('initial_quantity > 0', name=op.f('ck_batches_initial_quantity_positive')),
    sa.CheckConstraint('unit_cost >= 0', name=op.f('ck_batches_unit_cost_non_negative')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_batches_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['origin_address_id'], ['addresses.id'], name=op.f('fk_batches_origin_address_id_addresses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['origin_party_id'], ['parties.id'], name=op.f('fk_batches_origin_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_batches_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], name=op.f('fk_batches_production_order_id_production_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_batches_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_batches_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_batches')),
    sa.UniqueConstraint('batch_code', name='uq_batches_batch_code')
    )
    op.create_index('ix_batches_harvest_year', 'batches', ['harvest_year'], unique=False)
    op.create_index('ix_batches_origin_party', 'batches', ['origin_party_id'], unique=False)
    op.create_index('ix_batches_product', 'batches', ['product_id', 'status'], unique=False)
    op.create_table('expenses',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('expense_number', sa.String(length=30), nullable=False),
    sa.Column('category_id', sa.BigInteger(), nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=True),
    sa.Column('expense_date', sa.Date(), nullable=False),
    sa.Column('accounting_date', sa.Date(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('withholding_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('payment_method', sa.String(length=25), nullable=True),
    sa.Column('payment_status', sa.String(length=20), server_default='UNPAID', nullable=False),
    sa.Column('document_type', sa.String(length=30), nullable=True),
    sa.Column('document_number', sa.String(length=40), nullable=True),
    sa.Column('is_capitalizable', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_recurring', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('attachment_path', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("document_type IS NULL OR document_type IN ('DOCUMENTO_SOPORTE','FACTURA','NINGUNO','NOMINA','RECIBO')", name=op.f('ck_expenses_document_type_valid')),
    sa.CheckConstraint("payment_method IS NULL OR payment_method IN ('CHEQUE','CREDITO','DAVIPLATA','EFECTIVO','NEQUI','OTRO','PSE','TARJETA','TRANSFERENCIA')", name=op.f('ck_expenses_payment_method_valid')),
    sa.CheckConstraint("payment_status IN ('PAID', 'PARTIAL', 'UNPAID')", name=op.f('ck_expenses_payment_status_valid')),
    sa.CheckConstraint('subtotal >= 0', name=op.f('ck_expenses_subtotal_non_negative')),
    sa.CheckConstraint('tax_amount >= 0', name=op.f('ck_expenses_tax_amount_non_negative')),
    sa.CheckConstraint('withholding_amount >= 0', name=op.f('ck_expenses_withholding_non_negative')),
    sa.ForeignKeyConstraint(['category_id'], ['expense_categories.id'], name=op.f('fk_expenses_category_id_expense_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_expenses_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_expenses_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_expenses_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_expenses')),
    sa.UniqueConstraint('expense_number', name='uq_expenses_expense_number')
    )
    op.create_index('ix_expenses_accounting_date', 'expenses', [sa.literal_column('accounting_date DESC')], unique=False)
    op.create_index('ix_expenses_category_date', 'expenses', ['category_id', 'accounting_date'], unique=False)
    op.create_index('ix_expenses_party', 'expenses', ['party_id'], unique=False)
    op.create_table('inventory_locations',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('location_type', sa.String(length=30), nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=True),
    sa.Column('address_id', sa.BigInteger(), nullable=True),
    sa.Column('allows_negative_stock', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.CheckConstraint("location_type IN ('CONSIGNMENT', 'CUSTOMER', 'IN_TRANSIT', 'PROCESSOR', 'SCRAP', 'VIRTUAL', 'WAREHOUSE')", name=op.f('ck_inventory_locations_location_type_valid')),
    sa.CheckConstraint("location_type NOT IN ('PROCESSOR','CONSIGNMENT') OR party_id IS NOT NULL", name=op.f('ck_inventory_locations_third_party_requires_party')),
    sa.ForeignKeyConstraint(['address_id'], ['addresses.id'], name=op.f('fk_inventory_locations_address_id_addresses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_inventory_locations_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_inventory_locations_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_inventory_locations_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_locations')),
    sa.UniqueConstraint('code', name='uq_inventory_locations_code')
    )
    op.create_index('ix_inventory_locations_location_type', 'inventory_locations', ['location_type'], unique=False)
    op.create_index('ix_inventory_locations_party_id', 'inventory_locations', ['party_id'], unique=False)
    op.create_table('payment_allocations',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('payment_id', sa.BigInteger(), nullable=False),
    sa.Column('target_type', sa.String(length=20), nullable=False),
    sa.Column('target_id', sa.BigInteger(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('allocated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("target_type IN ('EXPENSE', 'FEE', 'INVOICE', 'PURCHASE', 'SALE')", name=op.f('ck_payment_allocations_target_type_valid')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_payment_allocations_amount_positive')),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name=op.f('fk_payment_allocations_payment_id_payments'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_allocations')),
    sa.UniqueConstraint('payment_id', 'target_type', 'target_id', name='uq_payment_allocations_payment_id')
    )
    op.create_index('ix_payment_allocations_target', 'payment_allocations', ['target_type', 'target_id'], unique=False)
    op.create_table('sales',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('sale_number', sa.String(length=30), nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('channel', sa.String(length=25), nullable=False),
    sa.Column('intermediary_party_id', sa.BigInteger(), nullable=True),
    sa.Column('price_list_id', sa.BigInteger(), nullable=True),
    sa.Column('salesperson_user_id', sa.BigInteger(), nullable=True),
    sa.Column('sale_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='DRAFT', nullable=False),
    sa.Column('payment_status', sa.String(length=20), server_default='UNPAID', nullable=False),
    sa.Column('payment_term_days', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('discount_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('tax_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('paid_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('cost_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('margin_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('margin_pct', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('freight_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('shipping_address_id', sa.BigInteger(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_reason', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('CAFETERIA', 'EVENT', 'INTERMEDIARY', 'ONLINE', 'RETAIL', 'WHOLESALE')", name=op.f('ck_sales_channel_valid')),
    sa.CheckConstraint("payment_status IN ('OVERDUE', 'PAID', 'PARTIAL', 'UNPAID')", name=op.f('ck_sales_payment_status_valid')),
    sa.CheckConstraint("status <> 'CANCELLED' OR cancelled_at IS NOT NULL", name=op.f('ck_sales_cancelled_requires_timestamp')),
    sa.CheckConstraint("status IN ('CANCELLED', 'CONFIRMED', 'DELIVERED', 'DISPATCHED', 'DRAFT', 'RETURNED')", name=op.f('ck_sales_status_valid')),
    sa.CheckConstraint('intermediary_party_id IS NULL OR intermediary_party_id <> party_id', name=op.f('ck_sales_intermediary_not_customer')),
    sa.CheckConstraint('payment_term_days >= 0', name=op.f('ck_sales_payment_term_non_negative')),
    sa.CheckConstraint('total >= 0', name=op.f('ck_sales_total_non_negative')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_sales_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['intermediary_party_id'], ['parties.id'], name=op.f('fk_sales_intermediary_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_sales_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['price_list_id'], ['price_lists.id'], name=op.f('fk_sales_price_list_id_price_lists'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['salesperson_user_id'], ['users.id'], name=op.f('fk_sales_salesperson_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['shipping_address_id'], ['addresses.id'], name=op.f('fk_sales_shipping_address_id_addresses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_sales_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sales')),
    sa.UniqueConstraint('sale_number', name='uq_sales_sale_number')
    )
    op.create_index('ix_sales_channel', 'sales', ['channel', 'sale_date'], unique=False)
    op.create_index('ix_sales_date', 'sales', [sa.literal_column('sale_date DESC')], unique=False)
    op.create_index('ix_sales_party_date', 'sales', ['party_id', sa.literal_column('sale_date DESC')], unique=False)
    op.create_index('ix_sales_payment_status', 'sales', ['payment_status', 'due_date'], unique=False)
    op.create_index('ix_sales_status', 'sales', ['status'], unique=False)
    op.create_table('batch_lineage',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('child_batch_id', sa.BigInteger(), nullable=False),
    sa.Column('parent_batch_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_consumed', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('contribution_pct', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('production_order_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('child_batch_id <> parent_batch_id', name=op.f('ck_batch_lineage_no_self_parent')),
    sa.CheckConstraint('contribution_pct IS NULL OR (contribution_pct >= 0 AND contribution_pct <= 1)', name=op.f('ck_batch_lineage_contribution_pct_fraction')),
    sa.CheckConstraint('quantity_consumed > 0', name=op.f('ck_batch_lineage_quantity_consumed_positive')),
    sa.ForeignKeyConstraint(['child_batch_id'], ['batches.id'], name=op.f('fk_batch_lineage_child_batch_id_batches'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_batch_id'], ['batches.id'], name=op.f('fk_batch_lineage_parent_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], name=op.f('fk_batch_lineage_production_order_id_production_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_batch_lineage_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_batch_lineage')),
    sa.UniqueConstraint('child_batch_id', 'parent_batch_id', name='uq_batch_lineage_child_batch_id')
    )
    op.create_index('ix_batch_lineage_child_batch_id', 'batch_lineage', ['child_batch_id'], unique=False)
    op.create_index('ix_batch_lineage_parent_batch_id', 'batch_lineage', ['parent_batch_id'], unique=False)
    op.create_table('cost_entries',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('cost_category_id', sa.BigInteger(), nullable=False),
    sa.Column('cost_rule_id', sa.BigInteger(), nullable=True),
    sa.Column('cost_object_type', sa.String(length=30), nullable=False),
    sa.Column('cost_object_id', sa.BigInteger(), nullable=True),
    sa.Column('amount', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('unit_id', sa.BigInteger(), nullable=True),
    sa.Column('unit_rate', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('calculation_basis', sa.String(length=30), nullable=True),
    sa.Column('party_id', sa.BigInteger(), nullable=True),
    sa.Column('incurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accounting_date', sa.Date(), nullable=False),
    sa.Column('is_estimated', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('expense_id', sa.BigInteger(), nullable=True),
    sa.Column('reverses_entry_id', sa.BigInteger(), nullable=True),
    sa.Column('document_reference', sa.String(length=60), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("calculation_basis IS NULL OR calculation_basis IN ('FLAT','PCT_OF_INPUT_COST','PER_HOUR','PER_UNIT_INPUT','PER_UNIT_OUTPUT')", name=op.f('ck_cost_entries_calculation_basis_valid')),
    sa.CheckConstraint("cost_object_id IS NOT NULL OR cost_object_type = 'PERIOD'", name=op.f('ck_cost_entries_object_id_required')),
    sa.CheckConstraint("cost_object_type IN ('BATCH', 'PARTY', 'PERIOD', 'PROCESS_EXECUTION', 'PRODUCT', 'PRODUCTION_ORDER', 'PURCHASE', 'SALE', 'SALE_ITEM', 'SHIPMENT')", name=op.f('ck_cost_entries_cost_object_type_valid')),
    sa.CheckConstraint('amount <> 0', name=op.f('ck_cost_entries_amount_non_zero')),
    sa.CheckConstraint('quantity IS NULL OR quantity > 0', name=op.f('ck_cost_entries_quantity_positive')),
    sa.CheckConstraint('reverses_entry_id IS NULL OR reverses_entry_id <> id', name=op.f('ck_cost_entries_no_self_reversal')),
    sa.ForeignKeyConstraint(['cost_category_id'], ['cost_categories.id'], name=op.f('fk_cost_entries_cost_category_id_cost_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['cost_rule_id'], ['cost_rules.id'], name=op.f('fk_cost_entries_cost_rule_id_cost_rules'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_cost_entries_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], name=op.f('fk_cost_entries_expense_id_expenses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_cost_entries_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reverses_entry_id'], ['cost_entries.id'], name=op.f('fk_cost_entries_reverses_entry_id_cost_entries'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_cost_entries_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_cost_entries_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cost_entries'))
    )
    op.create_index('ix_cost_entries_accounting', 'cost_entries', ['accounting_date'], unique=False)
    op.create_index('ix_cost_entries_category', 'cost_entries', ['cost_category_id', 'accounting_date'], unique=False)
    op.create_index('ix_cost_entries_object', 'cost_entries', ['cost_object_type', 'cost_object_id'], unique=False)
    op.create_index('ix_cost_entries_party', 'cost_entries', ['party_id'], unique=False)
    op.create_table('intermediary_fee_entries',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('sale_id', sa.BigInteger(), nullable=False),
    sa.Column('rule_id', sa.BigInteger(), nullable=True),
    sa.Column('calculation_basis', sa.String(length=25), nullable=False),
    sa.Column('rule_value', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('base_amount', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('fee_amount', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('status', sa.String(length=20), server_default='ACCRUED', nullable=False),
    sa.Column('accrued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expense_id', sa.BigInteger(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("calculation_basis IN ('FLAT_PER_SALE', 'PCT_OF_MARGIN', 'PCT_OF_SALE_TOTAL', 'PER_UNIT')", name=op.f('ck_intermediary_fee_entries_calculation_basis_valid')),
    sa.CheckConstraint("status IN ('ACCRUED', 'APPROVED', 'CANCELLED', 'PAID')", name=op.f('ck_intermediary_fee_entries_status_valid')),
    sa.CheckConstraint('fee_amount >= 0', name=op.f('ck_intermediary_fee_entries_fee_amount_non_negative')),
    sa.CheckConstraint('settled_at IS NULL OR settled_at >= accrued_at', name=op.f('ck_intermediary_fee_entries_settled_after_accrued')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_intermediary_fee_entries_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['expense_id'], ['expenses.id'], name=op.f('fk_intermediary_fee_entries_expense_id_expenses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_intermediary_fee_entries_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rule_id'], ['intermediary_fee_rules.id'], name=op.f('fk_intermediary_fee_entries_rule_id_intermediary_fee_rules'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], name=op.f('fk_intermediary_fee_entries_sale_id_sales'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_intermediary_fee_entries_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intermediary_fee_entries'))
    )
    op.create_index('ix_ife_party_status', 'intermediary_fee_entries', ['party_id', 'status'], unique=False)
    op.create_index('ix_ife_sale', 'intermediary_fee_entries', ['sale_id'], unique=False)
    op.create_table('inventory_movements',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('movement_type', sa.String(length=35), nullable=False),
    sa.Column('direction', sa.SmallInteger(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('location_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('total_cost', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reference_type', sa.String(length=30), nullable=True),
    sa.Column('reference_id', sa.BigInteger(), nullable=True),
    sa.Column('counterpart_movement_id', sa.BigInteger(), nullable=True),
    sa.Column('reverses_movement_id', sa.BigInteger(), nullable=True),
    sa.Column('reason_code', sa.String(length=30), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("(movement_type IN ('IN_ADJUSTMENT', 'IN_PRODUCTION', 'IN_PURCHASE', 'IN_SALE_RETURN', 'IN_TRANSFER', 'IN_WASTE_RECOVERY') AND direction = 1) OR (movement_type IN ('OUT_ADJUSTMENT', 'OUT_PRODUCTION', 'OUT_PURCHASE_RETURN', 'OUT_SALE', 'OUT_SAMPLE', 'OUT_TRANSFER', 'OUT_WASTE') AND direction = -1)", name=op.f('ck_inventory_movements_type_direction')),
    sa.CheckConstraint("movement_type IN ('IN_ADJUSTMENT', 'IN_PRODUCTION', 'IN_PURCHASE', 'IN_SALE_RETURN', 'IN_TRANSFER', 'IN_WASTE_RECOVERY', 'OUT_ADJUSTMENT', 'OUT_PRODUCTION', 'OUT_PURCHASE_RETURN', 'OUT_SALE', 'OUT_SAMPLE', 'OUT_TRANSFER', 'OUT_WASTE')", name=op.f('ck_inventory_movements_movement_type_valid')),
    sa.CheckConstraint("reason_code IS NULL OR reason_code IN ('CONTEO_FISICO', 'DANO', 'ERROR_REGISTRO', 'MUESTRA', 'OBSEQUIO', 'ROBO')", name=op.f('ck_inventory_movements_reason_code_valid')),
    sa.CheckConstraint("reference_type IS NULL OR reference_type IN ('ADJUSTMENT', 'COUNT', 'PRODUCTION_INPUT', 'PRODUCTION_OUTPUT', 'PRODUCTION_WASTE', 'PURCHASE_ITEM', 'SALE_ITEM_BATCH', 'SHIPMENT_ITEM', 'TRANSFER')", name=op.f('ck_inventory_movements_reference_type_valid')),
    sa.CheckConstraint('direction IN (1, -1)', name=op.f('ck_inventory_movements_direction_valid')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_inventory_movements_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_inventory_movements_quantity_base_positive')),
    sa.CheckConstraint('reference_type IS NULL OR reference_id IS NOT NULL', name=op.f('ck_inventory_movements_reference_id_required')),
    sa.CheckConstraint('unit_cost IS NULL OR unit_cost >= 0', name=op.f('ck_inventory_movements_unit_cost_non_negative')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_inventory_movements_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['counterpart_movement_id'], ['inventory_movements.id'], name='fk_inventory_movements_counterpart', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_inventory_movements_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['location_id'], ['inventory_locations.id'], name=op.f('fk_inventory_movements_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_inventory_movements_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reverses_movement_id'], ['inventory_movements.id'], name='fk_inventory_movements_reverses', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_inventory_movements_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_movements'))
    )
    op.create_index('ix_inventory_movements_lookup', 'inventory_movements', ['product_id', 'batch_id', 'location_id', 'occurred_at'], unique=False)
    op.create_index('ix_inventory_movements_occurred', 'inventory_movements', [sa.literal_column('occurred_at DESC')], unique=False)
    op.create_index('ix_inventory_movements_reference', 'inventory_movements', ['reference_type', 'reference_id'], unique=False)
    op.create_index('ix_inventory_movements_type', 'inventory_movements', ['movement_type'], unique=False)
    op.create_table('process_executions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('production_order_id', sa.BigInteger(), nullable=False),
    sa.Column('process_id', sa.BigInteger(), nullable=False),
    sa.Column('sequence_no', sa.SmallInteger(), nullable=False),
    sa.Column('executor_type', sa.String(length=20), nullable=False),
    sa.Column('executor_party_id', sa.BigInteger(), nullable=True),
    sa.Column('location_id', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('input_quantity_base', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('output_quantity_base', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('waste_quantity_base', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('yield_pct', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('cost_rule_id', sa.BigInteger(), nullable=True),
    sa.Column('cost_unit_id', sa.BigInteger(), nullable=True),
    sa.Column('cost_rate', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('cost_basis', sa.String(length=30), nullable=True),
    sa.Column('chargeable_quantity', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('computed_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('actual_cost', sa.Numeric(precision=16, scale=2), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('supplier_document_number', sa.String(length=40), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(executor_type = 'EXTERNAL' AND executor_party_id IS NOT NULL) OR (executor_type = 'INTERNAL' AND executor_party_id IS NULL)", name=op.f('ck_process_executions_executor_coherent')),
    sa.CheckConstraint("executor_type IN ('EXTERNAL', 'INTERNAL')", name=op.f('ck_process_executions_executor_type_valid')),
    sa.CheckConstraint("status IN ('CANCELLED', 'DONE', 'IN_PROGRESS', 'PENDING', 'RECEIVED', 'SENT')", name=op.f('ck_process_executions_status_valid')),
    sa.CheckConstraint('computed_cost >= 0', name=op.f('ck_process_executions_computed_cost_non_negative')),
    sa.CheckConstraint('cost_rate IS NULL OR cost_rate >= 0', name=op.f('ck_process_executions_cost_rate_non_negative')),
    sa.CheckConstraint('input_quantity_base >= 0', name=op.f('ck_process_executions_input_quantity_base_non_negative')),
    sa.CheckConstraint('output_quantity_base + waste_quantity_base <= input_quantity_base', name=op.f('ck_process_executions_mass_balance')),
    sa.CheckConstraint('output_quantity_base >= 0', name=op.f('ck_process_executions_output_quantity_base_non_negative')),
    sa.CheckConstraint('sequence_no > 0', name=op.f('ck_process_executions_sequence_positive')),
    sa.CheckConstraint('waste_quantity_base >= 0', name=op.f('ck_process_executions_waste_quantity_base_non_negative')),
    sa.ForeignKeyConstraint(['cost_rule_id'], ['cost_rules.id'], name=op.f('fk_process_executions_cost_rule_id_cost_rules'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['cost_unit_id'], ['units_of_measure.id'], name=op.f('fk_process_executions_cost_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_process_executions_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['executor_party_id'], ['parties.id'], name=op.f('fk_process_executions_executor_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['location_id'], ['inventory_locations.id'], name=op.f('fk_process_executions_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['process_id'], ['production_processes.id'], name=op.f('fk_process_executions_process_id_production_processes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], name=op.f('fk_process_executions_production_order_id_production_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_process_executions_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_process_executions')),
    sa.UniqueConstraint('production_order_id', 'sequence_no', name='uq_process_executions_production_order_id')
    )
    op.create_index('ix_process_executions_executor', 'process_executions', ['executor_party_id', 'status'], unique=False)
    op.create_index('ix_process_executions_order', 'process_executions', ['production_order_id', 'sequence_no'], unique=False)
    op.create_index('ix_process_executions_status', 'process_executions', ['status'], unique=False)
    op.create_table('purchases',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('purchase_number', sa.String(length=30), nullable=False),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('purchase_type', sa.String(length=25), nullable=False),
    sa.Column('purchase_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='DRAFT', nullable=False),
    sa.Column('destination_location_id', sa.BigInteger(), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('discount_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('tax_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('withholding_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('freight_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('payment_status', sa.String(length=20), server_default='UNPAID', nullable=False),
    sa.Column('supplier_document_type', sa.String(length=30), nullable=True),
    sa.Column('supplier_document_number', sa.String(length=40), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("payment_status IN ('PAID', 'PARTIAL', 'UNPAID')", name=op.f('ck_purchases_payment_status_valid')),
    sa.CheckConstraint("purchase_type IN ('ASSET', 'COFFEE_GROWER', 'SERVICE', 'SUPPLIER')", name=op.f('ck_purchases_purchase_type_valid')),
    sa.CheckConstraint("status IN ('CANCELLED', 'CONFIRMED', 'DRAFT', 'RECEIVED')", name=op.f('ck_purchases_status_valid')),
    sa.CheckConstraint("supplier_document_type IS NULL OR supplier_document_type IN ('DOCUMENTO_SOPORTE','FACTURA','NINGUNO','RECIBO')", name=op.f('ck_purchases_supplier_document_type_valid')),
    sa.CheckConstraint('discount_total >= 0', name=op.f('ck_purchases_discount_total_non_negative')),
    sa.CheckConstraint('freight_amount >= 0', name=op.f('ck_purchases_freight_amount_non_negative')),
    sa.CheckConstraint('subtotal >= 0', name=op.f('ck_purchases_subtotal_non_negative')),
    sa.CheckConstraint('tax_total >= 0', name=op.f('ck_purchases_tax_total_non_negative')),
    sa.CheckConstraint('total >= 0', name=op.f('ck_purchases_total_non_negative')),
    sa.CheckConstraint('withholding_total >= 0', name=op.f('ck_purchases_withholding_total_non_negative')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_purchases_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['destination_location_id'], ['inventory_locations.id'], name=op.f('fk_purchases_destination_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_purchases_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_purchases_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchases')),
    sa.UniqueConstraint('purchase_number', name='uq_purchases_purchase_number')
    )
    op.create_index('ix_purchases_party_date', 'purchases', ['party_id', 'purchase_date'], unique=False)
    op.create_index('ix_purchases_status', 'purchases', ['status'], unique=False)
    op.create_table('sale_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('sale_id', sa.BigInteger(), nullable=False),
    sa.Column('line_no', sa.SmallInteger(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('price_list_item_id', sa.BigInteger(), nullable=True),
    sa.Column('price_source', sa.String(length=30), nullable=False),
    sa.Column('discount_pct', sa.Numeric(precision=9, scale=6), server_default='0', nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('tax_id', sa.BigInteger(), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=9, scale=6), server_default='0', nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('total_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('margin_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('costing_method_used', sa.String(length=25), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("price_source IN ('MANUAL', 'PARTY_RULE', 'PRICE_LIST')", name=op.f('ck_sale_items_price_source_valid')),
    sa.CheckConstraint('discount_pct >= 0 AND discount_pct <= 1', name=op.f('ck_sale_items_discount_pct_fraction')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sale_items_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_sale_items_quantity_base_positive')),
    sa.CheckConstraint('unit_price >= 0', name=op.f('ck_sale_items_unit_price_non_negative')),
    sa.ForeignKeyConstraint(['price_list_item_id'], ['price_list_items.id'], name=op.f('fk_sale_items_price_list_item_id_price_list_items'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_sale_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], name=op.f('fk_sale_items_sale_id_sales'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tax_id'], ['taxes.id'], name=op.f('fk_sale_items_tax_id_taxes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_sale_items_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sale_items')),
    sa.UniqueConstraint('sale_id', 'line_no', name='uq_sale_items_sale_id')
    )
    op.create_index('ix_sale_items_product', 'sale_items', ['product_id'], unique=False)
    op.create_index('ix_sale_items_sale', 'sale_items', ['sale_id'], unique=False)
    op.create_table('shipments',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('shipment_number', sa.String(length=30), nullable=False),
    sa.Column('sale_id', sa.BigInteger(), nullable=True),
    sa.Column('carrier_party_id', sa.BigInteger(), nullable=True),
    sa.Column('carrier_name', sa.String(length=120), nullable=True),
    sa.Column('shipment_type', sa.String(length=25), nullable=False),
    sa.Column('origin_location_id', sa.BigInteger(), nullable=True),
    sa.Column('destination_location_id', sa.BigInteger(), nullable=True),
    sa.Column('destination_address_id', sa.BigInteger(), nullable=True),
    sa.Column('tracking_number', sa.String(length=80), nullable=True),
    sa.Column('tracking_url', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=25), server_default='PENDING', nullable=False),
    sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('estimated_delivery_date', sa.Date(), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_by', sa.String(length=150), nullable=True),
    sa.Column('total_weight_kg', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('package_count', sa.SmallInteger(), nullable=True),
    sa.Column('freight_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('freight_charged', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('insurance_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('carrier_document_number', sa.String(length=60), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("shipment_type IN ('PROCESSOR_IN', 'PROCESSOR_OUT', 'RETURN', 'SALE_DELIVERY', 'TRANSFER')", name=op.f('ck_shipments_shipment_type_valid')),
    sa.CheckConstraint("status IN ('CANCELLED', 'DELIVERED', 'DISPATCHED', 'FAILED', 'IN_TRANSIT', 'PENDING', 'RETURNED')", name=op.f('ck_shipments_status_valid')),
    sa.CheckConstraint('freight_charged >= 0', name=op.f('ck_shipments_freight_charged_non_negative')),
    sa.CheckConstraint('freight_cost >= 0', name=op.f('ck_shipments_freight_cost_non_negative')),
    sa.CheckConstraint('insurance_cost >= 0', name=op.f('ck_shipments_insurance_cost_non_negative')),
    sa.CheckConstraint('origin_location_id IS NULL OR destination_location_id IS NULL OR origin_location_id <> destination_location_id', name=op.f('ck_shipments_origin_differs_destination')),
    sa.ForeignKeyConstraint(['carrier_party_id'], ['parties.id'], name=op.f('fk_shipments_carrier_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_shipments_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['destination_address_id'], ['addresses.id'], name=op.f('fk_shipments_destination_address_id_addresses'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['destination_location_id'], ['inventory_locations.id'], name=op.f('fk_shipments_destination_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['origin_location_id'], ['inventory_locations.id'], name=op.f('fk_shipments_origin_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], name=op.f('fk_shipments_sale_id_sales'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_shipments_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shipments')),
    sa.UniqueConstraint('shipment_number', name='uq_shipments_shipment_number')
    )
    op.create_index('ix_shipments_carrier', 'shipments', ['carrier_party_id'], unique=False)
    op.create_index('ix_shipments_sale', 'shipments', ['sale_id'], unique=False)
    op.create_index('ix_shipments_status', 'shipments', ['status'], unique=False)
    op.create_index('ix_shipments_tracking', 'shipments', ['tracking_number'], unique=False)
    op.create_table('inventory_balances',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('location_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('average_unit_cost', sa.Numeric(precision=16, scale=4), server_default='0', nullable=False),
    sa.Column('total_value', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('last_movement_id', sa.BigInteger(), nullable=True),
    sa.Column('last_movement_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('average_unit_cost >= 0', name=op.f('ck_inventory_balances_average_unit_cost_non_negative')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_inventory_balances_batch_id_batches'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['last_movement_id'], ['inventory_movements.id'], name=op.f('fk_inventory_balances_last_movement_id_inventory_movements'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['location_id'], ['inventory_locations.id'], name=op.f('fk_inventory_balances_location_id_inventory_locations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_inventory_balances_product_id_products'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inventory_balances')),
    sa.UniqueConstraint('product_id', 'batch_id', 'location_id', name='uq_inventory_balances_product_id')
    )
    op.create_index('ix_inventory_balances_batch_id', 'inventory_balances', ['batch_id'], unique=False)
    op.create_index('ix_inventory_balances_location_id', 'inventory_balances', ['location_id'], unique=False)
    op.create_index('uq_inventory_balances_no_batch', 'inventory_balances', ['product_id', 'location_id'], unique=True, postgresql_where=sa.text('batch_id IS NULL'))
    op.create_table('invoices',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('document_type', sa.String(length=30), nullable=False),
    sa.Column('resolution_id', sa.BigInteger(), nullable=True),
    sa.Column('prefix', sa.String(length=10), nullable=False),
    sa.Column('consecutive', sa.BigInteger(), nullable=False),
    sa.Column('full_number', sa.String(length=30), nullable=False),
    sa.Column('sale_id', sa.BigInteger(), nullable=True),
    sa.Column('purchase_id', sa.BigInteger(), nullable=True),
    sa.Column('party_id', sa.BigInteger(), nullable=False),
    sa.Column('related_invoice_id', sa.BigInteger(), nullable=True),
    sa.Column('issue_date', sa.Date(), nullable=False),
    sa.Column('issue_time', sa.Time(timezone=True), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('discount_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('tax_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('withholding_total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('payment_means', sa.String(length=20), nullable=True),
    sa.Column('payment_form', sa.String(length=20), nullable=True),
    sa.Column('cufe', sa.String(length=200), nullable=True),
    sa.Column('uuid', sa.String(length=100), nullable=True),
    sa.Column('qr_data', sa.Text(), nullable=True),
    sa.Column('xml_signed', sa.Text(), nullable=True),
    sa.Column('xml_path', sa.String(length=255), nullable=True),
    sa.Column('pdf_path', sa.String(length=255), nullable=True),
    sa.Column('dian_status', sa.String(length=25), server_default='DRAFT', nullable=False),
    sa.Column('dian_track_id', sa.String(length=100), nullable=True),
    sa.Column('dian_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('dian_errors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.Column('updated_by_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("dian_status IN ('ACCEPTED', 'CANCELLED', 'DRAFT', 'GENERATED', 'REJECTED', 'SENT', 'SIGNED')", name=op.f('ck_invoices_dian_status_valid')),
    sa.CheckConstraint("document_type <> 'DOCUMENTO_SOPORTE' OR purchase_id IS NOT NULL", name=op.f('ck_invoices_support_requires_purchase')),
    sa.CheckConstraint("document_type = 'DOCUMENTO_SOPORTE' OR sale_id IS NOT NULL", name=op.f('ck_invoices_requires_sale')),
    sa.CheckConstraint("document_type IN ('DOCUMENTO_SOPORTE', 'FACTURA_VENTA', 'NOTA_CREDITO', 'NOTA_DEBITO')", name=op.f('ck_invoices_document_type_valid')),
    sa.CheckConstraint("document_type NOT IN ('NOTA_CREDITO','NOTA_DEBITO') OR related_invoice_id IS NOT NULL", name=op.f('ck_invoices_note_requires_related')),
    sa.CheckConstraint("payment_form IS NULL OR payment_form IN ('CONTADO','CREDITO')", name=op.f('ck_invoices_payment_form_valid')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_invoices_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_invoices_party_id_parties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], name=op.f('fk_invoices_purchase_id_purchases'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['related_invoice_id'], ['invoices.id'], name=op.f('fk_invoices_related_invoice_id_invoices'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['resolution_id'], ['fiscal_resolutions.id'], name=op.f('fk_invoices_resolution_id_fiscal_resolutions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], name=op.f('fk_invoices_sale_id_sales'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_invoices_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoices')),
    sa.UniqueConstraint('full_number', name='uq_invoices_full_number'),
    sa.UniqueConstraint('prefix', 'consecutive', 'document_type', name='uq_invoices_prefix')
    )
    op.create_index('ix_invoices_dian_status', 'invoices', ['dian_status'], unique=False)
    op.create_index('ix_invoices_issue_date', 'invoices', [sa.literal_column('issue_date DESC')], unique=False)
    op.create_index('ix_invoices_party', 'invoices', ['party_id', sa.literal_column('issue_date DESC')], unique=False)
    op.create_index('ix_invoices_sale', 'invoices', ['sale_id'], unique=False)
    op.create_index('uq_invoices_cufe', 'invoices', ['cufe'], unique=True, postgresql_where=sa.text('cufe IS NOT NULL'))
    op.create_table('production_inputs',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('production_order_id', sa.BigInteger(), nullable=False),
    sa.Column('process_execution_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('total_cost', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('movement_id', sa.BigInteger(), nullable=True),
    sa.Column('consumed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_production_inputs_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_production_inputs_quantity_base_positive')),
    sa.CheckConstraint('total_cost >= 0', name=op.f('ck_production_inputs_total_cost_non_negative')),
    sa.CheckConstraint('unit_cost >= 0', name=op.f('ck_production_inputs_unit_cost_non_negative')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_production_inputs_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], name=op.f('fk_production_inputs_movement_id_inventory_movements'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['process_execution_id'], ['process_executions.id'], name=op.f('fk_production_inputs_process_execution_id_process_executions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_production_inputs_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], name=op.f('fk_production_inputs_production_order_id_production_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_production_inputs_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_inputs'))
    )
    op.create_index('ix_production_inputs_execution', 'production_inputs', ['process_execution_id'], unique=False)
    op.create_index('ix_production_inputs_order', 'production_inputs', ['production_order_id'], unique=False)
    op.create_index('ix_production_inputs_product', 'production_inputs', ['product_id', 'batch_id'], unique=False)
    op.create_table('production_outputs',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('production_order_id', sa.BigInteger(), nullable=False),
    sa.Column('process_execution_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('output_kind', sa.String(length=20), server_default='MAIN', nullable=False),
    sa.Column('cost_allocation_pct', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('allocated_cost', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), nullable=True),
    sa.Column('currency', sa.CHAR(length=3), server_default='COP', nullable=False),
    sa.Column('location_id', sa.BigInteger(), nullable=True),
    sa.Column('movement_id', sa.BigInteger(), nullable=True),
    sa.Column('produced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("output_kind IN ('BYPRODUCT', 'MAIN', 'REWORK')", name=op.f('ck_production_outputs_output_kind_valid')),
    sa.CheckConstraint('allocated_cost >= 0', name=op.f('ck_production_outputs_allocated_cost_non_negative')),
    sa.CheckConstraint('cost_allocation_pct IS NULL OR (cost_allocation_pct >= 0 AND cost_allocation_pct <= 1)', name=op.f('ck_production_outputs_allocation_fraction')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_production_outputs_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_production_outputs_quantity_base_positive')),
    sa.CheckConstraint('unit_cost IS NULL OR unit_cost >= 0', name=op.f('ck_production_outputs_unit_cost_non_negative')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_production_outputs_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['location_id'], ['inventory_locations.id'], name=op.f('fk_production_outputs_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], name=op.f('fk_production_outputs_movement_id_inventory_movements'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['process_execution_id'], ['process_executions.id'], name=op.f('fk_production_outputs_process_execution_id_process_executions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_production_outputs_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], name=op.f('fk_production_outputs_production_order_id_production_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_production_outputs_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_outputs'))
    )
    op.create_index('ix_production_outputs_execution', 'production_outputs', ['process_execution_id'], unique=False)
    op.create_index('ix_production_outputs_order', 'production_outputs', ['production_order_id'], unique=False)
    op.create_index('ix_production_outputs_product', 'production_outputs', ['product_id', 'batch_id'], unique=False)
    op.create_table('production_waste',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('production_order_id', sa.BigInteger(), nullable=False),
    sa.Column('process_execution_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('waste_type', sa.String(length=30), nullable=False),
    sa.Column('is_expected', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('is_recoverable', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('recovered_product_id', sa.BigInteger(), nullable=True),
    sa.Column('recovered_batch_id', sa.BigInteger(), nullable=True),
    sa.Column('cost_treatment', sa.String(length=30), server_default='ABSORBED_BY_OUTPUT', nullable=False),
    sa.Column('cost_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('movement_id', sa.BigInteger(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("cost_treatment IN ('ABSORBED_BY_OUTPUT', 'ALLOCATED_TO_BYPRODUCT', 'EXPENSED')", name=op.f('ck_production_waste_cost_treatment_valid')),
    sa.CheckConstraint("waste_type IN ('CASCARILLA', 'CONTAMINACION', 'DEFECTO', 'DERRAME', 'MERMA_HUMEDAD', 'MERMA_PROCESO', 'PASILLA')", name=op.f('ck_production_waste_waste_type_valid')),
    sa.CheckConstraint('cost_amount >= 0', name=op.f('ck_production_waste_cost_amount_non_negative')),
    sa.CheckConstraint('is_recoverable = FALSE OR recovered_product_id IS NOT NULL', name=op.f('ck_production_waste_recoverable_requires_product')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_production_waste_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_production_waste_quantity_base_positive')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_production_waste_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], name=op.f('fk_production_waste_movement_id_inventory_movements'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['process_execution_id'], ['process_executions.id'], name=op.f('fk_production_waste_process_execution_id_process_executions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_production_waste_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['production_order_id'], ['production_orders.id'], name=op.f('fk_production_waste_production_order_id_production_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recovered_batch_id'], ['batches.id'], name=op.f('fk_production_waste_recovered_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recovered_product_id'], ['products.id'], name=op.f('fk_production_waste_recovered_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_production_waste_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_waste'))
    )
    op.create_index('ix_production_waste_execution', 'production_waste', ['process_execution_id'], unique=False)
    op.create_index('ix_production_waste_order', 'production_waste', ['production_order_id'], unique=False)
    op.create_index('ix_production_waste_type', 'production_waste', ['waste_type', 'is_expected'], unique=False)
    op.create_table('purchase_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('purchase_id', sa.BigInteger(), nullable=False),
    sa.Column('line_no', sa.SmallInteger(), nullable=False),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_price', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('tax_id', sa.BigInteger(), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=9, scale=6), server_default='0', nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('allocated_freight', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('landed_unit_cost', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('allocated_freight >= 0', name=op.f('ck_purchase_items_allocated_freight_non_negative')),
    sa.CheckConstraint('discount_amount >= 0', name=op.f('ck_purchase_items_discount_amount_non_negative')),
    sa.CheckConstraint('landed_unit_cost >= 0', name=op.f('ck_purchase_items_landed_unit_cost_non_negative')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_purchase_items_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_purchase_items_quantity_base_positive')),
    sa.CheckConstraint('tax_rate >= 0', name=op.f('ck_purchase_items_tax_rate_non_negative')),
    sa.CheckConstraint('unit_price >= 0', name=op.f('ck_purchase_items_unit_price_non_negative')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_purchase_items_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_purchase_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], name=op.f('fk_purchase_items_purchase_id_purchases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tax_id'], ['taxes.id'], name=op.f('fk_purchase_items_tax_id_taxes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_purchase_items_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_purchase_items')),
    sa.UniqueConstraint('purchase_id', 'line_no', name='uq_purchase_items_purchase_id')
    )
    op.create_index('ix_purchase_items_batch_id', 'purchase_items', ['batch_id'], unique=False)
    op.create_index('ix_purchase_items_product_id', 'purchase_items', ['product_id'], unique=False)
    op.create_index('ix_purchase_items_purchase_id', 'purchase_items', ['purchase_id'], unique=False)
    op.create_table('sale_item_batches',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('sale_item_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=False),
    sa.Column('location_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('total_cost', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('movement_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_sale_item_batches_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_sale_item_batches_quantity_base_positive')),
    sa.CheckConstraint('unit_cost >= 0', name=op.f('ck_sale_item_batches_unit_cost_non_negative')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_sale_item_batches_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['location_id'], ['inventory_locations.id'], name=op.f('fk_sale_item_batches_location_id_inventory_locations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], name=op.f('fk_sale_item_batches_movement_id_inventory_movements'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sale_item_id'], ['sale_items.id'], name=op.f('fk_sale_item_batches_sale_item_id_sale_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_sale_item_batches_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sale_item_batches')),
    sa.UniqueConstraint('sale_item_id', 'batch_id', 'location_id', name='uq_sale_item_batches_sale_item_id')
    )
    op.create_index('ix_sib_batch', 'sale_item_batches', ['batch_id'], unique=False)
    op.create_index('ix_sib_sale_item', 'sale_item_batches', ['sale_item_id'], unique=False)
    op.create_table('shipment_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('shipment_id', sa.BigInteger(), nullable=False),
    sa.Column('event_type', sa.String(length=30), nullable=False),
    sa.Column('location_text', sa.String(length=150), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("event_type IN ('CREATED', 'DELIVERED', 'DISPATCHED', 'FAILED', 'IN_TRANSIT', 'NOTE', 'OUT_FOR_DELIVERY', 'RETURNED')", name=op.f('ck_shipment_events_event_type_valid')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_shipment_events_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], name=op.f('fk_shipment_events_shipment_id_shipments'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shipment_events'))
    )
    op.create_index('ix_shipment_events_shipment', 'shipment_events', ['shipment_id', 'occurred_at'], unique=False)
    op.create_table('shipment_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('shipment_id', sa.BigInteger(), nullable=False),
    sa.Column('sale_item_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=False),
    sa.Column('batch_id', sa.BigInteger(), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=False),
    sa.Column('quantity_base', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('movement_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_shipment_items_quantity_positive')),
    sa.CheckConstraint('quantity_base > 0', name=op.f('ck_shipment_items_quantity_base_positive')),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name=op.f('fk_shipment_items_batch_id_batches'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['movement_id'], ['inventory_movements.id'], name=op.f('fk_shipment_items_movement_id_inventory_movements'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_shipment_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['sale_item_id'], ['sale_items.id'], name=op.f('fk_shipment_items_sale_item_id_sale_items'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['shipment_id'], ['shipments.id'], name=op.f('fk_shipment_items_shipment_id_shipments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_shipment_items_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shipment_items'))
    )
    op.create_index('ix_shipment_items_shipment_id', 'shipment_items', ['shipment_id'], unique=False)
    op.create_table('invoice_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('invoice_id', sa.BigInteger(), nullable=False),
    sa.Column('event_type', sa.String(length=30), nullable=False),
    sa.Column('status_before', sa.String(length=25), nullable=True),
    sa.Column('status_after', sa.String(length=25), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("event_type IN ('ACCEPTED', 'CANCELLED', 'EMAILED', 'ERROR', 'GENERATED', 'REJECTED', 'RETRY', 'SENT', 'SIGNED')", name=op.f('ck_invoice_events_event_type_valid')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_invoice_events_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_invoice_events_invoice_id_invoices'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoice_events'))
    )
    op.create_index('ix_invoice_events_invoice', 'invoice_events', ['invoice_id', 'occurred_at'], unique=False)
    op.create_table('invoice_items',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('invoice_id', sa.BigInteger(), nullable=False),
    sa.Column('line_no', sa.SmallInteger(), nullable=False),
    sa.Column('sale_item_id', sa.BigInteger(), nullable=True),
    sa.Column('purchase_item_id', sa.BigInteger(), nullable=True),
    sa.Column('product_id', sa.BigInteger(), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('product_code', sa.String(length=40), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('unit_id', sa.BigInteger(), nullable=True),
    sa.Column('unit_dian_code', sa.String(length=10), nullable=True),
    sa.Column('unit_price', sa.Numeric(precision=16, scale=4), nullable=False),
    sa.Column('discount_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('tax_code', sa.String(length=20), nullable=True),
    sa.Column('tax_rate', sa.Numeric(precision=9, scale=6), server_default='0', nullable=False),
    sa.Column('tax_amount', sa.Numeric(precision=16, scale=2), server_default='0', nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=16, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('discount_amount >= 0', name=op.f('ck_invoice_items_discount_non_negative')),
    sa.CheckConstraint('quantity > 0', name=op.f('ck_invoice_items_quantity_positive')),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_invoice_items_invoice_id_invoices'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], name=op.f('fk_invoice_items_product_id_products'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['purchase_item_id'], ['purchase_items.id'], name=op.f('fk_invoice_items_purchase_item_id_purchase_items'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sale_item_id'], ['sale_items.id'], name=op.f('fk_invoice_items_sale_item_id_sale_items'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['unit_id'], ['units_of_measure.id'], name=op.f('fk_invoice_items_unit_id_units_of_measure'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoice_items')),
    sa.UniqueConstraint('invoice_id', 'line_no', name='uq_invoice_items_invoice_id')
    )
    op.create_index('ix_invoice_items_invoice_id', 'invoice_items', ['invoice_id'], unique=False)

    for nombre, tabla, refiere, col, refcol, ondelete in FK_CICLICAS:
        op.create_foreign_key(nombre, tabla, refiere, [col], [refcol],
                              ondelete=ondelete)


def downgrade() -> None:
    for nombre, tabla, *_ in FK_CICLICAS:
        op.drop_constraint(nombre, tabla, type_="foreignkey")

    op.drop_index('ix_invoice_items_invoice_id', table_name='invoice_items')
    op.drop_table('invoice_items')
    op.drop_index('ix_invoice_events_invoice', table_name='invoice_events')
    op.drop_table('invoice_events')
    op.drop_index('ix_shipment_items_shipment_id', table_name='shipment_items')
    op.drop_table('shipment_items')
    op.drop_index('ix_shipment_events_shipment', table_name='shipment_events')
    op.drop_table('shipment_events')
    op.drop_index('ix_sib_batch', table_name='sale_item_batches')
    op.drop_index('ix_sib_sale_item', table_name='sale_item_batches')
    op.drop_table('sale_item_batches')
    op.drop_index('ix_purchase_items_batch_id', table_name='purchase_items')
    op.drop_index('ix_purchase_items_product_id', table_name='purchase_items')
    op.drop_index('ix_purchase_items_purchase_id', table_name='purchase_items')
    op.drop_table('purchase_items')
    op.drop_index('ix_production_waste_execution', table_name='production_waste')
    op.drop_index('ix_production_waste_order', table_name='production_waste')
    op.drop_index('ix_production_waste_type', table_name='production_waste')
    op.drop_table('production_waste')
    op.drop_index('ix_production_outputs_execution', table_name='production_outputs')
    op.drop_index('ix_production_outputs_order', table_name='production_outputs')
    op.drop_index('ix_production_outputs_product', table_name='production_outputs')
    op.drop_table('production_outputs')
    op.drop_index('ix_production_inputs_execution', table_name='production_inputs')
    op.drop_index('ix_production_inputs_order', table_name='production_inputs')
    op.drop_index('ix_production_inputs_product', table_name='production_inputs')
    op.drop_table('production_inputs')
    op.drop_index('ix_invoices_dian_status', table_name='invoices')
    op.drop_index('ix_invoices_issue_date', table_name='invoices')
    op.drop_index('ix_invoices_party', table_name='invoices')
    op.drop_index('ix_invoices_sale', table_name='invoices')
    op.drop_index('uq_invoices_cufe', table_name='invoices', postgresql_where=sa.text('cufe IS NOT NULL'))
    op.drop_table('invoices')
    op.drop_index('ix_inventory_balances_batch_id', table_name='inventory_balances')
    op.drop_index('ix_inventory_balances_location_id', table_name='inventory_balances')
    op.drop_index('uq_inventory_balances_no_batch', table_name='inventory_balances', postgresql_where=sa.text('batch_id IS NULL'))
    op.drop_table('inventory_balances')
    op.drop_index('ix_shipments_carrier', table_name='shipments')
    op.drop_index('ix_shipments_sale', table_name='shipments')
    op.drop_index('ix_shipments_status', table_name='shipments')
    op.drop_index('ix_shipments_tracking', table_name='shipments')
    op.drop_table('shipments')
    op.drop_index('ix_sale_items_product', table_name='sale_items')
    op.drop_index('ix_sale_items_sale', table_name='sale_items')
    op.drop_table('sale_items')
    op.drop_index('ix_purchases_party_date', table_name='purchases')
    op.drop_index('ix_purchases_status', table_name='purchases')
    op.drop_table('purchases')
    op.drop_index('ix_process_executions_executor', table_name='process_executions')
    op.drop_index('ix_process_executions_order', table_name='process_executions')
    op.drop_index('ix_process_executions_status', table_name='process_executions')
    op.drop_table('process_executions')
    op.drop_index('ix_inventory_movements_lookup', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_occurred', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_reference', table_name='inventory_movements')
    op.drop_index('ix_inventory_movements_type', table_name='inventory_movements')
    op.drop_table('inventory_movements')
    op.drop_index('ix_ife_party_status', table_name='intermediary_fee_entries')
    op.drop_index('ix_ife_sale', table_name='intermediary_fee_entries')
    op.drop_table('intermediary_fee_entries')
    op.drop_index('ix_cost_entries_accounting', table_name='cost_entries')
    op.drop_index('ix_cost_entries_category', table_name='cost_entries')
    op.drop_index('ix_cost_entries_object', table_name='cost_entries')
    op.drop_index('ix_cost_entries_party', table_name='cost_entries')
    op.drop_table('cost_entries')
    op.drop_index('ix_batch_lineage_child_batch_id', table_name='batch_lineage')
    op.drop_index('ix_batch_lineage_parent_batch_id', table_name='batch_lineage')
    op.drop_table('batch_lineage')
    op.drop_index('ix_sales_channel', table_name='sales')
    op.drop_index('ix_sales_date', table_name='sales')
    op.drop_index('ix_sales_party_date', table_name='sales')
    op.drop_index('ix_sales_payment_status', table_name='sales')
    op.drop_index('ix_sales_status', table_name='sales')
    op.drop_table('sales')
    op.drop_index('ix_payment_allocations_target', table_name='payment_allocations')
    op.drop_table('payment_allocations')
    op.drop_index('ix_inventory_locations_location_type', table_name='inventory_locations')
    op.drop_index('ix_inventory_locations_party_id', table_name='inventory_locations')
    op.drop_table('inventory_locations')
    op.drop_index('ix_expenses_accounting_date', table_name='expenses')
    op.drop_index('ix_expenses_category_date', table_name='expenses')
    op.drop_index('ix_expenses_party', table_name='expenses')
    op.drop_table('expenses')
    op.drop_index('ix_batches_harvest_year', table_name='batches')
    op.drop_index('ix_batches_origin_party', table_name='batches')
    op.drop_index('ix_batches_product', table_name='batches')
    op.drop_table('batches')
    op.drop_index('ix_unit_conversions_product_id', table_name='unit_conversions')
    op.drop_index('uq_unit_conversions_universal', table_name='unit_conversions', postgresql_where=sa.text('product_id IS NULL'))
    op.drop_table('unit_conversions')
    op.drop_index('ix_production_orders_dates', table_name='production_orders')
    op.drop_index('ix_production_orders_status', table_name='production_orders')
    op.drop_table('production_orders')
    op.drop_index('ix_price_list_items_lookup', table_name='price_list_items')
    op.drop_table('price_list_items')
    op.drop_index('ix_payments_party', table_name='payments')
    op.drop_index('ix_payments_status', table_name='payments')
    op.drop_table('payments')
    op.drop_index('ix_party_roles_role_code', table_name='party_roles')
    op.drop_table('party_roles')
    op.drop_index('ix_party_price_rules_party_id', table_name='party_price_rules')
    op.drop_table('party_price_rules')
    op.drop_index('ix_party_contacts_party_id', table_name='party_contacts')
    op.drop_index('uq_party_contacts_one_primary', table_name='party_contacts', postgresql_where=sa.text('is_primary'))
    op.drop_table('party_contacts')
    op.drop_index('ix_intermediary_fee_rules_party_id', table_name='intermediary_fee_rules')
    op.drop_table('intermediary_fee_rules')
    op.drop_index('ix_expense_categories_parent_id', table_name='expense_categories')
    op.drop_table('expense_categories')
    op.drop_index('ix_cost_rules_executor', table_name='cost_rules')
    op.drop_index('ix_cost_rules_lookup', table_name='cost_rules')
    op.drop_table('cost_rules')
    op.drop_table('coffee_profiles')
    op.drop_index('ix_addresses_party_id', table_name='addresses')
    op.drop_index('uq_addresses_one_primary', table_name='addresses', postgresql_where=sa.text('is_primary'))
    op.drop_table('addresses')
    op.drop_table('user_roles')
    op.drop_index('ix_products_is_active', table_name='products')
    op.drop_index('ix_products_product_kind', table_name='products')
    op.drop_index('ix_products_sku', table_name='products')
    op.drop_index('uq_products_barcode', table_name='products', postgresql_where=sa.text('barcode IS NOT NULL'))
    op.drop_table('products')
    op.drop_index('ix_production_processes_default_sequence', table_name='production_processes')
    op.drop_table('production_processes')
    op.drop_index('uq_price_lists_one_default', table_name='price_lists', postgresql_where=sa.text('is_default AND is_active'))
    op.drop_table('price_lists')
    op.drop_index('ix_parties_document_number', table_name='parties')
    op.drop_index('ix_parties_is_active', table_name='parties')
    op.drop_index('ix_parties_legal_name', table_name='parties')
    op.drop_table('parties')
    op.drop_table('fiscal_resolutions')
    op.drop_table('document_sequences')
    op.drop_index('ix_cost_categories_nature', table_name='cost_categories')
    op.drop_index('ix_cost_categories_parent_id', table_name='cost_categories')
    op.drop_table('cost_categories')
    op.drop_index('ix_app_settings_group_name', table_name='app_settings')
    op.drop_table('app_settings')
    op.drop_index('ix_users_is_active', table_name='users')
    op.drop_table('users')
    op.drop_index('ix_units_of_measure_dimension', table_name='units_of_measure')
    op.drop_index('uq_uom_one_base_per_dimension', table_name='units_of_measure', postgresql_where=sa.text('is_base_for_dimension'))
    op.drop_table('units_of_measure')
    op.drop_index('ix_taxes_tax_type', table_name='taxes')
    op.drop_table('taxes')
    op.drop_table('roles')
    op.drop_index('ix_product_categories_parent_id', table_name='product_categories')
    op.drop_table('product_categories')
