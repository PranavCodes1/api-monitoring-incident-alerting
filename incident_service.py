from datetime import datetime

from sqlalchemy import text

from alert_service import (
    create_incident_alert,
    create_recovery_alert
)
# =========================================================
# CREATE INCIDENT
# =========================================================

def create_incident(db, api, reason, started_at):
    """
    Create a new incident for an API failure.

    A new incident is created only when the API does not
    already have an OPEN incident.

    Returns:
        {
            "incident_id": int,
            "incident_code": str
        }

        Returns None if an OPEN incident already exists
        or if an error occurs.
    """

    try:

        # -------------------------------------------------
        # CHECK WHETHER AN OPEN INCIDENT ALREADY EXISTS
        # -------------------------------------------------

        existing_incident = db.session.execute(
            text("""
                SELECT id
                FROM incidents
                WHERE api_id = :api_id
                  AND status = 'OPEN'
                LIMIT 1
            """),
            {
                "api_id": api["id"]
            }
        ).first()

        # -------------------------------------------------
        # PREVENT DUPLICATE INCIDENTS
        # -------------------------------------------------

        if existing_incident:
            return None

        # -------------------------------------------------
        # GENERATE INCIDENT CODE
        # -------------------------------------------------

        incident_code = (
            f"INC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            f"-API{api['id']}"
        )

        # -------------------------------------------------
        # INSERT INCIDENT
        # -------------------------------------------------

        result = db.session.execute(
            text("""
                INSERT INTO incidents (
                    incident_code,
                    api_id,
                    reason,
                    started_at,
                    resolved_at,
                    duration_seconds,
                    status
                )
                VALUES (
                    :incident_code,
                    :api_id,
                    :reason,
                    :started_at,
                    NULL,
                    NULL,
                    'OPEN'
                )
                RETURNING id
            """),
            {
                "incident_code": incident_code,
                "api_id": api["id"],
                "reason": reason or "API request failed.",
                "started_at": started_at
            }
        )

        # -------------------------------------------------
        # GET GENERATED INCIDENT ID
        # -------------------------------------------------

        incident_id = result.scalar_one()

        # -------------------------------------------------
        # COMMIT
        # -------------------------------------------------

        db.session.commit()

        print(
            f"[INCIDENT CREATED] "
            f"{incident_code} | "
            f"{api['name']} | "
            f"{reason}"
        )
        # -------------------------------------------------
        # CREATE INCIDENT ALERT
        # -------------------------------------------------

        create_incident_alert(
            db=db,
            incident_id=incident_id,
            api=api,
            reason=reason
        )

        # -------------------------------------------------
        # RETURN INCIDENT INFORMATION
        # -------------------------------------------------

        return {
            "incident_id": incident_id,
            "incident_code": incident_code
        }

    except Exception as e:

        db.session.rollback()

        print(
            f"[INCIDENT ERROR] "
            f"Could not create incident for "
            f"API {api['id']}: {e}"
        )

        return None


# =========================================================
# RESOLVE INCIDENT
# =========================================================

def resolve_incident(db, api, resolved_at):
    """
    Resolve the currently OPEN incident for an API.

    Calculates the downtime between started_at and
    resolved_at.
    """

    try:

        # -------------------------------------------------
        # FIND OPEN INCIDENT
        # -------------------------------------------------

        incident = db.session.execute(
            text("""
                SELECT
                    id,
                    started_at
                FROM incidents
                WHERE api_id = :api_id
                  AND status = 'OPEN'
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {
                "api_id": api["id"]
            }
        ).mappings().first()

        # -------------------------------------------------
        # NOTHING TO RESOLVE
        # -------------------------------------------------

        if not incident:
            return False

        # -------------------------------------------------
        # CALCULATE DOWNTIME
        # -------------------------------------------------

        duration_seconds = int(
            (
                resolved_at - incident["started_at"]
            ).total_seconds()
        )

        if duration_seconds < 0:
            duration_seconds = 0

        # -------------------------------------------------
        # UPDATE INCIDENT
        # -------------------------------------------------

        db.session.execute(
            text("""
                UPDATE incidents
                SET
                    resolved_at = :resolved_at,
                    duration_seconds = :duration_seconds,
                    status = 'RESOLVED'
                WHERE id = :incident_id
            """),
            {
                "resolved_at": resolved_at,
                "duration_seconds": duration_seconds,
                "incident_id": incident["id"]
            }
        )

        db.session.commit()

        print(
            f"[INCIDENT RESOLVED] "
            f"API {api['name']} | "
            f"Downtime: {duration_seconds} seconds"
        )

        # -------------------------------------------------
        # CREATE RECOVERY ALERT
        # -------------------------------------------------

        create_recovery_alert(
            db=db,
            incident_id=incident["id"],
            api=api
        )


        return {
            "incident_id": incident["id"]
        }
    except Exception as e:

        db.session.rollback()

        print(
            f"[INCIDENT ERROR] "
            f"Could not resolve incident for "
            f"API {api['id']}: {e}"
        )

        return False


# =========================================================
# HANDLE API FAILURE
# =========================================================

def handle_api_failure(db, api, error_message, failed_at):
    """
    Called whenever an API check fails.

    Creates an incident immediately if there is no
    existing OPEN incident.
    """

    return create_incident(
        db=db,
        api=api,
        reason=error_message,
        started_at=failed_at
    )


# =========================================================
# HANDLE API RECOVERY
# =========================================================

def handle_api_recovery(db, api, recovered_at):
    """
    Called whenever an API check succeeds.

    If an OPEN incident exists, it is resolved.
    """

    return resolve_incident(
        db=db,
        api=api,
        resolved_at=recovered_at
    )
