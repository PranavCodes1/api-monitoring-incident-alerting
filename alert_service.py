from datetime import datetime
import os
import requests

from sqlalchemy import text
from models import SystemSetting


# =========================================================
# DISCORD CONFIGURATION
# =========================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


# =========================================================
# CHECK DISCORD ALERT STATUS
# =========================================================

def is_discord_alerts_enabled(db):
    setting = SystemSetting.query.filter_by(
        key="discord_alerts_enabled"
    ).first()

    # Default to enabled if the setting has not been saved yet.
    if setting is None:
        return True

    return setting.value == "true"


# =========================================================
# SEND MESSAGE TO DISCORD
# =========================================================

def send_discord_message(message):
    """Send a message to the configured Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD ERROR] Webhook URL is not configured.")
        return False

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message},
            timeout=10
        )

        if response.status_code in (200, 204):
            print("[DISCORD] Alert sent successfully.")
            return True

        print(
            f"[DISCORD ERROR] HTTP {response.status_code}: "
            f"{response.text}"
        )
        return False

    except requests.RequestException as e:
        print(f"[DISCORD ERROR] Could not send message: {e}")
        return False


def _send_or_disable_discord(db, message):
    """Return (sent, status), respecting the saved Discord toggle."""
    if not is_discord_alerts_enabled(db):
        return False, "Disabled"

    sent = send_discord_message(message)
    return sent, ("Sent" if sent else "Failed")


# =========================================================
# CREATE INCIDENT ALERT
# =========================================================

def create_incident_alert(db, incident_id, api, reason):
    """Record an incident alert and send it to Discord when enabled."""
    try:
        message = (
            "🚨 API INCIDENT\n\n"
            f"API: {api['name']}\n"
            "Status: DOWN\n"
            f"Reason: {reason or 'API request failed.'}\n"
            f"Incident ID: {incident_id}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        discord_sent, alert_status = _send_or_disable_discord(db, message)

        db.session.execute(
            text("""
                INSERT INTO alerts (
                    incident_id, alert_type, channel, message, sent_at, status
                ) VALUES (
                    :incident_id, 'Incident', 'Discord', :message, :sent_at, :status
                )
            """),
            {
                "incident_id": incident_id,
                "message": message,
                "sent_at": datetime.now(),
                "status": alert_status
            }
        )
        db.session.commit()

        print(
            f"[ALERT CREATED] Incident ID: {incident_id} | "
            f"API: {api['name']} | Discord: {alert_status}"
        )
        return discord_sent

    except Exception as e:
        db.session.rollback()
        print(
            f"[ALERT ERROR] Could not create incident alert "
            f"for incident {incident_id}: {e}"
        )
        return False


# =========================================================
# CREATE RECOVERY ALERT
# =========================================================

def create_recovery_alert(db, incident_id, api):
    """Record a recovery alert and send it to Discord when enabled."""
    try:
        message = (
            "✅ API RECOVERY\n\n"
            f"API: {api['name']}\n"
            "Status: UP\n"
            "The previous incident has been resolved.\n"
            f"Incident ID: {incident_id}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        discord_sent, alert_status = _send_or_disable_discord(db, message)

        db.session.execute(
            text("""
                INSERT INTO alerts (
                    incident_id, alert_type, channel, message, sent_at, status
                ) VALUES (
                    :incident_id, 'Recovery', 'Discord', :message, :sent_at, :status
                )
            """),
            {
                "incident_id": incident_id,
                "message": message,
                "sent_at": datetime.now(),
                "status": alert_status
            }
        )
        db.session.commit()

        print(
            f"[RECOVERY ALERT CREATED] Incident ID: {incident_id} | "
            f"API: {api['name']} | Discord: {alert_status}"
        )
        return discord_sent

    except Exception as e:
        db.session.rollback()
        print(
            f"[ALERT ERROR] Could not create recovery alert "
            f"for incident {incident_id}: {e}"
        )
        return False
