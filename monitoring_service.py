import time
import requests
from http_status_utils import http_status_label

from datetime import datetime

from sqlalchemy import text

from incident_service import (
    handle_api_failure,
    handle_api_recovery
)


# =========================================================
# CHECK ONE API
# =========================================================

def check_api(db, api):

    start_time = time.perf_counter()

    status_code = None
    response_time_ms = None
    success = False
    error_message = None

    # -----------------------------------------------------
    # THIS IS THE TIME OF THIS PARTICULAR CHECK
    # -----------------------------------------------------

    checked_at = datetime.now()

    try:

        # -------------------------------------------------
        # SEND HTTP REQUEST
        # -------------------------------------------------

        response = requests.request(
            method=api["method"],
            url=api["url"],
            timeout=api["timeout_seconds"]
        )

        # -------------------------------------------------
        # CALCULATE RESPONSE TIME
        # -------------------------------------------------

        end_time = time.perf_counter()

        response_time_ms = round(
            (end_time - start_time) * 1000,
            2
        )

        status_code = response.status_code

        # -------------------------------------------------
        # CHECK EXPECTED STATUS
        # -------------------------------------------------

        if status_code == api["expected_status"]:

            success = True

        else:

            success = False

            error_message = (
                f"{http_status_label(status_code)}. "
                f"Expected HTTP {api['expected_status']}."
            )

    except requests.exceptions.Timeout:

        end_time = time.perf_counter()

        response_time_ms = round(
            (end_time - start_time) * 1000,
            2
        )

        error_message = "Request timed out."

    except requests.exceptions.ConnectionError:

        end_time = time.perf_counter()

        response_time_ms = round(
            (end_time - start_time) * 1000,
            2
        )

        error_message = "Connection error."

    except requests.exceptions.RequestException as e:

        end_time = time.perf_counter()

        response_time_ms = round(
            (end_time - start_time) * 1000,
            2
        )

        error_message = str(e)

    except Exception as e:

        end_time = time.perf_counter()

        response_time_ms = round(
            (end_time - start_time) * 1000,
            2
        )

        error_message = str(e)


    # =====================================================
    # SAVE MONITORING LOG
    # =====================================================

    try:

        db.session.execute(
            text("""
                INSERT INTO monitoring_logs (
                    api_id,
                    status_code,
                    response_time_ms,
                    success,
                    error_message,
                    checked_at
                )

                VALUES (
                    :api_id,
                    :status_code,
                    :response_time_ms,
                    :success,
                    :error_message,
                    :checked_at
                )
            """),
            {
                "api_id": api["id"],
                "status_code": status_code,
                "response_time_ms": response_time_ms,
                "success": success,
                "error_message": error_message,
                "checked_at": checked_at
            }
        )

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            f"[MONITORING LOG ERROR] "
            f"API {api['id']}: {e}"
        )

        return {
            "success": False,
            "error": str(e)
        }


    # =====================================================
    # INCIDENT MANAGEMENT
    # =====================================================

    if success:

        # API is UP.
        # If an OPEN incident exists,
        # resolve it immediately.

        handle_api_recovery(
            db,
            api,
            checked_at
        )

    else:

        # API is DOWN.
        # Create an OPEN incident immediately.
        # If one already exists, incident_service
        # will prevent a duplicate.

        handle_api_failure(
            db,
            api,
            error_message,
            checked_at
        )


    # =====================================================
    # DISPLAY RESULT
    # =====================================================

    if success:

        print(
            f"[UP] {api['name']} | "
            f"HTTP {status_code} | "
            f"{response_time_ms} ms"
        )

    else:

        print(
            f"[DOWN] {api['name']} | "
            f"HTTP {status_code or 'N/A'} | "
            f"{error_message}"
        )


    return {
        "success": success,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "error_message": error_message
    }


# =========================================================
# CHECK ALL ACTIVE APIS
# =========================================================

def check_all_apis(db):

    try:

        rows = db.session.execute(
            text("""
                SELECT
                    id,
                    name,
                    url,
                    method,
                    expected_status,
                    timeout_seconds

                FROM apis

                WHERE is_active = TRUE

                ORDER BY id
            """)
        ).mappings().all()


        if not rows:

            print(
                "[MONITORING] "
                "No active APIs found."
            )

            return


        print()

        print(
            f"[MONITORING] "
            f"Checking {len(rows)} active API(s)..."
        )

        print()


        for api in rows:

            check_api(
                db,
                api
            )


    except Exception as e:

        db.session.rollback()

        print(
            f"[MONITORING ERROR] {e}"
        )
