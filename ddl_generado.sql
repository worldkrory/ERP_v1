-- DDL generado desde los modelos SQLAlchemy del ERP Densa Niebla.
-- NO es una migracion de Alembic: sirve para probar el esquema en una
-- base de datos desechable antes de aprobar los modelos.
--
--   createdb densa_ddl_test
--   psql -d densa_ddl_test -f ddl_generado.sql

\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE TABLE users (
	id BIGSERIAL NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(150) NOT NULL, 
	party_id BIGINT, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	is_superuser BOOLEAN DEFAULT 'false' NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	failed_login_count SMALLINT DEFAULT '0' NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	password_changed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX ix_users_is_active ON users (is_active);

CREATE TABLE roles (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	permissions JSONB DEFAULT '''[]''::jsonb' NOT NULL, 
	is_system BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_roles PRIMARY KEY (id), 
	CONSTRAINT uq_roles_code UNIQUE (code)
);

CREATE TABLE units_of_measure (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(15) NOT NULL, 
	name VARCHAR(60) NOT NULL, 
	dimension VARCHAR(20) NOT NULL, 
	is_base_for_dimension BOOLEAN DEFAULT 'false' NOT NULL, 
	decimal_places SMALLINT DEFAULT '3' NOT NULL, 
	dian_code VARCHAR(10), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_units_of_measure PRIMARY KEY (id), 
	CONSTRAINT uq_units_of_measure_code UNIQUE (code), 
	CONSTRAINT ck_units_of_measure_dimension_valid CHECK (dimension IN ('COUNT', 'MASS', 'TIME', 'VOLUME')), 
	CONSTRAINT ck_units_of_measure_decimal_places_range CHECK (decimal_places >= 0 AND decimal_places <= 6)
);

CREATE UNIQUE INDEX uq_uom_one_base_per_dimension ON units_of_measure (dimension) WHERE is_base_for_dimension;

CREATE INDEX ix_units_of_measure_dimension ON units_of_measure (dimension);

CREATE TABLE taxes (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(20) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	tax_type VARCHAR(20) NOT NULL, 
	rate NUMERIC(9, 6) NOT NULL, 
	dian_code VARCHAR(10), 
	is_withholding BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_taxes PRIMARY KEY (id), 
	CONSTRAINT uq_taxes_code UNIQUE (code), 
	CONSTRAINT ck_taxes_tax_type_valid CHECK (tax_type IN ('INC', 'IVA', 'NONE', 'RETEFUENTE', 'RETEICA', 'RETEIVA')), 
	CONSTRAINT ck_taxes_rate_non_negative CHECK (rate >= 0), 
	CONSTRAINT ck_taxes_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX ix_taxes_tax_type ON taxes (tax_type, valid_to);

CREATE TABLE product_categories (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	parent_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_product_categories PRIMARY KEY (id), 
	CONSTRAINT uq_product_categories_code UNIQUE (code), 
	CONSTRAINT ck_product_categories_no_self_parent CHECK (parent_id IS NULL OR parent_id <> id), 
	CONSTRAINT fk_product_categories_parent_id_product_categories FOREIGN KEY(parent_id) REFERENCES product_categories (id) ON DELETE RESTRICT
);

CREATE INDEX ix_product_categories_parent_id ON product_categories (parent_id);

CREATE TABLE user_roles (
	id BIGSERIAL NOT NULL, 
	user_id BIGINT NOT NULL, 
	role_id BIGINT NOT NULL, 
	assigned_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	assigned_by_id BIGINT, 
	CONSTRAINT pk_user_roles PRIMARY KEY (id), 
	CONSTRAINT uq_user_roles_user_id UNIQUE (user_id, role_id), 
	CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_user_roles_assigned_by_id_users FOREIGN KEY(assigned_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE parties (
	id BIGSERIAL NOT NULL, 
	party_type VARCHAR(20) NOT NULL, 
	document_type VARCHAR(10) NOT NULL, 
	document_number VARCHAR(30) NOT NULL, 
	verification_digit SMALLINT, 
	legal_name VARCHAR(200) NOT NULL, 
	trade_name VARCHAR(200), 
	first_name VARCHAR(100), 
	last_name VARCHAR(100), 
	email VARCHAR(255), 
	phone VARCHAR(30), 
	whatsapp VARCHAR(30), 
	tax_regime VARCHAR(30), 
	tax_responsibilities JSONB DEFAULT '''[]''::jsonb' NOT NULL, 
	is_vat_withholding_agent BOOLEAN DEFAULT 'false' NOT NULL, 
	municipality_code VARCHAR(5), 
	department_code VARCHAR(2), 
	country_code CHAR(2) DEFAULT 'CO' NOT NULL, 
	credit_limit NUMERIC(16, 2), 
	payment_term_days SMALLINT DEFAULT '0' NOT NULL, 
	default_price_list_id BIGINT, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_parties PRIMARY KEY (id), 
	CONSTRAINT uq_parties_document_type UNIQUE (document_type, document_number), 
	CONSTRAINT ck_parties_party_type_valid CHECK (party_type IN ('JURIDICA', 'NATURAL')), 
	CONSTRAINT ck_parties_document_type_valid CHECK (document_type IN ('CC', 'CE', 'NIT', 'NIT_EXT', 'PAS', 'PEP', 'RC', 'TI')), 
	CONSTRAINT ck_parties_tax_regime_valid CHECK (tax_regime IS NULL OR tax_regime IN ('COMUN','GRAN_CONTRIBUYENTE','NO_RESPONSABLE_IVA','REGIMEN_SIMPLE','SIMPLIFICADO')), 
	CONSTRAINT ck_parties_nit_requires_dv CHECK (document_type <> 'NIT' OR verification_digit IS NOT NULL), 
	CONSTRAINT ck_parties_natural_requires_names CHECK (party_type <> 'NATURAL' OR (first_name IS NOT NULL AND last_name IS NOT NULL)), 
	CONSTRAINT ck_parties_credit_limit_non_negative CHECK (credit_limit IS NULL OR credit_limit >= 0), 
	CONSTRAINT ck_parties_payment_term_non_negative CHECK (payment_term_days >= 0), 
	CONSTRAINT fk_parties_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_parties_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_parties_document_number ON parties (document_number);

CREATE INDEX ix_parties_is_active ON parties (is_active);

CREATE INDEX ix_parties_legal_name ON parties (legal_name);

CREATE TABLE products (
	id BIGSERIAL NOT NULL, 
	sku VARCHAR(40) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	product_kind VARCHAR(25) NOT NULL, 
	category_id BIGINT, 
	base_unit_id BIGINT NOT NULL, 
	sales_unit_id BIGINT, 
	purchase_unit_id BIGINT, 
	tax_id BIGINT, 
	tracks_batches BOOLEAN DEFAULT 'true' NOT NULL, 
	costing_method VARCHAR(25) DEFAULT 'SYSTEM_DEFAULT' NOT NULL, 
	is_sellable BOOLEAN DEFAULT 'true' NOT NULL, 
	is_purchasable BOOLEAN DEFAULT 'false' NOT NULL, 
	is_produced BOOLEAN DEFAULT 'false' NOT NULL, 
	min_stock NUMERIC(16, 4), 
	weight_kg NUMERIC(16, 4), 
	barcode VARCHAR(50), 
	image_path VARCHAR(255), 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_products PRIMARY KEY (id), 
	CONSTRAINT uq_products_sku UNIQUE (sku), 
	CONSTRAINT ck_products_product_kind_valid CHECK (product_kind IN ('FINISHED', 'RAW_MATERIAL', 'SEMI_FINISHED', 'SERVICE', 'SUPPLY')), 
	CONSTRAINT ck_products_costing_method_valid CHECK (costing_method IN ('SPECIFIC_BATCH', 'SYSTEM_DEFAULT', 'WEIGHTED_AVERAGE')), 
	CONSTRAINT ck_products_service_without_batches CHECK (tracks_batches = FALSE OR product_kind <> 'SERVICE'), 
	CONSTRAINT ck_products_at_least_one_usage CHECK (is_sellable OR is_purchasable OR is_produced), 
	CONSTRAINT ck_products_min_stock_non_negative CHECK (min_stock IS NULL OR min_stock >= 0), 
	CONSTRAINT ck_products_weight_non_negative CHECK (weight_kg IS NULL OR weight_kg >= 0), 
	CONSTRAINT fk_products_category_id_product_categories FOREIGN KEY(category_id) REFERENCES product_categories (id) ON DELETE SET NULL, 
	CONSTRAINT fk_products_base_unit_id_units_of_measure FOREIGN KEY(base_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_products_sales_unit_id_units_of_measure FOREIGN KEY(sales_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_products_purchase_unit_id_units_of_measure FOREIGN KEY(purchase_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_products_tax_id_taxes FOREIGN KEY(tax_id) REFERENCES taxes (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_products_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_products_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_products_sku ON products (sku);

CREATE UNIQUE INDEX uq_products_barcode ON products (barcode) WHERE barcode IS NOT NULL;

CREATE INDEX ix_products_is_active ON products (is_active);

CREATE INDEX ix_products_product_kind ON products (product_kind);

CREATE TABLE price_lists (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	channel VARCHAR(25) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	includes_tax BOOLEAN DEFAULT 'false' NOT NULL, 
	is_default BOOLEAN DEFAULT 'false' NOT NULL, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_price_lists PRIMARY KEY (id), 
	CONSTRAINT uq_price_lists_code UNIQUE (code), 
	CONSTRAINT ck_price_lists_channel_valid CHECK (channel IN ('CAFETERIA', 'EXPORT', 'INTERMEDIARY', 'INTERNAL', 'RETAIL', 'WHOLESALE')), 
	CONSTRAINT ck_price_lists_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT fk_price_lists_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_price_lists_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_price_lists_one_default ON price_lists (channel) WHERE is_default AND is_active;

CREATE TABLE production_processes (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	default_sequence SMALLINT NOT NULL, 
	default_unit_id BIGINT NOT NULL, 
	yields_new_batch BOOLEAN DEFAULT 'false' NOT NULL, 
	changes_product BOOLEAN DEFAULT 'false' NOT NULL, 
	expected_yield_pct NUMERIC(9, 6), 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_production_processes PRIMARY KEY (id), 
	CONSTRAINT uq_production_processes_code UNIQUE (code), 
	CONSTRAINT ck_production_processes_sequence_positive CHECK (default_sequence > 0), 
	CONSTRAINT ck_production_processes_expected_yield_fraction CHECK (expected_yield_pct IS NULL OR (expected_yield_pct > 0 AND expected_yield_pct <= 1)), 
	CONSTRAINT fk_production_processes_default_unit_id_units_of_measure FOREIGN KEY(default_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_processes_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_production_processes_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_production_processes_default_sequence ON production_processes (default_sequence);

CREATE TABLE cost_categories (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	parent_id BIGINT, 
	nature VARCHAR(20) NOT NULL, 
	affects_inventory BOOLEAN DEFAULT 'true' NOT NULL, 
	allocation_basis VARCHAR(25), 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_cost_categories PRIMARY KEY (id), 
	CONSTRAINT uq_cost_categories_code UNIQUE (code), 
	CONSTRAINT ck_cost_categories_nature_valid CHECK (nature IN ('DIRECT', 'INDIRECT')), 
	CONSTRAINT ck_cost_categories_allocation_basis_valid CHECK (allocation_basis IS NULL OR allocation_basis IN ('MANUAL','QUANTITY','TIME','VALUE')), 
	CONSTRAINT fk_cost_categories_parent_id_cost_categories FOREIGN KEY(parent_id) REFERENCES cost_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_categories_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cost_categories_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_cost_categories_parent_id ON cost_categories (parent_id);

CREATE INDEX ix_cost_categories_nature ON cost_categories (nature);

CREATE TABLE fiscal_resolutions (
	id BIGSERIAL NOT NULL, 
	resolution_number VARCHAR(40) NOT NULL, 
	document_type VARCHAR(30) NOT NULL, 
	prefix VARCHAR(10) NOT NULL, 
	range_from BIGINT NOT NULL, 
	range_to BIGINT NOT NULL, 
	current_number BIGINT NOT NULL, 
	technical_key VARCHAR(255), 
	valid_from DATE NOT NULL, 
	valid_to DATE NOT NULL, 
	environment VARCHAR(15) DEFAULT 'HABILITACION' NOT NULL, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_fiscal_resolutions PRIMARY KEY (id), 
	CONSTRAINT uq_fiscal_resolutions_prefix UNIQUE (prefix, document_type, resolution_number), 
	CONSTRAINT ck_fiscal_resolutions_document_type_valid CHECK (document_type IN ('DOCUMENTO_SOPORTE', 'FACTURA_VENTA', 'NOMINA', 'NOTA_CREDITO', 'NOTA_DEBITO')), 
	CONSTRAINT ck_fiscal_resolutions_environment_valid CHECK (environment IN ('HABILITACION', 'PRODUCCION')), 
	CONSTRAINT ck_fiscal_resolutions_range_order CHECK (range_to > range_from), 
	CONSTRAINT ck_fiscal_resolutions_current_number_in_range CHECK (current_number >= range_from - 1 AND current_number <= range_to), 
	CONSTRAINT ck_fiscal_resolutions_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT fk_fiscal_resolutions_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_fiscal_resolutions_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE app_settings (
	id BIGSERIAL NOT NULL, 
	key VARCHAR(60) NOT NULL, 
	value TEXT, 
	value_type VARCHAR(20) NOT NULL, 
	group_name VARCHAR(40), 
	description TEXT, 
	is_editable BOOLEAN DEFAULT 'true' NOT NULL, 
	changed_at TIMESTAMP WITH TIME ZONE, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_app_settings PRIMARY KEY (id), 
	CONSTRAINT uq_app_settings_key UNIQUE (key), 
	CONSTRAINT ck_app_settings_value_type_valid CHECK (value_type IN ('BOOLEAN', 'DATE', 'DECIMAL', 'INTEGER', 'JSON', 'STRING')), 
	CONSTRAINT fk_app_settings_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_app_settings_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_app_settings_group_name ON app_settings (group_name);

CREATE TABLE document_sequences (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	prefix VARCHAR(10), 
	pattern VARCHAR(40) NOT NULL, 
	next_number BIGINT DEFAULT '1' NOT NULL, 
	resets_yearly BOOLEAN DEFAULT 'true' NOT NULL, 
	current_year SMALLINT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_document_sequences PRIMARY KEY (id), 
	CONSTRAINT uq_document_sequences_code UNIQUE (code), 
	CONSTRAINT ck_document_sequences_code_valid CHECK (code IN ('EXPENSE', 'PAYMENT', 'PRODUCTION_ORDER', 'PURCHASE', 'SALE', 'SHIPMENT')), 
	CONSTRAINT ck_document_sequences_next_number_min CHECK (next_number >= 1), 
	CONSTRAINT ck_document_sequences_current_year_range CHECK (current_year IS NULL OR current_year >= 2000), 
	CONSTRAINT fk_document_sequences_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_document_sequences_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE party_roles (
	id BIGSERIAL NOT NULL, 
	party_id BIGINT NOT NULL, 
	role_code VARCHAR(30) NOT NULL, 
	valid_from DATE DEFAULT CURRENT_DATE NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_party_roles PRIMARY KEY (id), 
	CONSTRAINT uq_party_roles_party_id UNIQUE (party_id, role_code, valid_from), 
	CONSTRAINT ck_party_roles_role_code_valid CHECK (role_code IN ('CAFETERIA', 'CARRIER', 'COFFEE_GROWER', 'CUSTOMER', 'EMPLOYEE', 'INTERMEDIARY', 'PROCESSOR', 'SUPPLIER')), 
	CONSTRAINT ck_party_roles_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT fk_party_roles_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE CASCADE
);

CREATE INDEX ix_party_roles_role_code ON party_roles (role_code, valid_to);

CREATE TABLE addresses (
	id BIGSERIAL NOT NULL, 
	party_id BIGINT NOT NULL, 
	label VARCHAR(60), 
	address_type VARCHAR(20) DEFAULT 'BOTH' NOT NULL, 
	address_line VARCHAR(255) NOT NULL, 
	address_line_2 VARCHAR(255), 
	municipality_code VARCHAR(5), 
	municipality_name VARCHAR(100) NOT NULL, 
	department_code VARCHAR(2), 
	department_name VARCHAR(100) NOT NULL, 
	country_code CHAR(2) DEFAULT 'CO' NOT NULL, 
	postal_code VARCHAR(10), 
	latitude NUMERIC(10, 7), 
	longitude NUMERIC(10, 7), 
	is_primary BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_addresses PRIMARY KEY (id), 
	CONSTRAINT ck_addresses_address_type_valid CHECK (address_type IN ('BILLING', 'BOTH', 'FARM', 'SHIPPING')), 
	CONSTRAINT ck_addresses_latitude_range CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)), 
	CONSTRAINT ck_addresses_longitude_range CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180)), 
	CONSTRAINT fk_addresses_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_addresses_one_primary ON addresses (party_id) WHERE is_primary;

CREATE INDEX ix_addresses_party_id ON addresses (party_id);

CREATE TABLE party_contacts (
	id BIGSERIAL NOT NULL, 
	party_id BIGINT NOT NULL, 
	full_name VARCHAR(150) NOT NULL, 
	position VARCHAR(100), 
	email VARCHAR(255), 
	phone VARCHAR(30), 
	is_primary BOOLEAN DEFAULT 'false' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_party_contacts PRIMARY KEY (id), 
	CONSTRAINT fk_party_contacts_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE CASCADE
);

CREATE INDEX ix_party_contacts_party_id ON party_contacts (party_id);

CREATE UNIQUE INDEX uq_party_contacts_one_primary ON party_contacts (party_id) WHERE is_primary;

CREATE TABLE unit_conversions (
	id BIGSERIAL NOT NULL, 
	from_unit_id BIGINT NOT NULL, 
	to_unit_id BIGINT NOT NULL, 
	factor NUMERIC(20, 10) NOT NULL, 
	product_id BIGINT, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_unit_conversions PRIMARY KEY (id), 
	CONSTRAINT uq_unit_conversions_from_unit_id UNIQUE (from_unit_id, to_unit_id, product_id), 
	CONSTRAINT ck_unit_conversions_factor_positive CHECK (factor > 0), 
	CONSTRAINT ck_unit_conversions_distinct_units CHECK (from_unit_id <> to_unit_id), 
	CONSTRAINT fk_unit_conversions_from_unit_id_units_of_measure FOREIGN KEY(from_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_unit_conversions_to_unit_id_units_of_measure FOREIGN KEY(to_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_unit_conversions_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_unit_conversions_product_id ON unit_conversions (product_id);

CREATE UNIQUE INDEX uq_unit_conversions_universal ON unit_conversions (from_unit_id, to_unit_id) WHERE product_id IS NULL;

CREATE TABLE coffee_profiles (
	id BIGSERIAL NOT NULL, 
	product_id BIGINT NOT NULL, 
	variety VARCHAR(80), 
	process_method VARCHAR(30), 
	roast_level VARCHAR(20), 
	grind_type VARCHAR(20), 
	altitude_min_masl INTEGER, 
	altitude_max_masl INTEGER, 
	cupping_score NUMERIC(5, 2), 
	sensory_notes TEXT, 
	packaging_grams NUMERIC(10, 2), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_coffee_profiles PRIMARY KEY (id), 
	CONSTRAINT uq_coffee_profiles_product_id UNIQUE (product_id), 
	CONSTRAINT ck_coffee_profiles_process_method_valid CHECK (process_method IS NULL OR process_method IN ('ANAEROBICO','HONEY','LAVADO','NATURAL','OTRO')), 
	CONSTRAINT ck_coffee_profiles_roast_level_valid CHECK (roast_level IS NULL OR roast_level IN ('CLARO','MEDIO','MEDIO_OSCURO','OSCURO')), 
	CONSTRAINT ck_coffee_profiles_grind_type_valid CHECK (grind_type IS NULL OR grind_type IN ('EXPRESO','FINO','GRANO','GRUESO','MEDIO')), 
	CONSTRAINT ck_coffee_profiles_cupping_score_range CHECK (cupping_score IS NULL OR (cupping_score >= 0 AND cupping_score <= 100)), 
	CONSTRAINT ck_coffee_profiles_altitude_range CHECK (altitude_min_masl IS NULL OR altitude_max_masl IS NULL OR altitude_max_masl >= altitude_min_masl), 
	CONSTRAINT ck_coffee_profiles_packaging_positive CHECK (packaging_grams IS NULL OR packaging_grams > 0), 
	CONSTRAINT fk_coffee_profiles_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE TABLE price_list_items (
	id BIGSERIAL NOT NULL, 
	price_list_id BIGINT NOT NULL, 
	product_id BIGINT NOT NULL, 
	unit_id BIGINT NOT NULL, 
	unit_price NUMERIC(16, 4) NOT NULL, 
	min_quantity NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	max_quantity NUMERIC(16, 4), 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_price_list_items PRIMARY KEY (id), 
	CONSTRAINT ck_price_list_items_unit_price_non_negative CHECK (unit_price >= 0), 
	CONSTRAINT ck_price_list_items_min_quantity_non_negative CHECK (min_quantity >= 0), 
	CONSTRAINT ck_price_list_items_quantity_range CHECK (max_quantity IS NULL OR max_quantity >= min_quantity), 
	CONSTRAINT ck_price_list_items_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT price_list_items_no_overlap EXCLUDE USING gist (price_list_id WITH =, product_id WITH =, unit_id WITH =, numrange(min_quantity, COALESCE(max_quantity, 'infinity'::numeric), '[]') WITH &&, daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]') WITH &&), 
	CONSTRAINT fk_price_list_items_price_list_id_price_lists FOREIGN KEY(price_list_id) REFERENCES price_lists (id) ON DELETE CASCADE, 
	CONSTRAINT fk_price_list_items_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_price_list_items_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_price_list_items_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_price_list_items_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_price_list_items_lookup ON price_list_items (price_list_id, product_id, valid_from, valid_to);

CREATE TABLE party_price_rules (
	id BIGSERIAL NOT NULL, 
	party_id BIGINT NOT NULL, 
	rule_type VARCHAR(25) NOT NULL, 
	price_list_id BIGINT, 
	product_id BIGINT, 
	category_id BIGINT, 
	unit_id BIGINT, 
	value NUMERIC(16, 4), 
	min_quantity NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	priority SMALLINT DEFAULT '100' NOT NULL, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_party_price_rules PRIMARY KEY (id), 
	CONSTRAINT ck_party_price_rules_rule_type_valid CHECK (rule_type IN ('DISCOUNT_AMOUNT', 'DISCOUNT_PCT', 'FIXED_PRICE', 'LIST_ASSIGNMENT')), 
	CONSTRAINT ck_party_price_rules_list_assignment_requires_list CHECK (rule_type <> 'LIST_ASSIGNMENT' OR price_list_id IS NOT NULL), 
	CONSTRAINT ck_party_price_rules_fixed_price_requires_value_unit CHECK (rule_type <> 'FIXED_PRICE' OR (value IS NOT NULL AND unit_id IS NOT NULL)), 
	CONSTRAINT ck_party_price_rules_discount_requires_value CHECK (rule_type NOT IN ('DISCOUNT_PCT','DISCOUNT_AMOUNT') OR value IS NOT NULL), 
	CONSTRAINT ck_party_price_rules_product_xor_category CHECK (product_id IS NULL OR category_id IS NULL), 
	CONSTRAINT ck_party_price_rules_discount_pct_fraction CHECK (rule_type <> 'DISCOUNT_PCT' OR (value >= 0 AND value <= 1)), 
	CONSTRAINT ck_party_price_rules_min_quantity_non_negative CHECK (min_quantity >= 0), 
	CONSTRAINT ck_party_price_rules_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT fk_party_price_rules_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE CASCADE, 
	CONSTRAINT fk_party_price_rules_price_list_id_price_lists FOREIGN KEY(price_list_id) REFERENCES price_lists (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_party_price_rules_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	CONSTRAINT fk_party_price_rules_category_id_product_categories FOREIGN KEY(category_id) REFERENCES product_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_party_price_rules_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_party_price_rules_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_party_price_rules_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_party_price_rules_party_id ON party_price_rules (party_id, rule_type, priority);

CREATE TABLE intermediary_fee_rules (
	id BIGSERIAL NOT NULL, 
	party_id BIGINT NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	calculation_basis VARCHAR(25) NOT NULL, 
	value NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT, 
	product_id BIGINT, 
	category_id BIGINT, 
	min_fee_amount NUMERIC(16, 2), 
	max_fee_amount NUMERIC(16, 2), 
	priority SMALLINT DEFAULT '100' NOT NULL, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_intermediary_fee_rules PRIMARY KEY (id), 
	CONSTRAINT ck_intermediary_fee_rules_calculation_basis_valid CHECK (calculation_basis IN ('FLAT_PER_SALE', 'PCT_OF_MARGIN', 'PCT_OF_SALE_TOTAL', 'PER_UNIT')), 
	CONSTRAINT ck_intermediary_fee_rules_value_non_negative CHECK (value >= 0), 
	CONSTRAINT ck_intermediary_fee_rules_per_unit_requires_unit CHECK (calculation_basis <> 'PER_UNIT' OR unit_id IS NOT NULL), 
	CONSTRAINT ck_intermediary_fee_rules_fee_amount_range CHECK (max_fee_amount IS NULL OR min_fee_amount IS NULL OR max_fee_amount >= min_fee_amount), 
	CONSTRAINT ck_intermediary_fee_rules_pct_fraction CHECK (calculation_basis NOT LIKE 'PCT%%' OR value <= 1), 
	CONSTRAINT ck_intermediary_fee_rules_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT fk_intermediary_fee_rules_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE CASCADE, 
	CONSTRAINT fk_intermediary_fee_rules_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intermediary_fee_rules_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intermediary_fee_rules_category_id_product_categories FOREIGN KEY(category_id) REFERENCES product_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intermediary_fee_rules_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intermediary_fee_rules_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_intermediary_fee_rules_party_id ON intermediary_fee_rules (party_id, priority, valid_to);

CREATE TABLE production_orders (
	id BIGSERIAL NOT NULL, 
	order_number VARCHAR(30) NOT NULL, 
	status VARCHAR(20) DEFAULT 'DRAFT' NOT NULL, 
	target_product_id BIGINT, 
	planned_quantity NUMERIC(16, 4), 
	unit_id BIGINT, 
	planned_start_date DATE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	total_input_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total_process_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total_overhead_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	output_quantity_base NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	waste_quantity_base NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	yield_pct NUMERIC(9, 6), 
	unit_cost NUMERIC(16, 4), 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_production_orders PRIMARY KEY (id), 
	CONSTRAINT uq_production_orders_order_number UNIQUE (order_number), 
	CONSTRAINT ck_production_orders_status_valid CHECK (status IN ('CANCELLED', 'CLOSED', 'COMPLETED', 'DRAFT', 'IN_PROGRESS', 'RELEASED')), 
	CONSTRAINT ck_production_orders_planned_quantity_positive CHECK (planned_quantity IS NULL OR planned_quantity > 0), 
	CONSTRAINT ck_production_orders_total_input_cost_non_negative CHECK (total_input_cost >= 0), 
	CONSTRAINT ck_production_orders_total_process_cost_non_negative CHECK (total_process_cost >= 0), 
	CONSTRAINT ck_production_orders_total_overhead_cost_non_negative CHECK (total_overhead_cost >= 0), 
	CONSTRAINT ck_production_orders_total_cost_non_negative CHECK (total_cost >= 0), 
	CONSTRAINT ck_production_orders_output_quantity_base_non_negative CHECK (output_quantity_base >= 0), 
	CONSTRAINT ck_production_orders_waste_quantity_base_non_negative CHECK (waste_quantity_base >= 0), 
	CONSTRAINT ck_production_orders_dates_order CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at), 
	CONSTRAINT fk_production_orders_target_product_id_products FOREIGN KEY(target_product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_orders_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_orders_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_production_orders_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_production_orders_dates ON production_orders (started_at, completed_at);

CREATE INDEX ix_production_orders_status ON production_orders (status);

CREATE TABLE cost_rules (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(150) NOT NULL, 
	cost_category_id BIGINT NOT NULL, 
	applies_to VARCHAR(30) NOT NULL, 
	process_id BIGINT, 
	product_id BIGINT, 
	executor_type VARCHAR(20), 
	executor_party_id BIGINT, 
	calculation_basis VARCHAR(30) NOT NULL, 
	unit_id BIGINT, 
	rate NUMERIC(16, 4) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	min_charge NUMERIC(16, 2), 
	max_charge NUMERIC(16, 2), 
	min_quantity NUMERIC(16, 4), 
	priority SMALLINT DEFAULT '100' NOT NULL, 
	valid_from DATE NOT NULL, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	valid_to DATE, 
	CONSTRAINT pk_cost_rules PRIMARY KEY (id), 
	CONSTRAINT uq_cost_rules_code UNIQUE (code), 
	CONSTRAINT ck_cost_rules_applies_to_valid CHECK (applies_to IN ('ORDER', 'PROCESS', 'PRODUCT', 'SALE', 'SHIPMENT')), 
	CONSTRAINT ck_cost_rules_calculation_basis_valid CHECK (calculation_basis IN ('FLAT', 'PCT_OF_INPUT_COST', 'PER_HOUR', 'PER_UNIT_INPUT', 'PER_UNIT_OUTPUT')), 
	CONSTRAINT ck_cost_rules_executor_type_valid CHECK (executor_type IS NULL OR executor_type IN ('EXTERNAL','INTERNAL')), 
	CONSTRAINT ck_cost_rules_process_required CHECK (applies_to <> 'PROCESS' OR process_id IS NOT NULL), 
	CONSTRAINT ck_cost_rules_unit_required CHECK (calculation_basis IN ('FLAT','PCT_OF_INPUT_COST') OR unit_id IS NOT NULL), 
	CONSTRAINT ck_cost_rules_charge_range CHECK (max_charge IS NULL OR min_charge IS NULL OR max_charge >= min_charge), 
	CONSTRAINT ck_cost_rules_min_quantity_positive CHECK (min_quantity IS NULL OR min_quantity > 0), 
	CONSTRAINT ck_cost_rules_rate_non_negative CHECK (rate >= 0), 
	CONSTRAINT ck_cost_rules_validity_range CHECK (valid_to IS NULL OR valid_to >= valid_from), 
	CONSTRAINT cost_rules_no_overlap EXCLUDE USING gist (process_id WITH =, executor_party_id WITH =, product_id WITH =, daterange(valid_from, COALESCE(valid_to, 'infinity'::date), '[]') WITH &&), 
	CONSTRAINT fk_cost_rules_cost_category_id_cost_categories FOREIGN KEY(cost_category_id) REFERENCES cost_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_rules_process_id_production_processes FOREIGN KEY(process_id) REFERENCES production_processes (id) ON DELETE CASCADE, 
	CONSTRAINT fk_cost_rules_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	CONSTRAINT fk_cost_rules_executor_party_id_parties FOREIGN KEY(executor_party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_rules_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_rules_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cost_rules_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_cost_rules_executor ON cost_rules (executor_party_id);

CREATE INDEX ix_cost_rules_lookup ON cost_rules (applies_to, process_id, valid_from, valid_to);

CREATE TABLE payments (
	id BIGSERIAL NOT NULL, 
	payment_number VARCHAR(30) NOT NULL, 
	party_id BIGINT NOT NULL, 
	direction VARCHAR(15) NOT NULL, 
	payment_date DATE NOT NULL, 
	method VARCHAR(25) NOT NULL, 
	amount NUMERIC(16, 2) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	allocated_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	unallocated_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	status VARCHAR(20) DEFAULT 'CONFIRMED' NOT NULL, 
	reference VARCHAR(80), 
	bank_account VARCHAR(60), 
	receipt_path VARCHAR(255), 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_payments PRIMARY KEY (id), 
	CONSTRAINT uq_payments_payment_number UNIQUE (payment_number), 
	CONSTRAINT ck_payments_direction_valid CHECK (direction IN ('INBOUND', 'OUTBOUND')), 
	CONSTRAINT ck_payments_method_valid CHECK (method IN ('CHEQUE', 'CREDITO', 'DAVIPLATA', 'EFECTIVO', 'NEQUI', 'OTRO', 'PSE', 'TARJETA', 'TRANSFERENCIA')), 
	CONSTRAINT ck_payments_status_valid CHECK (status IN ('CONFIRMED', 'PENDING', 'REVERSED')), 
	CONSTRAINT ck_payments_amount_positive CHECK (amount > 0), 
	CONSTRAINT ck_payments_allocated_non_negative CHECK (allocated_amount >= 0), 
	CONSTRAINT ck_payments_unallocated_non_negative CHECK (unallocated_amount >= 0), 
	CONSTRAINT fk_payments_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_payments_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_payments_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_payments_status ON payments (status);

CREATE INDEX ix_payments_party ON payments (party_id, payment_date DESC);

CREATE TABLE expense_categories (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	parent_id BIGINT, 
	expense_nature VARCHAR(25) NOT NULL, 
	is_cost_of_sales BOOLEAN DEFAULT 'false' NOT NULL, 
	default_cost_category_id BIGINT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_expense_categories PRIMARY KEY (id), 
	CONSTRAINT uq_expense_categories_code UNIQUE (code), 
	CONSTRAINT ck_expense_categories_expense_nature_valid CHECK (expense_nature IN ('ADMINISTRATIVE', 'FINANCIAL', 'OPERATIONAL', 'OTHER', 'SALES', 'TAX')), 
	CONSTRAINT ck_expense_categories_no_self_parent CHECK (parent_id IS NULL OR parent_id <> id), 
	CONSTRAINT fk_expense_categories_parent_id_expense_categories FOREIGN KEY(parent_id) REFERENCES expense_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_expense_categories_default_cost_category_id_cost_categories FOREIGN KEY(default_cost_category_id) REFERENCES cost_categories (id) ON DELETE SET NULL, 
	CONSTRAINT fk_expense_categories_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_expense_categories_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_expense_categories_parent_id ON expense_categories (parent_id);

CREATE TABLE inventory_locations (
	id BIGSERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	location_type VARCHAR(30) NOT NULL, 
	party_id BIGINT, 
	address_id BIGINT, 
	allows_negative_stock BOOLEAN DEFAULT 'false' NOT NULL, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
	CONSTRAINT pk_inventory_locations PRIMARY KEY (id), 
	CONSTRAINT uq_inventory_locations_code UNIQUE (code), 
	CONSTRAINT ck_inventory_locations_location_type_valid CHECK (location_type IN ('CONSIGNMENT', 'CUSTOMER', 'IN_TRANSIT', 'PROCESSOR', 'SCRAP', 'VIRTUAL', 'WAREHOUSE')), 
	CONSTRAINT ck_inventory_locations_third_party_requires_party CHECK (location_type NOT IN ('PROCESSOR','CONSIGNMENT') OR party_id IS NOT NULL), 
	CONSTRAINT fk_inventory_locations_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_locations_address_id_addresses FOREIGN KEY(address_id) REFERENCES addresses (id) ON DELETE SET NULL, 
	CONSTRAINT fk_inventory_locations_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_inventory_locations_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_inventory_locations_party_id ON inventory_locations (party_id);

CREATE INDEX ix_inventory_locations_location_type ON inventory_locations (location_type);

CREATE TABLE batches (
	id BIGSERIAL NOT NULL, 
	batch_code VARCHAR(40) NOT NULL, 
	product_id BIGINT NOT NULL, 
	batch_type VARCHAR(25) NOT NULL, 
	origin_party_id BIGINT, 
	origin_address_id BIGINT, 
	farm_name VARCHAR(150), 
	municipality_name VARCHAR(100), 
	harvest_year SMALLINT, 
	harvest_period VARCHAR(20), 
	production_order_id BIGINT, 
	purchase_item_id BIGINT, 
	initial_quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	unit_cost NUMERIC(16, 4) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	humidity_pct NUMERIC(5, 2), 
	defect_pct NUMERIC(5, 2), 
	cupping_score NUMERIC(5, 2), 
	received_date DATE, 
	production_date DATE, 
	expiry_date DATE, 
	status VARCHAR(20) DEFAULT 'ACTIVE' NOT NULL, 
	quality_notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_batches PRIMARY KEY (id), 
	CONSTRAINT uq_batches_batch_code UNIQUE (batch_code), 
	CONSTRAINT ck_batches_batch_type_valid CHECK (batch_type IN ('ADJUSTED', 'PRODUCED', 'PURCHASED')), 
	CONSTRAINT ck_batches_status_valid CHECK (status IN ('ACTIVE', 'BLOCKED', 'DEPLETED', 'EXPIRED')), 
	CONSTRAINT ck_batches_harvest_period_valid CHECK (harvest_period IS NULL OR harvest_period IN ('PRINCIPAL','TRAVIESA')), 
	CONSTRAINT ck_batches_initial_quantity_positive CHECK (initial_quantity > 0), 
	CONSTRAINT ck_batches_unit_cost_non_negative CHECK (unit_cost >= 0), 
	CONSTRAINT ck_batches_humidity_pct_range CHECK (humidity_pct IS NULL OR (humidity_pct >= 0 AND humidity_pct <= 100)), 
	CONSTRAINT ck_batches_defect_pct_range CHECK (defect_pct IS NULL OR (defect_pct >= 0 AND defect_pct <= 100)), 
	CONSTRAINT ck_batches_produced_requires_order CHECK (batch_type <> 'PRODUCED' OR production_order_id IS NOT NULL), 
	CONSTRAINT ck_batches_expiry_after_production CHECK (expiry_date IS NULL OR production_date IS NULL OR expiry_date >= production_date), 
	CONSTRAINT fk_batches_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_batches_origin_party_id_parties FOREIGN KEY(origin_party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_batches_origin_address_id_addresses FOREIGN KEY(origin_address_id) REFERENCES addresses (id) ON DELETE SET NULL, 
	CONSTRAINT fk_batches_production_order_id_production_orders FOREIGN KEY(production_order_id) REFERENCES production_orders (id) ON DELETE SET NULL, 
	CONSTRAINT fk_batches_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_batches_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_batches_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_batches_harvest_year ON batches (harvest_year);

CREATE INDEX ix_batches_product ON batches (product_id, status);

CREATE INDEX ix_batches_origin_party ON batches (origin_party_id);

CREATE TABLE sales (
	id BIGSERIAL NOT NULL, 
	sale_number VARCHAR(30) NOT NULL, 
	party_id BIGINT NOT NULL, 
	channel VARCHAR(25) NOT NULL, 
	intermediary_party_id BIGINT, 
	price_list_id BIGINT, 
	salesperson_user_id BIGINT, 
	sale_date DATE NOT NULL, 
	status VARCHAR(20) DEFAULT 'DRAFT' NOT NULL, 
	payment_status VARCHAR(20) DEFAULT 'UNPAID' NOT NULL, 
	payment_term_days SMALLINT DEFAULT '0' NOT NULL, 
	due_date DATE, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	subtotal NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	discount_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	tax_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	paid_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	cost_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	margin_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	margin_pct NUMERIC(9, 6), 
	freight_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	shipping_address_id BIGINT, 
	confirmed_at TIMESTAMP WITH TIME ZONE, 
	cancelled_at TIMESTAMP WITH TIME ZONE, 
	cancellation_reason TEXT, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_sales PRIMARY KEY (id), 
	CONSTRAINT uq_sales_sale_number UNIQUE (sale_number), 
	CONSTRAINT ck_sales_channel_valid CHECK (channel IN ('CAFETERIA', 'EVENT', 'INTERMEDIARY', 'ONLINE', 'RETAIL', 'WHOLESALE')), 
	CONSTRAINT ck_sales_status_valid CHECK (status IN ('CANCELLED', 'CONFIRMED', 'DELIVERED', 'DISPATCHED', 'DRAFT', 'RETURNED')), 
	CONSTRAINT ck_sales_payment_status_valid CHECK (payment_status IN ('OVERDUE', 'PAID', 'PARTIAL', 'UNPAID')), 
	CONSTRAINT ck_sales_intermediary_not_customer CHECK (intermediary_party_id IS NULL OR intermediary_party_id <> party_id), 
	CONSTRAINT ck_sales_total_non_negative CHECK (total >= 0), 
	CONSTRAINT ck_sales_cancelled_requires_timestamp CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL), 
	CONSTRAINT ck_sales_payment_term_non_negative CHECK (payment_term_days >= 0), 
	CONSTRAINT fk_sales_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_intermediary_party_id_parties FOREIGN KEY(intermediary_party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_price_list_id_price_lists FOREIGN KEY(price_list_id) REFERENCES price_lists (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_salesperson_user_id_users FOREIGN KEY(salesperson_user_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_sales_shipping_address_id_addresses FOREIGN KEY(shipping_address_id) REFERENCES addresses (id) ON DELETE SET NULL, 
	CONSTRAINT fk_sales_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_sales_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_sales_payment_status ON sales (payment_status, due_date);

CREATE INDEX ix_sales_date ON sales (sale_date DESC);

CREATE INDEX ix_sales_party_date ON sales (party_id, sale_date DESC);

CREATE INDEX ix_sales_channel ON sales (channel, sale_date);

CREATE INDEX ix_sales_status ON sales (status);

CREATE TABLE payment_allocations (
	id BIGSERIAL NOT NULL, 
	payment_id BIGINT NOT NULL, 
	target_type VARCHAR(20) NOT NULL, 
	target_id BIGINT NOT NULL, 
	amount NUMERIC(16, 2) NOT NULL, 
	allocated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_payment_allocations PRIMARY KEY (id), 
	CONSTRAINT uq_payment_allocations_payment_id UNIQUE (payment_id, target_type, target_id), 
	CONSTRAINT ck_payment_allocations_target_type_valid CHECK (target_type IN ('EXPENSE', 'FEE', 'INVOICE', 'PURCHASE', 'SALE')), 
	CONSTRAINT ck_payment_allocations_amount_positive CHECK (amount > 0), 
	CONSTRAINT fk_payment_allocations_payment_id_payments FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE CASCADE
);

CREATE INDEX ix_payment_allocations_target ON payment_allocations (target_type, target_id);

CREATE TABLE expenses (
	id BIGSERIAL NOT NULL, 
	expense_number VARCHAR(30) NOT NULL, 
	category_id BIGINT NOT NULL, 
	party_id BIGINT, 
	expense_date DATE NOT NULL, 
	accounting_date DATE NOT NULL, 
	description VARCHAR(255) NOT NULL, 
	subtotal NUMERIC(16, 2) NOT NULL, 
	tax_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	withholding_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total NUMERIC(16, 2) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	payment_method VARCHAR(25), 
	payment_status VARCHAR(20) DEFAULT 'UNPAID' NOT NULL, 
	document_type VARCHAR(30), 
	document_number VARCHAR(40), 
	is_capitalizable BOOLEAN DEFAULT 'false' NOT NULL, 
	is_recurring BOOLEAN DEFAULT 'false' NOT NULL, 
	attachment_path VARCHAR(255), 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_expenses PRIMARY KEY (id), 
	CONSTRAINT uq_expenses_expense_number UNIQUE (expense_number), 
	CONSTRAINT ck_expenses_payment_status_valid CHECK (payment_status IN ('PAID', 'PARTIAL', 'UNPAID')), 
	CONSTRAINT ck_expenses_payment_method_valid CHECK (payment_method IS NULL OR payment_method IN ('CHEQUE','CREDITO','DAVIPLATA','EFECTIVO','NEQUI','OTRO','PSE','TARJETA','TRANSFERENCIA')), 
	CONSTRAINT ck_expenses_document_type_valid CHECK (document_type IS NULL OR document_type IN ('DOCUMENTO_SOPORTE','FACTURA','NINGUNO','NOMINA','RECIBO')), 
	CONSTRAINT ck_expenses_subtotal_non_negative CHECK (subtotal >= 0), 
	CONSTRAINT ck_expenses_tax_amount_non_negative CHECK (tax_amount >= 0), 
	CONSTRAINT ck_expenses_withholding_non_negative CHECK (withholding_amount >= 0), 
	CONSTRAINT fk_expenses_category_id_expense_categories FOREIGN KEY(category_id) REFERENCES expense_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_expenses_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_expenses_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_expenses_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_expenses_category_date ON expenses (category_id, accounting_date);

CREATE INDEX ix_expenses_accounting_date ON expenses (accounting_date DESC);

CREATE INDEX ix_expenses_party ON expenses (party_id);

CREATE TABLE intermediary_fee_entries (
	id BIGSERIAL NOT NULL, 
	party_id BIGINT NOT NULL, 
	sale_id BIGINT NOT NULL, 
	rule_id BIGINT, 
	calculation_basis VARCHAR(25) NOT NULL, 
	rule_value NUMERIC(16, 4) NOT NULL, 
	base_amount NUMERIC(16, 2) NOT NULL, 
	fee_amount NUMERIC(16, 2) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	status VARCHAR(20) DEFAULT 'ACCRUED' NOT NULL, 
	accrued_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	settled_at TIMESTAMP WITH TIME ZONE, 
	expense_id BIGINT, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_intermediary_fee_entries PRIMARY KEY (id), 
	CONSTRAINT ck_intermediary_fee_entries_calculation_basis_valid CHECK (calculation_basis IN ('FLAT_PER_SALE', 'PCT_OF_MARGIN', 'PCT_OF_SALE_TOTAL', 'PER_UNIT')), 
	CONSTRAINT ck_intermediary_fee_entries_status_valid CHECK (status IN ('ACCRUED', 'APPROVED', 'CANCELLED', 'PAID')), 
	CONSTRAINT ck_intermediary_fee_entries_fee_amount_non_negative CHECK (fee_amount >= 0), 
	CONSTRAINT ck_intermediary_fee_entries_settled_after_accrued CHECK (settled_at IS NULL OR settled_at >= accrued_at), 
	CONSTRAINT fk_intermediary_fee_entries_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intermediary_fee_entries_sale_id_sales FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_intermediary_fee_entries_rule_id_intermediary_fee_rules FOREIGN KEY(rule_id) REFERENCES intermediary_fee_rules (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intermediary_fee_entries_expense_id_expenses FOREIGN KEY(expense_id) REFERENCES expenses (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intermediary_fee_entries_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_intermediary_fee_entries_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_ife_party_status ON intermediary_fee_entries (party_id, status);

CREATE INDEX ix_ife_sale ON intermediary_fee_entries (sale_id);

CREATE TABLE purchases (
	id BIGSERIAL NOT NULL, 
	purchase_number VARCHAR(30) NOT NULL, 
	party_id BIGINT NOT NULL, 
	purchase_type VARCHAR(25) NOT NULL, 
	purchase_date DATE NOT NULL, 
	status VARCHAR(20) DEFAULT 'DRAFT' NOT NULL, 
	destination_location_id BIGINT, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	subtotal NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	discount_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	tax_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	withholding_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	freight_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	payment_status VARCHAR(20) DEFAULT 'UNPAID' NOT NULL, 
	supplier_document_type VARCHAR(30), 
	supplier_document_number VARCHAR(40), 
	received_at TIMESTAMP WITH TIME ZONE, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_purchases PRIMARY KEY (id), 
	CONSTRAINT uq_purchases_purchase_number UNIQUE (purchase_number), 
	CONSTRAINT ck_purchases_purchase_type_valid CHECK (purchase_type IN ('ASSET', 'COFFEE_GROWER', 'SERVICE', 'SUPPLIER')), 
	CONSTRAINT ck_purchases_status_valid CHECK (status IN ('CANCELLED', 'CONFIRMED', 'DRAFT', 'RECEIVED')), 
	CONSTRAINT ck_purchases_payment_status_valid CHECK (payment_status IN ('PAID', 'PARTIAL', 'UNPAID')), 
	CONSTRAINT ck_purchases_supplier_document_type_valid CHECK (supplier_document_type IS NULL OR supplier_document_type IN ('DOCUMENTO_SOPORTE','FACTURA','NINGUNO','RECIBO')), 
	CONSTRAINT ck_purchases_subtotal_non_negative CHECK (subtotal >= 0), 
	CONSTRAINT ck_purchases_discount_total_non_negative CHECK (discount_total >= 0), 
	CONSTRAINT ck_purchases_tax_total_non_negative CHECK (tax_total >= 0), 
	CONSTRAINT ck_purchases_withholding_total_non_negative CHECK (withholding_total >= 0), 
	CONSTRAINT ck_purchases_freight_amount_non_negative CHECK (freight_amount >= 0), 
	CONSTRAINT ck_purchases_total_non_negative CHECK (total >= 0), 
	CONSTRAINT fk_purchases_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_purchases_destination_location_id_inventory_locations FOREIGN KEY(destination_location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_purchases_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_purchases_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_purchases_status ON purchases (status);

CREATE INDEX ix_purchases_party_date ON purchases (party_id, purchase_date);

CREATE TABLE inventory_movements (
	id BIGSERIAL NOT NULL, 
	movement_type VARCHAR(35) NOT NULL, 
	direction SMALLINT NOT NULL, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	location_id BIGINT NOT NULL, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	unit_cost NUMERIC(16, 4), 
	total_cost NUMERIC(16, 2), 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reference_type VARCHAR(30), 
	reference_id BIGINT, 
	counterpart_movement_id BIGINT, 
	reverses_movement_id BIGINT, 
	reason_code VARCHAR(30), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by_id BIGINT, 
	CONSTRAINT pk_inventory_movements PRIMARY KEY (id), 
	CONSTRAINT ck_inventory_movements_movement_type_valid CHECK (movement_type IN ('IN_ADJUSTMENT', 'IN_PRODUCTION', 'IN_PURCHASE', 'IN_SALE_RETURN', 'IN_TRANSFER', 'IN_WASTE_RECOVERY', 'OUT_ADJUSTMENT', 'OUT_PRODUCTION', 'OUT_PURCHASE_RETURN', 'OUT_SALE', 'OUT_SAMPLE', 'OUT_TRANSFER', 'OUT_WASTE')), 
	CONSTRAINT ck_inventory_movements_direction_valid CHECK (direction IN (1, -1)), 
	CONSTRAINT ck_inventory_movements_type_direction CHECK ((movement_type IN ('IN_ADJUSTMENT', 'IN_PRODUCTION', 'IN_PURCHASE', 'IN_SALE_RETURN', 'IN_TRANSFER', 'IN_WASTE_RECOVERY') AND direction = 1) OR (movement_type IN ('OUT_ADJUSTMENT', 'OUT_PRODUCTION', 'OUT_PURCHASE_RETURN', 'OUT_SALE', 'OUT_SAMPLE', 'OUT_TRANSFER', 'OUT_WASTE') AND direction = -1)), 
	CONSTRAINT ck_inventory_movements_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_inventory_movements_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_inventory_movements_unit_cost_non_negative CHECK (unit_cost IS NULL OR unit_cost >= 0), 
	CONSTRAINT ck_inventory_movements_reference_type_valid CHECK (reference_type IS NULL OR reference_type IN ('ADJUSTMENT', 'COUNT', 'PRODUCTION_INPUT', 'PRODUCTION_OUTPUT', 'PRODUCTION_WASTE', 'PURCHASE_ITEM', 'SALE_ITEM_BATCH', 'SHIPMENT_ITEM', 'TRANSFER')), 
	CONSTRAINT ck_inventory_movements_reference_id_required CHECK (reference_type IS NULL OR reference_id IS NOT NULL), 
	CONSTRAINT ck_inventory_movements_reason_code_valid CHECK (reason_code IS NULL OR reason_code IN ('CONTEO_FISICO', 'DANO', 'ERROR_REGISTRO', 'MUESTRA', 'OBSEQUIO', 'ROBO')), 
	CONSTRAINT fk_inventory_movements_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_location_id_inventory_locations FOREIGN KEY(location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_counterpart FOREIGN KEY(counterpart_movement_id) REFERENCES inventory_movements (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_reverses FOREIGN KEY(reverses_movement_id) REFERENCES inventory_movements (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_inventory_movements_occurred ON inventory_movements (occurred_at DESC);

CREATE INDEX ix_inventory_movements_type ON inventory_movements (movement_type);

CREATE INDEX ix_inventory_movements_lookup ON inventory_movements (product_id, batch_id, location_id, occurred_at);

CREATE INDEX ix_inventory_movements_reference ON inventory_movements (reference_type, reference_id);

CREATE TABLE batch_lineage (
	id BIGSERIAL NOT NULL, 
	child_batch_id BIGINT NOT NULL, 
	parent_batch_id BIGINT NOT NULL, 
	quantity_consumed NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	contribution_pct NUMERIC(9, 6), 
	production_order_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_batch_lineage PRIMARY KEY (id), 
	CONSTRAINT uq_batch_lineage_child_batch_id UNIQUE (child_batch_id, parent_batch_id), 
	CONSTRAINT ck_batch_lineage_no_self_parent CHECK (child_batch_id <> parent_batch_id), 
	CONSTRAINT ck_batch_lineage_quantity_consumed_positive CHECK (quantity_consumed > 0), 
	CONSTRAINT ck_batch_lineage_contribution_pct_fraction CHECK (contribution_pct IS NULL OR (contribution_pct >= 0 AND contribution_pct <= 1)), 
	CONSTRAINT fk_batch_lineage_child_batch_id_batches FOREIGN KEY(child_batch_id) REFERENCES batches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_batch_lineage_parent_batch_id_batches FOREIGN KEY(parent_batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_batch_lineage_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_batch_lineage_production_order_id_production_orders FOREIGN KEY(production_order_id) REFERENCES production_orders (id) ON DELETE SET NULL
);

CREATE INDEX ix_batch_lineage_parent_batch_id ON batch_lineage (parent_batch_id);

CREATE INDEX ix_batch_lineage_child_batch_id ON batch_lineage (child_batch_id);

CREATE TABLE process_executions (
	id BIGSERIAL NOT NULL, 
	production_order_id BIGINT NOT NULL, 
	process_id BIGINT NOT NULL, 
	sequence_no SMALLINT NOT NULL, 
	executor_type VARCHAR(20) NOT NULL, 
	executor_party_id BIGINT, 
	location_id BIGINT, 
	status VARCHAR(20) DEFAULT 'PENDING' NOT NULL, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	received_at TIMESTAMP WITH TIME ZONE, 
	input_quantity_base NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	output_quantity_base NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	waste_quantity_base NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	yield_pct NUMERIC(9, 6), 
	cost_rule_id BIGINT, 
	cost_unit_id BIGINT, 
	cost_rate NUMERIC(16, 4), 
	cost_basis VARCHAR(30), 
	chargeable_quantity NUMERIC(16, 4), 
	computed_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	actual_cost NUMERIC(16, 2), 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	supplier_document_number VARCHAR(40), 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_process_executions PRIMARY KEY (id), 
	CONSTRAINT uq_process_executions_production_order_id UNIQUE (production_order_id, sequence_no), 
	CONSTRAINT ck_process_executions_executor_type_valid CHECK (executor_type IN ('EXTERNAL', 'INTERNAL')), 
	CONSTRAINT ck_process_executions_status_valid CHECK (status IN ('CANCELLED', 'DONE', 'IN_PROGRESS', 'PENDING', 'RECEIVED', 'SENT')), 
	CONSTRAINT ck_process_executions_executor_coherent CHECK ((executor_type = 'EXTERNAL' AND executor_party_id IS NOT NULL) OR (executor_type = 'INTERNAL' AND executor_party_id IS NULL)), 
	CONSTRAINT ck_process_executions_mass_balance CHECK (output_quantity_base + waste_quantity_base <= input_quantity_base), 
	CONSTRAINT ck_process_executions_input_quantity_base_non_negative CHECK (input_quantity_base >= 0), 
	CONSTRAINT ck_process_executions_output_quantity_base_non_negative CHECK (output_quantity_base >= 0), 
	CONSTRAINT ck_process_executions_waste_quantity_base_non_negative CHECK (waste_quantity_base >= 0), 
	CONSTRAINT ck_process_executions_computed_cost_non_negative CHECK (computed_cost >= 0), 
	CONSTRAINT ck_process_executions_cost_rate_non_negative CHECK (cost_rate IS NULL OR cost_rate >= 0), 
	CONSTRAINT ck_process_executions_sequence_positive CHECK (sequence_no > 0), 
	CONSTRAINT fk_process_executions_production_order_id_production_orders FOREIGN KEY(production_order_id) REFERENCES production_orders (id) ON DELETE CASCADE, 
	CONSTRAINT fk_process_executions_process_id_production_processes FOREIGN KEY(process_id) REFERENCES production_processes (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_process_executions_executor_party_id_parties FOREIGN KEY(executor_party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_process_executions_location_id_inventory_locations FOREIGN KEY(location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_process_executions_cost_rule_id_cost_rules FOREIGN KEY(cost_rule_id) REFERENCES cost_rules (id) ON DELETE SET NULL, 
	CONSTRAINT fk_process_executions_cost_unit_id_units_of_measure FOREIGN KEY(cost_unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_process_executions_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_process_executions_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_process_executions_order ON process_executions (production_order_id, sequence_no);

CREATE INDEX ix_process_executions_status ON process_executions (status);

CREATE INDEX ix_process_executions_executor ON process_executions (executor_party_id, status);

CREATE TABLE cost_entries (
	id BIGSERIAL NOT NULL, 
	cost_category_id BIGINT NOT NULL, 
	cost_rule_id BIGINT, 
	cost_object_type VARCHAR(30) NOT NULL, 
	cost_object_id BIGINT, 
	amount NUMERIC(16, 2) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	quantity NUMERIC(16, 4), 
	unit_id BIGINT, 
	unit_rate NUMERIC(16, 4), 
	calculation_basis VARCHAR(30), 
	party_id BIGINT, 
	incurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	accounting_date DATE NOT NULL, 
	is_estimated BOOLEAN DEFAULT 'false' NOT NULL, 
	expense_id BIGINT, 
	reverses_entry_id BIGINT, 
	document_reference VARCHAR(60), 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_cost_entries PRIMARY KEY (id), 
	CONSTRAINT ck_cost_entries_cost_object_type_valid CHECK (cost_object_type IN ('BATCH', 'PARTY', 'PERIOD', 'PROCESS_EXECUTION', 'PRODUCT', 'PRODUCTION_ORDER', 'PURCHASE', 'SALE', 'SALE_ITEM', 'SHIPMENT')), 
	CONSTRAINT ck_cost_entries_calculation_basis_valid CHECK (calculation_basis IS NULL OR calculation_basis IN ('FLAT','PCT_OF_INPUT_COST','PER_HOUR','PER_UNIT_INPUT','PER_UNIT_OUTPUT')), 
	CONSTRAINT ck_cost_entries_amount_non_zero CHECK (amount <> 0), 
	CONSTRAINT ck_cost_entries_object_id_required CHECK (cost_object_id IS NOT NULL OR cost_object_type = 'PERIOD'), 
	CONSTRAINT ck_cost_entries_quantity_positive CHECK (quantity IS NULL OR quantity > 0), 
	CONSTRAINT ck_cost_entries_no_self_reversal CHECK (reverses_entry_id IS NULL OR reverses_entry_id <> id), 
	CONSTRAINT fk_cost_entries_cost_category_id_cost_categories FOREIGN KEY(cost_category_id) REFERENCES cost_categories (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_entries_cost_rule_id_cost_rules FOREIGN KEY(cost_rule_id) REFERENCES cost_rules (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cost_entries_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_entries_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_entries_expense_id_expenses FOREIGN KEY(expense_id) REFERENCES expenses (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cost_entries_reverses_entry_id_cost_entries FOREIGN KEY(reverses_entry_id) REFERENCES cost_entries (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cost_entries_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_cost_entries_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_cost_entries_object ON cost_entries (cost_object_type, cost_object_id);

CREATE INDEX ix_cost_entries_category ON cost_entries (cost_category_id, accounting_date);

CREATE INDEX ix_cost_entries_party ON cost_entries (party_id);

CREATE INDEX ix_cost_entries_accounting ON cost_entries (accounting_date);

CREATE TABLE sale_items (
	id BIGSERIAL NOT NULL, 
	sale_id BIGINT NOT NULL, 
	line_no SMALLINT NOT NULL, 
	product_id BIGINT NOT NULL, 
	description VARCHAR(255), 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	unit_price NUMERIC(16, 4) NOT NULL, 
	price_list_item_id BIGINT, 
	price_source VARCHAR(30) NOT NULL, 
	discount_pct NUMERIC(9, 6) DEFAULT '0' NOT NULL, 
	discount_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	tax_id BIGINT, 
	tax_rate NUMERIC(9, 6) DEFAULT '0' NOT NULL, 
	tax_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	subtotal NUMERIC(16, 2) NOT NULL, 
	total NUMERIC(16, 2) NOT NULL, 
	unit_cost NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	total_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	margin_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	costing_method_used VARCHAR(25), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_sale_items PRIMARY KEY (id), 
	CONSTRAINT uq_sale_items_sale_id UNIQUE (sale_id, line_no), 
	CONSTRAINT ck_sale_items_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_sale_items_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_sale_items_unit_price_non_negative CHECK (unit_price >= 0), 
	CONSTRAINT ck_sale_items_price_source_valid CHECK (price_source IN ('MANUAL', 'PARTY_RULE', 'PRICE_LIST')), 
	CONSTRAINT ck_sale_items_discount_pct_fraction CHECK (discount_pct >= 0 AND discount_pct <= 1), 
	CONSTRAINT fk_sale_items_sale_id_sales FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE CASCADE, 
	CONSTRAINT fk_sale_items_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sale_items_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sale_items_price_list_item_id_price_list_items FOREIGN KEY(price_list_item_id) REFERENCES price_list_items (id) ON DELETE SET NULL, 
	CONSTRAINT fk_sale_items_tax_id_taxes FOREIGN KEY(tax_id) REFERENCES taxes (id) ON DELETE RESTRICT
);

CREATE INDEX ix_sale_items_product ON sale_items (product_id);

CREATE INDEX ix_sale_items_sale ON sale_items (sale_id);

CREATE TABLE shipments (
	id BIGSERIAL NOT NULL, 
	shipment_number VARCHAR(30) NOT NULL, 
	sale_id BIGINT, 
	carrier_party_id BIGINT, 
	carrier_name VARCHAR(120), 
	shipment_type VARCHAR(25) NOT NULL, 
	origin_location_id BIGINT, 
	destination_location_id BIGINT, 
	destination_address_id BIGINT, 
	tracking_number VARCHAR(80), 
	tracking_url VARCHAR(255), 
	status VARCHAR(25) DEFAULT 'PENDING' NOT NULL, 
	dispatched_at TIMESTAMP WITH TIME ZONE, 
	estimated_delivery_date DATE, 
	delivered_at TIMESTAMP WITH TIME ZONE, 
	received_by VARCHAR(150), 
	total_weight_kg NUMERIC(16, 4), 
	package_count SMALLINT, 
	freight_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	freight_charged NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	insurance_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	carrier_document_number VARCHAR(60), 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_shipments PRIMARY KEY (id), 
	CONSTRAINT uq_shipments_shipment_number UNIQUE (shipment_number), 
	CONSTRAINT ck_shipments_shipment_type_valid CHECK (shipment_type IN ('PROCESSOR_IN', 'PROCESSOR_OUT', 'RETURN', 'SALE_DELIVERY', 'TRANSFER')), 
	CONSTRAINT ck_shipments_status_valid CHECK (status IN ('CANCELLED', 'DELIVERED', 'DISPATCHED', 'FAILED', 'IN_TRANSIT', 'PENDING', 'RETURNED')), 
	CONSTRAINT ck_shipments_origin_differs_destination CHECK (origin_location_id IS NULL OR destination_location_id IS NULL OR origin_location_id <> destination_location_id), 
	CONSTRAINT ck_shipments_freight_cost_non_negative CHECK (freight_cost >= 0), 
	CONSTRAINT ck_shipments_freight_charged_non_negative CHECK (freight_charged >= 0), 
	CONSTRAINT ck_shipments_insurance_cost_non_negative CHECK (insurance_cost >= 0), 
	CONSTRAINT fk_shipments_sale_id_sales FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipments_carrier_party_id_parties FOREIGN KEY(carrier_party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipments_origin_location_id_inventory_locations FOREIGN KEY(origin_location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipments_destination_location_id_inventory_locations FOREIGN KEY(destination_location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipments_destination_address_id_addresses FOREIGN KEY(destination_address_id) REFERENCES addresses (id) ON DELETE SET NULL, 
	CONSTRAINT fk_shipments_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_shipments_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_shipments_carrier ON shipments (carrier_party_id);

CREATE INDEX ix_shipments_status ON shipments (status);

CREATE INDEX ix_shipments_tracking ON shipments (tracking_number);

CREATE INDEX ix_shipments_sale ON shipments (sale_id);

CREATE TABLE purchase_items (
	id BIGSERIAL NOT NULL, 
	purchase_id BIGINT NOT NULL, 
	line_no SMALLINT NOT NULL, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	unit_price NUMERIC(16, 4) NOT NULL, 
	discount_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	tax_id BIGINT, 
	tax_rate NUMERIC(9, 6) DEFAULT '0' NOT NULL, 
	tax_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	allocated_freight NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	subtotal NUMERIC(16, 2) NOT NULL, 
	total NUMERIC(16, 2) NOT NULL, 
	landed_unit_cost NUMERIC(16, 4) NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_purchase_items PRIMARY KEY (id), 
	CONSTRAINT uq_purchase_items_purchase_id UNIQUE (purchase_id, line_no), 
	CONSTRAINT ck_purchase_items_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_purchase_items_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_purchase_items_unit_price_non_negative CHECK (unit_price >= 0), 
	CONSTRAINT ck_purchase_items_discount_amount_non_negative CHECK (discount_amount >= 0), 
	CONSTRAINT ck_purchase_items_tax_rate_non_negative CHECK (tax_rate >= 0), 
	CONSTRAINT ck_purchase_items_allocated_freight_non_negative CHECK (allocated_freight >= 0), 
	CONSTRAINT ck_purchase_items_landed_unit_cost_non_negative CHECK (landed_unit_cost >= 0), 
	CONSTRAINT fk_purchase_items_purchase_id_purchases FOREIGN KEY(purchase_id) REFERENCES purchases (id) ON DELETE CASCADE, 
	CONSTRAINT fk_purchase_items_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_purchase_items_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_purchase_items_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_purchase_items_tax_id_taxes FOREIGN KEY(tax_id) REFERENCES taxes (id) ON DELETE RESTRICT
);

CREATE INDEX ix_purchase_items_purchase_id ON purchase_items (purchase_id);

CREATE INDEX ix_purchase_items_batch_id ON purchase_items (batch_id);

CREATE INDEX ix_purchase_items_product_id ON purchase_items (product_id);

CREATE TABLE inventory_balances (
	id BIGSERIAL NOT NULL, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	location_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	average_unit_cost NUMERIC(16, 4) DEFAULT '0' NOT NULL, 
	total_value NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	last_movement_id BIGINT, 
	last_movement_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_inventory_balances PRIMARY KEY (id), 
	CONSTRAINT uq_inventory_balances_product_id UNIQUE (product_id, batch_id, location_id), 
	CONSTRAINT ck_inventory_balances_average_unit_cost_non_negative CHECK (average_unit_cost >= 0), 
	CONSTRAINT fk_inventory_balances_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	CONSTRAINT fk_inventory_balances_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE, 
	CONSTRAINT fk_inventory_balances_location_id_inventory_locations FOREIGN KEY(location_id) REFERENCES inventory_locations (id) ON DELETE CASCADE, 
	CONSTRAINT fk_inventory_balances_last_movement_id_inventory_movements FOREIGN KEY(last_movement_id) REFERENCES inventory_movements (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX uq_inventory_balances_no_batch ON inventory_balances (product_id, location_id) WHERE batch_id IS NULL;

CREATE INDEX ix_inventory_balances_batch_id ON inventory_balances (batch_id);

CREATE INDEX ix_inventory_balances_location_id ON inventory_balances (location_id);

CREATE TABLE production_inputs (
	id BIGSERIAL NOT NULL, 
	production_order_id BIGINT NOT NULL, 
	process_execution_id BIGINT, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	unit_cost NUMERIC(16, 4) NOT NULL, 
	total_cost NUMERIC(16, 2) NOT NULL, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	movement_id BIGINT, 
	consumed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_production_inputs PRIMARY KEY (id), 
	CONSTRAINT ck_production_inputs_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_production_inputs_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_production_inputs_unit_cost_non_negative CHECK (unit_cost >= 0), 
	CONSTRAINT ck_production_inputs_total_cost_non_negative CHECK (total_cost >= 0), 
	CONSTRAINT fk_production_inputs_production_order_id_production_orders FOREIGN KEY(production_order_id) REFERENCES production_orders (id) ON DELETE CASCADE, 
	CONSTRAINT fk_production_inputs_process_execution_id_process_executions FOREIGN KEY(process_execution_id) REFERENCES process_executions (id) ON DELETE SET NULL, 
	CONSTRAINT fk_production_inputs_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_inputs_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_inputs_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_inputs_movement_id_inventory_movements FOREIGN KEY(movement_id) REFERENCES inventory_movements (id) ON DELETE SET NULL
);

CREATE INDEX ix_production_inputs_execution ON production_inputs (process_execution_id);

CREATE INDEX ix_production_inputs_order ON production_inputs (production_order_id);

CREATE INDEX ix_production_inputs_product ON production_inputs (product_id, batch_id);

CREATE TABLE production_outputs (
	id BIGSERIAL NOT NULL, 
	production_order_id BIGINT NOT NULL, 
	process_execution_id BIGINT, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	output_kind VARCHAR(20) DEFAULT 'MAIN' NOT NULL, 
	cost_allocation_pct NUMERIC(9, 6), 
	allocated_cost NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	unit_cost NUMERIC(16, 4), 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	location_id BIGINT, 
	movement_id BIGINT, 
	produced_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_production_outputs PRIMARY KEY (id), 
	CONSTRAINT ck_production_outputs_output_kind_valid CHECK (output_kind IN ('BYPRODUCT', 'MAIN', 'REWORK')), 
	CONSTRAINT ck_production_outputs_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_production_outputs_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_production_outputs_allocated_cost_non_negative CHECK (allocated_cost >= 0), 
	CONSTRAINT ck_production_outputs_allocation_fraction CHECK (cost_allocation_pct IS NULL OR (cost_allocation_pct >= 0 AND cost_allocation_pct <= 1)), 
	CONSTRAINT ck_production_outputs_unit_cost_non_negative CHECK (unit_cost IS NULL OR unit_cost >= 0), 
	CONSTRAINT fk_production_outputs_production_order_id_production_orders FOREIGN KEY(production_order_id) REFERENCES production_orders (id) ON DELETE CASCADE, 
	CONSTRAINT fk_production_outputs_process_execution_id_process_executions FOREIGN KEY(process_execution_id) REFERENCES process_executions (id) ON DELETE SET NULL, 
	CONSTRAINT fk_production_outputs_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_outputs_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_outputs_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_outputs_location_id_inventory_locations FOREIGN KEY(location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_outputs_movement_id_inventory_movements FOREIGN KEY(movement_id) REFERENCES inventory_movements (id) ON DELETE SET NULL
);

CREATE INDEX ix_production_outputs_product ON production_outputs (product_id, batch_id);

CREATE INDEX ix_production_outputs_order ON production_outputs (production_order_id);

CREATE INDEX ix_production_outputs_execution ON production_outputs (process_execution_id);

CREATE TABLE production_waste (
	id BIGSERIAL NOT NULL, 
	production_order_id BIGINT NOT NULL, 
	process_execution_id BIGINT, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	waste_type VARCHAR(30) NOT NULL, 
	is_expected BOOLEAN DEFAULT 'true' NOT NULL, 
	is_recoverable BOOLEAN DEFAULT 'false' NOT NULL, 
	recovered_product_id BIGINT, 
	recovered_batch_id BIGINT, 
	cost_treatment VARCHAR(30) DEFAULT 'ABSORBED_BY_OUTPUT' NOT NULL, 
	cost_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	movement_id BIGINT, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_production_waste PRIMARY KEY (id), 
	CONSTRAINT ck_production_waste_waste_type_valid CHECK (waste_type IN ('CASCARILLA', 'CONTAMINACION', 'DEFECTO', 'DERRAME', 'MERMA_HUMEDAD', 'MERMA_PROCESO', 'PASILLA')), 
	CONSTRAINT ck_production_waste_cost_treatment_valid CHECK (cost_treatment IN ('ABSORBED_BY_OUTPUT', 'ALLOCATED_TO_BYPRODUCT', 'EXPENSED')), 
	CONSTRAINT ck_production_waste_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_production_waste_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_production_waste_cost_amount_non_negative CHECK (cost_amount >= 0), 
	CONSTRAINT ck_production_waste_recoverable_requires_product CHECK (is_recoverable = FALSE OR recovered_product_id IS NOT NULL), 
	CONSTRAINT fk_production_waste_production_order_id_production_orders FOREIGN KEY(production_order_id) REFERENCES production_orders (id) ON DELETE CASCADE, 
	CONSTRAINT fk_production_waste_process_execution_id_process_executions FOREIGN KEY(process_execution_id) REFERENCES process_executions (id) ON DELETE SET NULL, 
	CONSTRAINT fk_production_waste_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_waste_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_waste_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_waste_recovered_product_id_products FOREIGN KEY(recovered_product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_waste_recovered_batch_id_batches FOREIGN KEY(recovered_batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_production_waste_movement_id_inventory_movements FOREIGN KEY(movement_id) REFERENCES inventory_movements (id) ON DELETE SET NULL
);

CREATE INDEX ix_production_waste_order ON production_waste (production_order_id);

CREATE INDEX ix_production_waste_type ON production_waste (waste_type, is_expected);

CREATE INDEX ix_production_waste_execution ON production_waste (process_execution_id);

CREATE TABLE sale_item_batches (
	id BIGSERIAL NOT NULL, 
	sale_item_id BIGINT NOT NULL, 
	batch_id BIGINT NOT NULL, 
	location_id BIGINT NOT NULL, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	unit_cost NUMERIC(16, 4) NOT NULL, 
	total_cost NUMERIC(16, 2) NOT NULL, 
	movement_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_sale_item_batches PRIMARY KEY (id), 
	CONSTRAINT uq_sale_item_batches_sale_item_id UNIQUE (sale_item_id, batch_id, location_id), 
	CONSTRAINT ck_sale_item_batches_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_sale_item_batches_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT ck_sale_item_batches_unit_cost_non_negative CHECK (unit_cost >= 0), 
	CONSTRAINT fk_sale_item_batches_sale_item_id_sale_items FOREIGN KEY(sale_item_id) REFERENCES sale_items (id) ON DELETE CASCADE, 
	CONSTRAINT fk_sale_item_batches_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sale_item_batches_location_id_inventory_locations FOREIGN KEY(location_id) REFERENCES inventory_locations (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sale_item_batches_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sale_item_batches_movement_id_inventory_movements FOREIGN KEY(movement_id) REFERENCES inventory_movements (id) ON DELETE SET NULL
);

CREATE INDEX ix_sib_batch ON sale_item_batches (batch_id);

CREATE INDEX ix_sib_sale_item ON sale_item_batches (sale_item_id);

CREATE TABLE invoices (
	id BIGSERIAL NOT NULL, 
	document_type VARCHAR(30) NOT NULL, 
	resolution_id BIGINT, 
	prefix VARCHAR(10) NOT NULL, 
	consecutive BIGINT NOT NULL, 
	full_number VARCHAR(30) NOT NULL, 
	sale_id BIGINT, 
	purchase_id BIGINT, 
	party_id BIGINT NOT NULL, 
	related_invoice_id BIGINT, 
	issue_date DATE NOT NULL, 
	issue_time TIME WITH TIME ZONE, 
	due_date DATE, 
	currency CHAR(3) DEFAULT 'COP' NOT NULL, 
	subtotal NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	discount_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	tax_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	withholding_total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	total NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	payment_means VARCHAR(20), 
	payment_form VARCHAR(20), 
	cufe VARCHAR(200), 
	uuid VARCHAR(100), 
	qr_data TEXT, 
	xml_signed TEXT, 
	xml_path VARCHAR(255), 
	pdf_path VARCHAR(255), 
	dian_status VARCHAR(25) DEFAULT 'DRAFT' NOT NULL, 
	dian_track_id VARCHAR(100), 
	dian_response JSONB, 
	dian_errors JSONB, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	accepted_at TIMESTAMP WITH TIME ZONE, 
	email_sent_at TIMESTAMP WITH TIME ZONE, 
	notes TEXT, 
	created_by_id BIGINT, 
	updated_by_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_invoices PRIMARY KEY (id), 
	CONSTRAINT uq_invoices_prefix UNIQUE (prefix, consecutive, document_type), 
	CONSTRAINT uq_invoices_full_number UNIQUE (full_number), 
	CONSTRAINT ck_invoices_document_type_valid CHECK (document_type IN ('DOCUMENTO_SOPORTE', 'FACTURA_VENTA', 'NOTA_CREDITO', 'NOTA_DEBITO')), 
	CONSTRAINT ck_invoices_dian_status_valid CHECK (dian_status IN ('ACCEPTED', 'CANCELLED', 'DRAFT', 'GENERATED', 'REJECTED', 'SENT', 'SIGNED')), 
	CONSTRAINT ck_invoices_payment_form_valid CHECK (payment_form IS NULL OR payment_form IN ('CONTADO','CREDITO')), 
	CONSTRAINT ck_invoices_note_requires_related CHECK (document_type NOT IN ('NOTA_CREDITO','NOTA_DEBITO') OR related_invoice_id IS NOT NULL), 
	CONSTRAINT ck_invoices_support_requires_purchase CHECK (document_type <> 'DOCUMENTO_SOPORTE' OR purchase_id IS NOT NULL), 
	CONSTRAINT ck_invoices_requires_sale CHECK (document_type = 'DOCUMENTO_SOPORTE' OR sale_id IS NOT NULL), 
	CONSTRAINT fk_invoices_resolution_id_fiscal_resolutions FOREIGN KEY(resolution_id) REFERENCES fiscal_resolutions (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_invoices_sale_id_sales FOREIGN KEY(sale_id) REFERENCES sales (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_invoices_purchase_id_purchases FOREIGN KEY(purchase_id) REFERENCES purchases (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_invoices_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_invoices_related_invoice_id_invoices FOREIGN KEY(related_invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_invoices_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	CONSTRAINT fk_invoices_updated_by_id_users FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_invoices_sale ON invoices (sale_id);

CREATE UNIQUE INDEX uq_invoices_cufe ON invoices (cufe) WHERE cufe IS NOT NULL;

CREATE INDEX ix_invoices_dian_status ON invoices (dian_status);

CREATE INDEX ix_invoices_issue_date ON invoices (issue_date DESC);

CREATE INDEX ix_invoices_party ON invoices (party_id, issue_date DESC);

CREATE TABLE shipment_items (
	id BIGSERIAL NOT NULL, 
	shipment_id BIGINT NOT NULL, 
	sale_item_id BIGINT, 
	product_id BIGINT NOT NULL, 
	batch_id BIGINT, 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT NOT NULL, 
	quantity_base NUMERIC(16, 4) NOT NULL, 
	movement_id BIGINT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_shipment_items PRIMARY KEY (id), 
	CONSTRAINT ck_shipment_items_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_shipment_items_quantity_base_positive CHECK (quantity_base > 0), 
	CONSTRAINT fk_shipment_items_shipment_id_shipments FOREIGN KEY(shipment_id) REFERENCES shipments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_shipment_items_sale_item_id_sale_items FOREIGN KEY(sale_item_id) REFERENCES sale_items (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipment_items_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipment_items_batch_id_batches FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipment_items_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_shipment_items_movement_id_inventory_movements FOREIGN KEY(movement_id) REFERENCES inventory_movements (id) ON DELETE SET NULL
);

CREATE INDEX ix_shipment_items_shipment_id ON shipment_items (shipment_id);

CREATE TABLE shipment_events (
	id BIGSERIAL NOT NULL, 
	shipment_id BIGINT NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	location_text VARCHAR(150), 
	message TEXT, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by_id BIGINT, 
	CONSTRAINT pk_shipment_events PRIMARY KEY (id), 
	CONSTRAINT ck_shipment_events_event_type_valid CHECK (event_type IN ('CREATED', 'DELIVERED', 'DISPATCHED', 'FAILED', 'IN_TRANSIT', 'NOTE', 'OUT_FOR_DELIVERY', 'RETURNED')), 
	CONSTRAINT fk_shipment_events_shipment_id_shipments FOREIGN KEY(shipment_id) REFERENCES shipments (id) ON DELETE CASCADE, 
	CONSTRAINT fk_shipment_events_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_shipment_events_shipment ON shipment_events (shipment_id, occurred_at);

CREATE TABLE invoice_items (
	id BIGSERIAL NOT NULL, 
	invoice_id BIGINT NOT NULL, 
	line_no SMALLINT NOT NULL, 
	sale_item_id BIGINT, 
	purchase_item_id BIGINT, 
	product_id BIGINT, 
	description VARCHAR(255) NOT NULL, 
	product_code VARCHAR(40), 
	quantity NUMERIC(16, 4) NOT NULL, 
	unit_id BIGINT, 
	unit_dian_code VARCHAR(10), 
	unit_price NUMERIC(16, 4) NOT NULL, 
	discount_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	tax_code VARCHAR(20), 
	tax_rate NUMERIC(9, 6) DEFAULT '0' NOT NULL, 
	tax_amount NUMERIC(16, 2) DEFAULT '0' NOT NULL, 
	subtotal NUMERIC(16, 2) NOT NULL, 
	total NUMERIC(16, 2) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_invoice_items PRIMARY KEY (id), 
	CONSTRAINT uq_invoice_items_invoice_id UNIQUE (invoice_id, line_no), 
	CONSTRAINT ck_invoice_items_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_invoice_items_discount_non_negative CHECK (discount_amount >= 0), 
	CONSTRAINT fk_invoice_items_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, 
	CONSTRAINT fk_invoice_items_sale_item_id_sale_items FOREIGN KEY(sale_item_id) REFERENCES sale_items (id) ON DELETE SET NULL, 
	CONSTRAINT fk_invoice_items_purchase_item_id_purchase_items FOREIGN KEY(purchase_item_id) REFERENCES purchase_items (id) ON DELETE SET NULL, 
	CONSTRAINT fk_invoice_items_product_id_products FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	CONSTRAINT fk_invoice_items_unit_id_units_of_measure FOREIGN KEY(unit_id) REFERENCES units_of_measure (id) ON DELETE RESTRICT
);

CREATE INDEX ix_invoice_items_invoice_id ON invoice_items (invoice_id);

CREATE TABLE invoice_events (
	id BIGSERIAL NOT NULL, 
	invoice_id BIGINT NOT NULL, 
	event_type VARCHAR(30) NOT NULL, 
	status_before VARCHAR(25), 
	status_after VARCHAR(25), 
	payload JSONB, 
	message TEXT, 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_by_id BIGINT, 
	CONSTRAINT pk_invoice_events PRIMARY KEY (id), 
	CONSTRAINT ck_invoice_events_event_type_valid CHECK (event_type IN ('ACCEPTED', 'CANCELLED', 'EMAILED', 'ERROR', 'GENERATED', 'REJECTED', 'RETRY', 'SENT', 'SIGNED')), 
	CONSTRAINT fk_invoice_events_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, 
	CONSTRAINT fk_invoice_events_created_by_id_users FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_invoice_events_invoice ON invoice_events (invoice_id, occurred_at);

ALTER TABLE parties ADD CONSTRAINT fk_parties_default_price_list_id_price_lists FOREIGN KEY(default_price_list_id) REFERENCES price_lists (id) ON DELETE SET NULL;

ALTER TABLE batches ADD CONSTRAINT fk_batches_purchase_item_id_purchase_items FOREIGN KEY(purchase_item_id) REFERENCES purchase_items (id) ON DELETE SET NULL;

ALTER TABLE users ADD CONSTRAINT fk_users_party_id_parties FOREIGN KEY(party_id) REFERENCES parties (id) ON DELETE SET NULL;


COMMIT;
