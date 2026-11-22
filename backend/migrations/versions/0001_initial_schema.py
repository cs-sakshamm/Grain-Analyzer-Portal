"""Initial schema: organisation, identity, devices, analysis, files, notifications, audit.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-22

Enum types are created explicitly so the downgrade can drop them after the tables that
use them. ``gen_random_uuid()`` is built into PostgreSQL 13+, which is the minimum
supported by the Compose image and CI service.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

ENUM_VALUES: dict[str, list[str]] = {
    "membership_role": ["department_admin", "department_user"],
    "device_status": ["provisioned", "active", "suspended", "retired"],
    "scan_processing_status": [
        "received",
        "awaiting_files",
        "verifying",
        "completed",
        "failed",
    ],
    "quality_verdict": ["pass", "flagged", "inconclusive", "lab_confirmation_required"],
    "measurement_basis": [
        "count_percent",
        "estimated_mass_percent",
        "physical_mass_percent",
        "physical_mass_grams",
        "count",
        "dimension",
        "ratio",
        "other",
    ],
    "scan_file_role": ["report_pdf", "bottom_image", "top_image", "other"],
    "upload_status": ["pending", "uploaded", "verified", "rejected"],
    "age_validation_status": ["unvalidated", "provisional", "validated", "rejected"],
    "notification_event_type": [
        "scan_completed",
        "quality_flagged",
        "upload_failed",
        "report_available",
        "lab_confirmation_required",
    ],
    "notification_severity": ["info", "warning", "critical"],
    "audit_actor_type": ["user", "device", "system"],
}

ENUMS = {
    name: postgresql.ENUM(*values, name=name, create_type=False)
    for name, values in ENUM_VALUES.items()
}


def upgrade() -> None:
    for name, values in ENUM_VALUES.items():
        joined = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({joined})")

    op.create_table(
        "departments",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_departments"),
    )
    op.create_index("uq_departments_code", "departments", ["code"], unique=True)
    op.create_index("uq_departments_code_ci", "departments", [sa.text("lower(code)")], unique=True)
    op.create_index("idx_departments_active", "departments", ["is_active"])

    op.create_table(
        "users",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("is_super_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_index("idx_users_active", "users", ["is_active"])

    op.create_table(
        "memberships",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", ENUMS["membership_role"], nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_memberships_department",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
    )
    op.create_index(
        "uq_memberships_user_department", "memberships", ["user_id", "department_id"], unique=True
    )
    op.create_index(
        "idx_memberships_department",
        "memberships",
        ["department_id", "role"],
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "idx_memberships_user",
        "memberships",
        ["user_id"],
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "user_sessions",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("token_family_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.CheckConstraint("expires_at > issued_at", name="ck_user_sessions_expiry_after_issue"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_sessions_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
    )
    op.create_index(
        "uq_user_sessions_refresh_hash", "user_sessions", ["refresh_token_hash"], unique=True
    )
    op.create_index(
        "idx_user_sessions_user", "user_sessions", ["user_id", sa.text("expires_at DESC")]
    )
    op.create_index("idx_user_sessions_family", "user_sessions", ["token_family_id"])

    op.create_table(
        "devices",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("device_uid", sa.String(64), nullable=False),
        sa.Column("serial_number", sa.String(128), nullable=False),
        sa.Column("friendly_name", sa.String(200), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("hardware_revision", sa.String(64), nullable=True),
        sa.Column("firmware_version", sa.String(64), nullable=True),
        sa.Column("installation_location", sa.String(255), nullable=True),
        sa.Column(
            "status",
            ENUMS["device_status"],
            server_default=sa.text("'provisioned'"),
            nullable=False,
        ),
        sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_upload_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
    )
    op.create_index("uq_devices_device_uid", "devices", ["device_uid"], unique=True)
    op.create_index("uq_devices_serial_number", "devices", ["serial_number"], unique=True)
    op.create_index("idx_devices_status", "devices", ["status"])
    op.create_index("idx_devices_last_seen", "devices", [sa.text("last_seen_at DESC")])

    op.create_table(
        "device_credentials",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(120), nullable=True),
        sa.CheckConstraint("version > 0", name="ck_device_credentials_version_positive"),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_device_credentials_device",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_device_credentials_created_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_credentials"),
    )
    op.create_index(
        "uq_device_credentials_client_id", "device_credentials", ["client_id"], unique=True
    )
    op.create_index(
        "uq_device_credentials_device_version",
        "device_credentials",
        ["device_id", "version"],
        unique=True,
    )
    op.create_index(
        "uq_device_credentials_active",
        "device_credentials",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "idx_device_credentials_device",
        "device_credentials",
        ["device_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "device_assignments",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_device_assignments_period",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_device_assignments_device", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_device_assignments_department",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name="fk_device_assignments_assigned_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_assignments"),
    )
    op.create_index(
        "uq_device_assignments_active",
        "device_assignments",
        ["device_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )
    op.create_index(
        "idx_device_assignments_device",
        "device_assignments",
        ["device_id", sa.text("effective_from DESC")],
    )
    op.create_index(
        "idx_device_assignments_department",
        "device_assignments",
        ["department_id", sa.text("effective_from DESC")],
    )

    op.create_table(
        "batches",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("batch_code", sa.String(64), nullable=False),
        sa.Column("lot_code", sa.String(64), nullable=True),
        sa.Column("variety", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_batches_department", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batches"),
    )
    op.create_index(
        "uq_batches_dept_code_lot_null",
        "batches",
        ["department_id", "batch_code"],
        unique=True,
        postgresql_where=sa.text("lot_code IS NULL"),
    )
    op.create_index(
        "uq_batches_dept_code_lot",
        "batches",
        ["department_id", "batch_code", "lot_code"],
        unique=True,
        postgresql_where=sa.text("lot_code IS NOT NULL"),
    )
    op.create_index("idx_batches_department", "batches", ["department_id", "batch_code"])

    op.create_table(
        "scans",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("client_scan_id", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("sample_id", sa.String(128), nullable=False),
        sa.Column("batch_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("batch_code", sa.String(64), nullable=True),
        sa.Column("lot_code", sa.String(64), nullable=True),
        sa.Column("variety", sa.String(120), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "processing_status",
            ENUMS["scan_processing_status"],
            server_default=sa.text("'awaiting_files'"),
            nullable=False,
        ),
        sa.Column("quality_verdict", ENUMS["quality_verdict"], nullable=True),
        sa.Column("ruleset_version", sa.String(64), nullable=True),
        sa.Column("certification_status", sa.String(32), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_status <> 'completed' OR finalized_at IS NOT NULL",
            name="ck_scans_completed_has_finalized_at",
        ),
        sa.CheckConstraint(
            "analyzed_at <= received_at + interval '1 hour'",
            name="ck_scans_analyzed_at_not_future",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_scans_device", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["department_id"], ["departments.id"], name="fk_scans_department", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["batches.id"], name="fk_scans_batch", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scans"),
    )
    op.create_index(
        "uq_scans_device_client_scan", "scans", ["device_id", "client_scan_id"], unique=True
    )
    op.create_index(
        "idx_scans_department_completed",
        "scans",
        ["department_id", sa.text("analyzed_at DESC")],
        postgresql_where=sa.text("processing_status = 'completed'"),
    )
    op.create_index(
        "idx_scans_department_received", "scans", ["department_id", sa.text("received_at DESC")]
    )
    op.create_index(
        "idx_scans_batch",
        "scans",
        ["department_id", "batch_id"],
        postgresql_where=sa.text("batch_id IS NOT NULL"),
    )
    op.create_index("idx_scans_device", "scans", ["device_id", sa.text("received_at DESC")])
    op.create_index(
        "idx_scans_status",
        "scans",
        ["processing_status"],
        postgresql_where=sa.text("processing_status <> 'completed'"),
    )

    op.create_table(
        "measurements",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("metric_code", sa.String(64), nullable=False),
        sa.Column("metric_label", sa.String(120), nullable=True),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("basis", ENUMS["measurement_basis"], nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("value >= 0", name="ck_measurements_value_non_negative"),
        sa.CheckConstraint(
            "is_estimated OR basis IN "
            "('count_percent','physical_mass_percent','physical_mass_grams','count',"
            "'dimension','ratio','other')",
            name="ck_measurements_estimated_basis",
        ),
        sa.CheckConstraint(
            "basis <> 'count_percent' OR unit = 'percent'",
            name="ck_measurements_count_percent_unit",
        ),
        sa.CheckConstraint(
            "basis <> 'estimated_mass_percent' OR (unit = 'percent' AND is_estimated)",
            name="ck_measurements_estimated_mass_unit",
        ),
        sa.CheckConstraint(
            "basis <> 'physical_mass_percent' OR unit = 'percent'",
            name="ck_measurements_physical_percent_unit",
        ),
        sa.CheckConstraint(
            "basis <> 'physical_mass_grams' OR unit = 'gram'",
            name="ck_measurements_physical_grams_unit",
        ),
        sa.CheckConstraint(
            "basis <> 'dimension' OR unit = 'mm'", name="ck_measurements_dimension_unit"
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_measurements_scan", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_measurements"),
    )
    op.create_index(
        "uq_measurements_scan_metric_basis",
        "measurements",
        ["scan_id", "metric_code", "basis"],
        unique=True,
    )
    op.create_index("idx_measurements_scan", "measurements", ["scan_id"])
    op.create_index("idx_measurements_metric", "measurements", ["metric_code", "basis"])

    op.create_table(
        "quality_evaluations",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("parameter_code", sa.String(64), nullable=False),
        sa.Column("basis", ENUMS["measurement_basis"], nullable=False),
        sa.Column("measured_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("threshold_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("comparison_operator", sa.String(8), nullable=True),
        sa.Column("source_limit_text", sa.String(120), nullable=True),
        sa.Column("status", ENUMS["quality_verdict"], nullable=False),
        sa.Column("ruleset_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_quality_evaluations_scan", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quality_evaluations"),
    )
    op.create_index(
        "uq_quality_evaluations_scan_parameter_basis",
        "quality_evaluations",
        ["scan_id", "parameter_code", "basis"],
        unique=True,
    )
    op.create_index("idx_quality_evaluations_scan", "quality_evaluations", ["scan_id"])
    op.create_index("idx_quality_evaluations_status", "quality_evaluations", ["status"])

    op.create_table(
        "age_results",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("age_value_months", sa.Numeric(6, 2), nullable=True),
        sa.Column("age_min_months", sa.Numeric(6, 2), nullable=True),
        sa.Column("age_max_months", sa.Numeric(6, 2), nullable=True),
        sa.Column("age_category", sa.String(64), nullable=True),
        sa.Column("proportion_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("unit", sa.String(24), nullable=True),
        sa.Column("method", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("validation_status", ENUMS["age_validation_status"], nullable=True),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "age_min_months IS NULL OR age_min_months >= 0", name="ck_age_results_min_non_negative"
        ),
        sa.CheckConstraint(
            "age_max_months IS NULL OR age_max_months >= 0", name="ck_age_results_max_non_negative"
        ),
        sa.CheckConstraint(
            "age_min_months IS NULL OR age_max_months IS NULL OR age_max_months >= age_min_months",
            name="ck_age_results_range_order",
        ),
        sa.CheckConstraint(
            "age_value_months IS NOT NULL OR age_min_months IS NOT NULL "
            "OR age_max_months IS NOT NULL OR age_category IS NOT NULL",
            name="ck_age_results_has_information",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_age_results_confidence_range",
        ),
        sa.CheckConstraint(
            "proportion_percent IS NULL OR (proportion_percent >= 0 AND proportion_percent <= 100)",
            name="ck_age_results_proportion_range",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_age_results_scan", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_age_results"),
    )
    op.create_index("uq_age_results_scan", "age_results", ["scan_id"], unique=True)

    op.create_table(
        "scan_files",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", ENUMS["scan_file_role"], nullable=False),
        sa.Column("storage_backend", sa.String(16), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column(
            "upload_status",
            ENUMS["upload_status"],
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_scan_files_size_positive"),
        sa.CheckConstraint(
            "upload_status <> 'verified' OR verified_at IS NOT NULL",
            name="ck_scan_files_verified_has_timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_scan_files_scan", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scan_files"),
    )
    op.create_index("uq_scan_files_storage_key", "scan_files", ["storage_key"], unique=True)
    op.create_index(
        "uq_scan_files_fixed_role",
        "scan_files",
        ["scan_id", "role"],
        unique=True,
        postgresql_where=sa.text("role <> 'other'"),
    )
    op.create_index("idx_scan_files_scan", "scan_files", ["scan_id"])
    op.create_index(
        "idx_scan_files_status",
        "scan_files",
        ["upload_status"],
        postgresql_where=sa.text("upload_status <> 'verified'"),
    )

    op.create_table(
        "upload_attempts",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scan_file_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("role", ENUMS["scan_file_role"], nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("diagnostic_code", sa.String(64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('prepare','upload','verify')", name="ck_upload_attempts_stage"
        ),
        sa.CheckConstraint(
            "status IN ('started','succeeded','failed')", name="ck_upload_attempts_status"
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_upload_attempts_scan", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["scan_file_id"],
            ["scan_files.id"],
            name="fk_upload_attempts_scan_file",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_upload_attempts"),
    )
    op.create_index(
        "idx_upload_attempts_scan", "upload_attempts", ["scan_id", sa.text("created_at DESC")]
    )

    op.create_table(
        "notifications",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("scan_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("event_type", ENUMS["notification_event_type"], nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column(
            "severity",
            ENUMS["notification_severity"],
            server_default=sa.text("'info'"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_notifications_department",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_notifications_scan", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    op.create_index("uq_notifications_event_key", "notifications", ["event_key"], unique=True)
    op.create_index(
        "idx_notifications_department",
        "notifications",
        ["department_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_notifications_scan", "notifications", ["scan_id"])

    op.create_table(
        "notification_recipients",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("notification_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name="fk_notification_recipients_notification",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_notification_recipients_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_recipients"),
    )
    op.create_index(
        "uq_notification_recipients_notification_user",
        "notification_recipients",
        ["notification_id", "user_id"],
        unique=True,
    )
    op.create_index(
        "idx_notification_recipients_unread",
        "notification_recipients",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("read_at IS NULL"),
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_type", ENUMS["audit_actor_type"], nullable=False),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_device_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type <> 'user' OR actor_user_id IS NOT NULL", name="ck_audit_logs_user_actor"
        ),
        sa.CheckConstraint(
            "actor_type <> 'device' OR actor_device_id IS NOT NULL",
            name="ck_audit_logs_device_actor",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_audit_logs_actor_user", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["actor_device_id"],
            ["devices.id"],
            name="fk_audit_logs_actor_device",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name="fk_audit_logs_department",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("idx_audit_logs_occurred", "audit_logs", [sa.text("occurred_at DESC")])
    op.create_index(
        "idx_audit_logs_department", "audit_logs", ["department_id", sa.text("occurred_at DESC")]
    )
    op.create_index(
        "idx_audit_logs_actor", "audit_logs", ["actor_user_id", sa.text("occurred_at DESC")]
    )
    op.create_index("idx_audit_logs_target", "audit_logs", ["target_type", "target_id"])


def downgrade() -> None:
    for table in [
        "audit_logs",
        "notification_recipients",
        "notifications",
        "upload_attempts",
        "scan_files",
        "age_results",
        "quality_evaluations",
        "measurements",
        "scans",
        "batches",
        "device_assignments",
        "device_credentials",
        "devices",
        "user_sessions",
        "memberships",
        "users",
        "departments",
    ]:
        op.drop_table(table)
    for name in reversed(list(ENUM_VALUES)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
