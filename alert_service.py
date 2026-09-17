from datetime import datetime
import os
import requests

from sqlalchemy import text


# =========================================================
# DISCORD CONFIGURATION
# =========================================================

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


# =========================================================
# SEND MESSAGE TO DISCORD
# =========================================================

def send_discord_message(message):
    """
    Send an alert message to the configured Discord channel.
    """

    if not DISCORD_WEBHOOK_URL:
        print("[DISCORD ERROR] Webhook URL is not configured.")
        return False

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": message
            },
            timeout=10
        )

        if response.status_code in [200, 204]:
            print("[DISCORD] Alert sent successfully.")
            return True

        print(
            f"[DISCORD ERROR] "
            f"HTTP {response.status_code}: {response.text}"
        )

        return False

    except requests.RequestException as e:
        print(
            f"[DISCORD ERROR] "
            f"Could not send message: {e}"
        )

        return False


# =========================================================
# CREATE INCIDENT ALERT
# =========================================================

def create_incident_alert(db, incident_id, api, reason):
    """
    Create an incident alert and send it to Discord.
    """

    try:

        # -------------------------------------------------
        # CREATE ALERT MESSAGE
        # -------------------------------------------------

        message = (
            "🚨 API INCIDENT\n\n"
            f"API: {api['name']}\n"
            "Status: DOWN\n"
            f"Reason: {reason or 'API request failed.'}\n"
            f"Incident ID: {incident_id}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # -------------------------------------------------
        # SEND TO DISCORD
        # -------------------------------------------------

        discord_sent = send_discord_message(message)

        # -------------------------------------------------
        # SAVE ALERT IN DATABASE
        # -------------------------------------------------

        db.session.execute(
            text("""
                INSERT INTO alerts (
                    incident_id,
                    alert_type,
                    channel,
                    message,
                    sent_at,
                    status
                )
                VALUES (
                    :incident_id,
                    'Incident',
                    'Discord',
                    :message,
                    :sent_at,
                    :status
                )
            """),
            {
                "incident_id": incident_id,
                "message": message,
                "sent_at": datetime.now(),
                "status": "Sent" if discord_sent else "Failed"
            }
        )

        db.session.commit()

        print(
            f"[ALERT CREATED] "
            f"Incident ID: {incident_id} | "
            f"API: {api['name']} | "
            f"Discord: {'Sent' if discord_sent else 'Failed'}"
        )

        return discord_sent

    except Exception as e:

        db.session.rollback()

        print(
            f"[ALERT ERROR] "
            f"Could not create incident alert "
            f"for incident {incident_id}: {e}"
        )

        return False


# =========================================================
# CREATE RECOVERY ALERT
# =========================================================

def create_recovery_alert(db, incident_id, api):
    """
    Create a recovery alert and send it to Discord.
    """

    try:

        # -------------------------------------------------
        # CREATE RECOVERY MESSAGE
        # -------------------------------------------------

        message = (
            "✅ API RECOVERY\n\n"
            f"API: {api['name']}\n"
            "Status: UP\n"
            "The previous incident has been resolved.\n"
            f"Incident ID: {incident_id}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # -------------------------------------------------
        # SEND TO DISCORD
        # -------------------------------------------------

        discord_sent = send_discord_message(message)

        # -------------------------------------------------
        # SAVE ALERT IN DATABASE
        # -------------------------------------------------

        db.session.execute(
            text("""
                INSERT INTO alerts (
                    incident_id,
                    alert_type,
                    channel,
                    message,
                    sent_at,
                    status
                )
                VALUES (
                    :incident_id,
                    'Recovery',
                    'Discord',
                    :message,
                    :sent_at,
                    :status
                )
            """),
            {
                "incident_id": incident_id,
                "message": message,
                "sent_at": datetime.now(),
                "status": "Sent" if discord_sent else "Failed"
            }
        )

        db.session.commit()

        print(
            f"[RECOVERY ALERT CREATED] "
            f"Incident ID: {incident_id} | "
            f"API: {api['name']} | "
            f"Discord: {'Sent' if discord_sent else 'Failed'}"
        )

        return discord_sent

    except Exception as e:

        db.session.rollback()

        print(
            f"[ALERT ERROR] "
            f"Could not create recovery alert "
            f"for incident {incident_id}: {e}"
        )

        return False
