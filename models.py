from datetime import datetime

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


# =========================================================
# ADMIN
# =========================================================

class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self):
        return f"<Admin {self.username}>"


# =========================================================
# API
# =========================================================

class API(db.Model):
    __tablename__ = "apis"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(150),
        nullable=False
    )

    url = db.Column(
        db.String(500),
        nullable=False
    )

    method = db.Column(
        db.String(10),
        nullable=False,
        default="GET"
    )

    expected_status = db.Column(
        db.Integer,
        nullable=False,
        default=200
    )

    interval_seconds = db.Column(
        db.Integer,
        nullable=False,
        default=60
    )

    timeout_seconds = db.Column(
        db.Integer,
        nullable=False,
        default=10
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationship with monitoring logs
    monitoring_logs = db.relationship(
        "MonitoringLog",
        back_populates="api",
        cascade="all, delete-orphan"
    )

    # Relationship with incidents
    incidents = db.relationship(
        "Incident",
        back_populates="api",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<API {self.name}>"


# =========================================================
# MONITORING LOG
# =========================================================

class MonitoringLog(db.Model):
    __tablename__ = "monitoring_logs"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    api_id = db.Column(
        db.Integer,
        db.ForeignKey("apis.id"),
        nullable=False
    )

    status_code = db.Column(
        db.Integer,
        nullable=True
    )

    response_time_ms = db.Column(
        db.Float,
        nullable=True
    )

    success = db.Column(
        db.Boolean,
        nullable=False
    )

    error_message = db.Column(
        db.Text,
        nullable=True
    )

    checked_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    api = db.relationship(
        "API",
        back_populates="monitoring_logs"
    )

    def __repr__(self):
        return f"<MonitoringLog API={self.api_id}>"


# =========================================================
# INCIDENT
# =========================================================

class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    incident_code = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    api_id = db.Column(
        db.Integer,
        db.ForeignKey("apis.id"),
        nullable=False
    )

    reason = db.Column(
        db.Text,
        nullable=False
    )

    started_at = db.Column(
        db.DateTime,
        nullable=False
    )

    resolved_at = db.Column(
        db.DateTime,
        nullable=True
    )

    duration_seconds = db.Column(
        db.Integer,
        nullable=True
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="ACTIVE"
    )

    api = db.relationship(
        "API",
        back_populates="incidents"
    )

    alerts = db.relationship(
        "Alert",
        back_populates="incident",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Incident {self.incident_code}>"


# =========================================================
# ALERT
# =========================================================

class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    incident_id = db.Column(
        db.Integer,
        db.ForeignKey("incidents.id"),
        nullable=False
    )

    alert_type = db.Column(
        db.String(50),
        nullable=False
    )

    channel = db.Column(
        db.String(50),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    sent_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        nullable=False
    )

    incident = db.relationship(
        "Incident",
        back_populates="alerts"
    )

    def __repr__(self):
        return f"<Alert {self.id}>"

# =========================================================
# SYSTEM SETTINGS
# =========================================================

class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    key = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    value = db.Column(
        db.Text,
        nullable=True
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self):
        return f"<SystemSetting {self.key}>"
