import os
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    session,
    request,
    jsonify,
    flash
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from sqlalchemy import text

from datetime import datetime, timedelta

from models import (
    db,
    Admin,
    SystemSetting
)

from apscheduler.schedulers.background import BackgroundScheduler

from monitoring_service import check_all_apis
from report_service import generate_report
from report_notification_service import send_report_to_discord as send_report_message_to_discord
from alert_service import send_discord_message
from http_status_utils import http_status_label
# =========================================================
# PATH CONFIGURATION
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(
    BASE_DIR,
    "flask_jinja_templates",
    "templates"
)

STATIC_DIR = os.path.join(
    BASE_DIR,
    "flask_jinja_templates",
    "static"
)


# =========================================================
# FLASK APPLICATION
# =========================================================

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR
)

app.jinja_env.filters["http_status_label"] = http_status_label


# =========================================================
# APPLICATION CONFIGURATION
# =========================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key-change-later"
)


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "postgresql://pranav@localhost:5432/api_monitoring"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


# =========================================================
# LOGIN REQUIRED
# =========================================================

def login_required(view_function):

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if "admin_logged_in" not in session:
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view

# =========================================================
# SETTINGS HELPERS
# =========================================================

def get_setting(key, default=None):

    setting = SystemSetting.query.filter_by(
        key=key
    ).first()

    if setting is None:
        return default

    return setting.value


def save_setting(key, value):

    setting = SystemSetting.query.filter_by(
        key=key
    ).first()

    if setting is None:

        setting = SystemSetting(
            key=key,
            value=value
        )

        db.session.add(setting)

    else:

        setting.value = value

    db.session.commit()
# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if "admin_logged_in" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not password:

            return render_template(
                "login.html",
                error="Please enter username and password."
            )

        admin = Admin.query.filter_by(
            username=username
        ).first()

        if admin and check_password_hash(
            admin.password_hash,
            password
        ):

            session.clear()

            session["admin_logged_in"] = True
            session["admin_id"] = admin.id
            session["admin_username"] = admin.username

            return redirect(
                url_for("dashboard")
            )

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    return render_template("login.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_required
def dashboard():

    try:
        # =====================================================
        # 1. GET ALL APIS WITH LATEST MONITORING RESULT
        # =====================================================

        api_rows = db.session.execute(
            text("""
                SELECT
                    a.id,
                    a.name,
                    a.url,
                    a.method,

                    ml.status_code AS last_status_code,
                    ml.response_time_ms AS last_response_time,
                    ml.success AS last_success,
                    ml.checked_at AS last_checked

                FROM apis a

                LEFT JOIN LATERAL (
                    SELECT
                        status_code,
                        response_time_ms,
                        success,
                        checked_at

                    FROM monitoring_logs

                    WHERE monitoring_logs.api_id = a.id

                    ORDER BY checked_at DESC

                    LIMIT 1

                ) ml ON TRUE

                ORDER BY a.id DESC
            """)
        ).mappings().all()


        # =====================================================
        # 2. BUILD API DATA
        # =====================================================

        apis = []

        for row in api_rows:

            # Current status
            if row["last_success"] is True:
                status = "UP"

            elif row["last_success"] is False:
                status = "DOWN"

            else:
                status = "DOWN"


            # Response time
            if row["last_response_time"] is not None:
                response_time = round(
                    float(row["last_response_time"]),
                    2
                )
            else:
                response_time = None


            # Last checked
            if row["last_checked"] is not None:
                last_checked = row["last_checked"].strftime(
                    "%d %b %Y, %H:%M:%S"
                )
            else:
                last_checked = "Never"


            # Active incident
            active_incident = db.session.execute(
                text("""
                    SELECT incident_code
                    FROM incidents
                    WHERE api_id = :api_id
                      AND status = 'OPEN'
                    ORDER BY started_at DESC
                    LIMIT 1
                """),
                {
                    "api_id": row["id"]
                }
            ).scalar()


            apis.append({
                "id": row["id"],
                "name": row["name"],
                "url": row["url"],
                "method": row["method"],

                "status": status,

                "icon_class": "bi-cloud-arrow-up",

                "last_status_code": (
                    row["last_status_code"]
                    if row["last_status_code"] is not None
                    else "—"
                ),

                "last_response_time": response_time,

                "last_checked": last_checked,

                "active_incident_code": active_incident
            })


        # =====================================================
        # 3. SUMMARY CARDS
        # =====================================================

        total_apis = len(apis)

        apis_up = sum(
            1
            for api in apis
            if api["status"] == "UP"
        )

        apis_down = sum(
            1
            for api in apis
            if api["status"] == "DOWN"
        )


        # =====================================================
        # 4. ACTIVE INCIDENTS
        # =====================================================

        active_incidents = db.session.execute(
            text("""
                SELECT COUNT(*)
                FROM incidents
                WHERE status = 'OPEN'
            """)
        ).scalar() or 0


        # =====================================================
        # 5. OVERALL UPTIME
        # =====================================================

        uptime_result = db.session.execute(
            text("""
                SELECT
                    COALESCE(
                        ROUND(
                            100.0 *
                            SUM(
                                CASE
                                    WHEN success = TRUE THEN 1
                                    ELSE 0
                                END
                            )
                            /
                            NULLIF(COUNT(*), 0),
                            2
                        ),
                        0
                    ) AS uptime
                FROM monitoring_logs
            """)
        ).scalar()

        overall_uptime = float(uptime_result or 0)


        # =====================================================
        # 6. AVERAGE RESPONSE TIME
        # =====================================================

        response_result = db.session.execute(
            text("""
                SELECT
                    COALESCE(
                        AVG(response_time_ms),
                        0
                    )
                FROM monitoring_logs
                WHERE response_time_ms IS NOT NULL
            """)
        ).scalar()

        avg_response_time = round(
            float(response_result or 0),
            2
        )


        # =====================================================
        # 7. RECENT INCIDENTS
        # =====================================================

        incident_rows = db.session.execute(
            text("""
                SELECT
                    i.id,
                    i.api_id,
                    i.reason,
                    i.started_at,
                    i.resolved_at,
                    i.status,
                    a.name AS api_name

                FROM incidents i

                JOIN apis a
                    ON a.id = i.api_id

                ORDER BY
                    COALESCE(i.resolved_at, i.started_at) DESC

                LIMIT 5
            """)
        ).mappings().all()


        recent_incidents = []

        for incident in incident_rows:

            if incident["status"] == "OPEN":
                display_status = "ACTIVE"
                event_time = incident["started_at"]

            else:
                display_status = "RESOLVED"
                event_time = (
                    incident["resolved_at"]
                    if incident["resolved_at"]
                    else incident["started_at"]
                )


            # Calculate time ago
            seconds = int(
                (
                    datetime.now() - event_time
                ).total_seconds()
            )

            if seconds < 60:
                time_ago = f"{seconds} sec ago"

            elif seconds < 3600:
                time_ago = f"{seconds // 60} min ago"

            elif seconds < 86400:
                time_ago = f"{seconds // 3600} hr ago"

            else:
                time_ago = f"{seconds // 86400} days ago"


            recent_incidents.append({
                "id": incident["id"],
                "api_name": incident["api_name"],
                "reason": incident["reason"],
                "status": display_status,
                "time_ago": time_ago
            })


        # =====================================================
        # 8. RECENT ALERTS
        # =====================================================

        alert_rows = db.session.execute(
            text("""
                SELECT
                    al.id,
                    al.alert_type,
                    al.channel,
                    al.message,
                    al.sent_at,
                    al.status,
                    a.name AS api_name

                FROM alerts al

                JOIN incidents i
                    ON al.incident_id = i.id

                JOIN apis a
                    ON i.api_id = a.id

                ORDER BY al.sent_at DESC

                LIMIT 5
            """)
        ).mappings().all()


        recent_alerts = []

        for alert in alert_rows:

            seconds = int(
                (
                    datetime.now() - alert["sent_at"]
                ).total_seconds()
            )

            if seconds < 60:
                time_ago = f"{seconds} sec ago"

            elif seconds < 3600:
                time_ago = f"{seconds // 60} min ago"

            elif seconds < 86400:
                time_ago = f"{seconds // 3600} hr ago"

            else:
                time_ago = f"{seconds // 86400} days ago"


            recent_alerts.append({
                "id": alert["id"],
                "api_name": alert["api_name"],
                "channel": alert["channel"],
                "status": str(
                    alert["status"]
                ).upper(),
                "description": alert["message"],
                "time_ago": time_ago
            })


        # =====================================================
        # 9. RENDER DASHBOARD
        # =====================================================

        return render_template(
            "dashboard.html",

            total_apis=total_apis,
            apis_up=apis_up,
            apis_down=apis_down,

            active_incidents=active_incidents,

            overall_uptime=overall_uptime,
            avg_response_time=avg_response_time,

            apis=apis,

            recent_incidents=recent_incidents,
            recent_alerts=recent_alerts
        )


    except Exception as e:

        db.session.rollback()

        print("[DASHBOARD ERROR]", e)

        return render_template(
            "dashboard.html",

            total_apis=0,
            apis_up=0,
            apis_down=0,

            active_incidents=0,

            overall_uptime=0,
            avg_response_time=0,

            apis=[],
            recent_incidents=[],
            recent_alerts=[]
        )
# =========================================================
# API MANAGEMENT
# =========================================================

@app.route("/api-management")
@login_required
def api_management():

    # -----------------------------------------------------
    # GET ALL APIS
    # -----------------------------------------------------

    api_rows = db.session.execute(
        text("""
            SELECT
                a.id,
                a.name,
                a.url,
                a.method,
                a.expected_status,
                a.interval_seconds,
                a.timeout_seconds,
                a.is_active,
                a.created_at,

                ml.status_code AS last_status_code,
                ml.response_time_ms AS last_response_time,
                ml.success AS last_success,
                ml.checked_at AS last_checked

            FROM apis a

            LEFT JOIN LATERAL (
                SELECT
                    status_code,
                    response_time_ms,
                    success,
                    checked_at

                FROM monitoring_logs

                WHERE api_id = a.id

                ORDER BY checked_at DESC

                LIMIT 1
            ) ml ON TRUE

            ORDER BY a.id DESC
        """)
    ).mappings().all()


    # -----------------------------------------------------
    # BUILD API DATA FOR TEMPLATE
    # -----------------------------------------------------

    apis = []

    for row in api_rows:

        # ---------------------------------------------
        # CURRENT STATUS
        # ---------------------------------------------

        if row["last_success"] is True:
            status = "UP"
        else:
            status = "DOWN"


        # ---------------------------------------------
        # RESPONSE TIME
        # ---------------------------------------------

        if row["last_response_time"] is not None:

            response_time = round(
                float(row["last_response_time"]),
                2
            )

        else:

            response_time = None


        # ---------------------------------------------
        # INCIDENT COUNT
        # ---------------------------------------------

        incident_count = db.session.execute(
            text("""
                SELECT COUNT(*)
                FROM incidents
                WHERE api_id = :api_id
            """),
            {
                "api_id": row["id"]
            }
        ).scalar()


        # ---------------------------------------------
        # UPTIME
        # ---------------------------------------------

        uptime = db.session.execute(
            text("""
                SELECT
                    COALESCE(
                        ROUND(
                            100.0 *
                            SUM(
                                CASE
                                    WHEN success = TRUE THEN 1
                                    ELSE 0
                                END
                            )
                            /
                            NULLIF(COUNT(*), 0),
                            2
                        ),
                        0
                    )
                FROM monitoring_logs
                WHERE api_id = :api_id
            """),
            {
                "api_id": row["id"]
            }
        ).scalar()


        if uptime is None:
            uptime = 0


        # ---------------------------------------------
        # RECENT MONITORING LOGS
        # ---------------------------------------------

        log_rows = db.session.execute(
            text("""
                SELECT
                    checked_at,
                    status_code,
                    response_time_ms,
                    success

                FROM monitoring_logs

                WHERE api_id = :api_id

                ORDER BY checked_at DESC

                LIMIT 5
            """),
            {
                "api_id": row["id"]
            }
        ).mappings().all()


        recent_logs = []

        for log in log_rows:

            recent_logs.append({
                "checked_at": log["checked_at"],
                "status_code": log["status_code"] or "—",
                "response_time_ms": (
                    round(float(log["response_time_ms"]), 2)
                    if log["response_time_ms"] is not None
                    else "—"
                ),
                "success": log["success"]
            })


        # ---------------------------------------------
        # ICON
        # ---------------------------------------------

        icon_class = "bi-cloud-arrow-up"


        # ---------------------------------------------
        # CREATE TEMPLATE OBJECT
        # ---------------------------------------------

        api_data = {
            "id": row["id"],
            "name": row["name"],
            "url": row["url"],
            "method": row["method"],
            "expected_status": row["expected_status"],
            "interval_seconds": row["interval_seconds"],
            "timeout_seconds": row["timeout_seconds"],
            "is_active": row["is_active"],

            "status": status,

            "icon_class": icon_class,

            "last_response_time": response_time,

            "uptime": uptime,

            "incident_count": incident_count,

            "last_checked": (
                row["last_checked"]
                if row["last_checked"] is not None
                else "Never"
            ),

            "recent_logs": recent_logs
        }

        apis.append(api_data)


    # -----------------------------------------------------
    # SUMMARY COUNTS
    # -----------------------------------------------------

    total_apis = len(apis)

    apis_up = sum(
        1
        for api in apis
        if api["status"] == "UP"
    )

    apis_down = total_apis - apis_up


    # -----------------------------------------------------
    # RENDER PAGE
    # -----------------------------------------------------

    return render_template(
        "api_management.html",

        apis=apis,

        total_apis=total_apis,

        apis_up=apis_up,

        apis_down=apis_down
    )


# =========================================================
# ADD API
# =========================================================

@app.route("/api-management/add", methods=["POST"])
@login_required
def add_api():

    # -----------------------------------------------------
    # GET FORM DATA
    # -----------------------------------------------------

    name = request.form.get(
        "name",
        ""
    ).strip()

    url = request.form.get(
        "url",
        ""
    ).strip()

    method = request.form.get(
        "method",
        "GET"
    ).upper()

    expected_status = request.form.get(
        "expected_status",
        "200"
    )

    interval_seconds = request.form.get(
        "interval_seconds",
        "60"
    )

    timeout_seconds = request.form.get(
        "timeout_seconds",
        "5"
    )


    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not name or not url:

        flash(
            "API name and URL are required.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    allowed_methods = {
        "GET",
        "POST",
        "PUT",
        "DELETE"
    }

    if method not in allowed_methods:

        flash(
            "Invalid HTTP method.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    try:

        expected_status = int(
            expected_status
        )

        interval_seconds = int(
            interval_seconds
        )

        timeout_seconds = int(
            timeout_seconds
        )

    except ValueError:

        flash(
            "Status, interval and timeout must be valid numbers.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    if not 100 <= expected_status <= 599:

        flash(
            "Expected status must be between 100 and 599.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    if interval_seconds < 1:

        flash(
            "Monitoring interval must be at least 1 second.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    if timeout_seconds < 1:

        flash(
            "Timeout must be at least 1 second.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    # -----------------------------------------------------
    # INSERT INTO DATABASE
    # -----------------------------------------------------

    try:

        db.session.execute(
            text("""
                INSERT INTO apis (
                    name,
                    url,
                    method,
                    expected_status,
                    interval_seconds,
                    timeout_seconds,
                    is_active,
                    created_at
                )

                VALUES (
                    :name,
                    :url,
                    :method,
                    :expected_status,
                    :interval_seconds,
                    :timeout_seconds,
                    TRUE,
                    CURRENT_TIMESTAMP
                )
            """),
            {
                "name": name,
                "url": url,
                "method": method,
                "expected_status": expected_status,
                "interval_seconds": interval_seconds,
                "timeout_seconds": timeout_seconds
            }
        )

        db.session.commit()

        flash(
            f'API "{name}" added successfully.',
            "success"
        )

    except Exception as e:

        db.session.rollback()

        print("ADD API ERROR:", e)

        flash(
            "Unable to add API. Please check the server logs.",
            "danger"
        )


    return redirect(
        url_for("api_management")
    )


# =========================================================
# EDIT API
# =========================================================

@app.route("/api-management/edit/<int:id>", methods=["POST"])
@login_required
def edit_api(id):

    # -----------------------------------------------------
    # GET FORM DATA
    # -----------------------------------------------------

    name = request.form.get(
        "name",
        ""
    ).strip()

    url = request.form.get(
        "url",
        ""
    ).strip()

    method = request.form.get(
        "method",
        "GET"
    ).upper()

    expected_status = request.form.get(
        "expected_status",
        "200"
    )

    interval_seconds = request.form.get(
        "interval_seconds",
        "60"
    )

    timeout_seconds = request.form.get(
        "timeout_seconds",
        "5"
    )


    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not name or not url:

        flash(
            "API name and URL are required.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    try:

        expected_status = int(
            expected_status
        )

        interval_seconds = int(
            interval_seconds
        )

        timeout_seconds = int(
            timeout_seconds
        )

    except ValueError:

        flash(
            "Status, interval and timeout must be valid numbers.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    if method not in {
        "GET",
        "POST",
        "PUT",
        "DELETE"
    }:

        flash(
            "Invalid HTTP method.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    if not 100 <= expected_status <= 599:

        flash(
            "Expected status must be between 100 and 599.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    if interval_seconds < 1 or timeout_seconds < 1:

        flash(
            "Interval and timeout must be at least 1 second.",
            "danger"
        )

        return redirect(
            url_for("api_management")
        )


    # -----------------------------------------------------
    # UPDATE DATABASE
    # -----------------------------------------------------

    try:

        result = db.session.execute(
            text("""
                UPDATE apis

                SET
                    name = :name,
                    url = :url,
                    method = :method,
                    expected_status = :expected_status,
                    interval_seconds = :interval_seconds,
                    timeout_seconds = :timeout_seconds

                WHERE id = :id
            """),
            {
                "id": id,
                "name": name,
                "url": url,
                "method": method,
                "expected_status": expected_status,
                "interval_seconds": interval_seconds,
                "timeout_seconds": timeout_seconds
            }
        )


        if result.rowcount == 0:

            db.session.rollback()

            flash(
                "API not found.",
                "danger"
            )

            return redirect(
                url_for("api_management")
            )


        db.session.commit()

        flash(
            f'API "{name}" updated successfully.',
            "success"
        )

    except Exception as e:

        db.session.rollback()

        print("EDIT API ERROR:", e)

        flash(
            "Unable to update API.",
            "danger"
        )


    return redirect(
        url_for("api_management")
    )


# =========================================================
# DELETE API
# =========================================================

@app.route("/api-management/delete/<int:id>", methods=["POST"])
@login_required
def delete_api(id):

    try:

        # -------------------------------------------------
        # CHECK API EXISTS
        # -------------------------------------------------

        api = db.session.execute(
            text("""
                SELECT name
                FROM apis
                WHERE id = :id
            """),
            {
                "id": id
            }
        ).mappings().first()


        if not api:

            flash(
                "API not found.",
                "danger"
            )

            return redirect(
                url_for("api_management")
            )


        api_name = api["name"]


        # -------------------------------------------------
        # DELETE ALERTS CONNECTED TO INCIDENTS
        # -------------------------------------------------

        db.session.execute(
            text("""
                DELETE FROM alerts
                WHERE incident_id IN (
                    SELECT id
                    FROM incidents
                    WHERE api_id = :api_id
                )
            """),
            {
                "api_id": id
            }
        )


        # -------------------------------------------------
        # DELETE INCIDENTS
        # -------------------------------------------------

        db.session.execute(
            text("""
                DELETE FROM incidents
                WHERE api_id = :api_id
            """),
            {
                "api_id": id
            }
        )


        # -------------------------------------------------
        # DELETE MONITORING LOGS
        # -------------------------------------------------

        db.session.execute(
            text("""
                DELETE FROM monitoring_logs
                WHERE api_id = :api_id
            """),
            {
                "api_id": id
            }
        )


        # -------------------------------------------------
        # DELETE API
        # -------------------------------------------------

        db.session.execute(
            text("""
                DELETE FROM apis
                WHERE id = :api_id
            """),
            {
                "api_id": id
            }
        )


        db.session.commit()

        flash(
            f'API "{api_name}" deleted successfully.',
            "success"
        )

    except Exception as e:

        db.session.rollback()

        print("DELETE API ERROR:", e)

        flash(
            "Unable to delete API.",
            "danger"
        )


    return redirect(
        url_for("api_management")
    )


# =========================================================
# MONITORING
# =========================================================

@app.route("/monitoring")
@login_required
def monitoring():

    # =========================================================
    # 1. MONITORING SUMMARY - LAST 24 HOURS
    # =========================================================

    summary = db.session.execute(
        text("""
            SELECT
                COUNT(*) AS total_checks,
                COUNT(*) FILTER (WHERE success = TRUE) AS successful_checks,
                COUNT(*) FILTER (WHERE success = FALSE) AS failed_checks,
                COALESCE(AVG(response_time_ms), 0) AS avg_response_time
            FROM monitoring_logs
            WHERE checked_at >= NOW() - INTERVAL '24 hours'
        """)
    ).mappings().first()

    total_checks = summary["total_checks"] or 0
    successful_checks = summary["successful_checks"] or 0
    failed_checks = summary["failed_checks"] or 0

    avg_response_time = round(
        float(summary["avg_response_time"] or 0),
        2
    )

    # Calculate percentages safely
    if total_checks > 0:
        successful_percent = round(
            (successful_checks / total_checks) * 100,
            2
        )

        failed_percent = round(
            (failed_checks / total_checks) * 100,
            2
        )
    else:
        successful_percent = 0
        failed_percent = 0


    # =========================================================
    # 2. CURRENT API HEALTH
    # =========================================================

    api_rows = db.session.execute(
        text("""
            SELECT
                a.id,
                a.name,
                a.url,
                a.method,
                a.interval_seconds,
                a.is_active,

                ml.status_code AS last_status_code,
                ml.response_time_ms AS last_response_time,
                ml.success AS last_success,
                ml.checked_at AS last_checked

            FROM apis a

            LEFT JOIN LATERAL (
                SELECT
                    status_code,
                    response_time_ms,
                    success,
                    checked_at

                FROM monitoring_logs

                WHERE monitoring_logs.api_id = a.id

                ORDER BY checked_at DESC

                LIMIT 1
            ) ml ON TRUE

            ORDER BY a.id
        """)
    ).mappings().all()


    apis = []

    for api in api_rows:

        # -----------------------------------------------------
        # Determine current status
        # -----------------------------------------------------

        if api["last_success"] is True:
            status = "UP"

        else:
            status = "DOWN"


        # -----------------------------------------------------
        # Calculate uptime
        # -----------------------------------------------------

        uptime_result = db.session.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE success = TRUE
                    ) AS successful

                FROM monitoring_logs

                WHERE api_id = :api_id
            """),
            {
                "api_id": api["id"]
            }
        ).mappings().first()


        total_api_checks = uptime_result["total"] or 0
        successful_api_checks = uptime_result["successful"] or 0


        if total_api_checks > 0:

            uptime = round(
                (successful_api_checks / total_api_checks) * 100,
                2
            )

        else:

            uptime = 0


        # -----------------------------------------------------
        # Last checked
        # -----------------------------------------------------

        if api["last_checked"]:

            last_checked = api["last_checked"].strftime(
                "%d %b %Y, %H:%M:%S"
            )

        else:

            last_checked = "Never"


        # -----------------------------------------------------
        # Next check
        # -----------------------------------------------------

        if api["last_checked"]:

            from datetime import timedelta

            next_check_time = (
                api["last_checked"]
                + timedelta(
                    seconds=api["interval_seconds"]
                )
            )

            next_check = next_check_time.strftime(
                "%d %b %Y, %H:%M:%S"
            )

        else:

            next_check = "Pending"


        # -----------------------------------------------------
        # Icon
        # -----------------------------------------------------

        icon_class = "bi-globe2"


        apis.append({
            "id": api["id"],
            "name": api["name"],
            "url": api["url"],
            "method": api["method"],
            "status": status,
            "last_status_code": (
                api["last_status_code"]
                if api["last_status_code"] is not None
                else "—"
            ),
            "last_response_time": (
                round(float(api["last_response_time"]), 2)
                if api["last_response_time"] is not None
                else None
            ),
            "uptime": uptime,
            "last_checked": last_checked,
            "next_check": next_check,
            "icon_class": icon_class,
            "is_active": api["is_active"]
        })


    # =========================================================
    # 3. MONITORING HISTORY
    # =========================================================

    monitoring_logs = db.session.execute(
        text("""
            SELECT
                ml.id,
                ml.checked_at,
                ml.status_code,
                ml.response_time_ms,
                ml.success,
                ml.error_message,
                a.name AS api_name

            FROM monitoring_logs ml

            INNER JOIN apis a
                ON a.id = ml.api_id

            ORDER BY ml.checked_at DESC

            LIMIT 100
        """)
    ).mappings().all()


    # =========================================================
    # 4. RENDER PAGE
    # =========================================================

    return render_template(
        "monitoring.html",

        total_checks=total_checks,
        successful_checks=successful_checks,
        failed_checks=failed_checks,

        successful_percent=successful_percent,
        failed_percent=failed_percent,

        avg_response_time=avg_response_time,

        apis=apis,
        monitoring_logs=monitoring_logs
    )

@app.route("/monitoring/data")
@login_required
def monitoring_data():

    # ---------------------------------------------------------
    # Summary
    # ---------------------------------------------------------

    summary = db.session.execute(
        text("""
            SELECT
                COUNT(*) AS total_checks,
                COUNT(*) FILTER (WHERE success = TRUE) AS successful_checks,
                COUNT(*) FILTER (WHERE success = FALSE) AS failed_checks,
                COALESCE(AVG(response_time_ms), 0) AS avg_response_time
            FROM monitoring_logs
            WHERE checked_at >= NOW() - INTERVAL '24 hours'
        """)
    ).mappings().first()

    total_checks = summary["total_checks"] or 0
    successful_checks = summary["successful_checks"] or 0
    failed_checks = summary["failed_checks"] or 0

    avg_response_time = round(
        float(summary["avg_response_time"] or 0),
        2
    )

    if total_checks:
        successful_percent = round(
            successful_checks / total_checks * 100,
            2
        )
        failed_percent = round(
            failed_checks / total_checks * 100,
            2
        )
    else:
        successful_percent = 0
        failed_percent = 0


    # ---------------------------------------------------------
    # Latest result for every API
    # ---------------------------------------------------------

    api_rows = db.session.execute(
        text("""
            SELECT
                a.id,
                a.name,
                a.url,
                a.method,
                a.interval_seconds,
                a.is_active,

                ml.status_code,
                ml.response_time_ms,
                ml.success,
                ml.error_message,
                ml.checked_at

            FROM apis a

            LEFT JOIN LATERAL (
                SELECT
                    status_code,
                    response_time_ms,
                    success,
                    error_message,
                    checked_at

                FROM monitoring_logs

                WHERE monitoring_logs.api_id = a.id

                ORDER BY checked_at DESC

                LIMIT 1
            ) ml ON TRUE

            ORDER BY a.id
        """)
    ).mappings().all()


    apis = []

    for api in api_rows:

        if api["success"] is True:
            status = "UP"
        elif api["success"] is False:
            status = "DOWN"
        else:
            status = "PENDING"


        # Uptime
        uptime_result = db.session.execute(
            text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE success = TRUE
                    ) AS successful

                FROM monitoring_logs

                WHERE api_id = :api_id
            """),
            {"api_id": api["id"]}
        ).mappings().first()


        total_api_checks = uptime_result["total"] or 0
        successful_api_checks = uptime_result["successful"] or 0


        if total_api_checks:
            uptime = round(
                successful_api_checks /
                total_api_checks * 100,
                2
            )
        else:
            uptime = 0


        last_checked = (
            api["checked_at"].strftime("%d %b %Y, %H:%M:%S")
            if api["checked_at"]
            else "Never"
        )


        response_time = (
            round(float(api["response_time_ms"]), 2)
            if api["response_time_ms"] is not None
            else None
        )


        apis.append({
            "id": api["id"],
            "name": api["name"],
            "url": api["url"],
            "method": api["method"],
            "status": status,
            "status_code": api["status_code"],
            "response_time": response_time,
            "uptime": uptime,
            "last_checked": last_checked,
            "is_active": api["is_active"]
        })


    # ---------------------------------------------------------
    # Monitoring history
    # ---------------------------------------------------------

    logs = db.session.execute(
        text("""
            SELECT
                ml.id,
                ml.checked_at,
                ml.status_code,
                ml.response_time_ms,
                ml.success,
                ml.error_message,
                a.name AS api_name

            FROM monitoring_logs ml

            JOIN apis a
                ON a.id = ml.api_id

            ORDER BY ml.checked_at DESC

            LIMIT 100
        """)
    ).mappings().all()


    monitoring_logs = []

    for log in logs:

        monitoring_logs.append({
            "id": log["id"],
            "api_name": log["api_name"],
            "status_code": log["status_code"],
            "response_time": (
                round(float(log["response_time_ms"]), 2)
                if log["response_time_ms"] is not None
                else None
            ),
            "success": log["success"],
            "error_message": log["error_message"],
            "checked_at": (
                log["checked_at"].strftime(
                    "%d %b %Y, %H:%M:%S"
                )
                if log["checked_at"]
                else None
            )
        })


    # ---------------------------------------------------------
    # JSON response
    # ---------------------------------------------------------

    return jsonify({
        "summary": {
            "total_checks": total_checks,
            "successful_checks": successful_checks,
            "failed_checks": failed_checks,
            "successful_percent": successful_percent,
            "failed_percent": failed_percent,
            "avg_response_time": avg_response_time
        },

        "apis": apis,

        "monitoring_logs": monitoring_logs
    })

# =========================================================
# INCIDENTS
# =========================================================

@app.route("/incidents", defaults={"incident_id": None})
@app.route("/incidents/<int:incident_id>")
@login_required
def incidents(incident_id):

    # =====================================================
    # 1. INCIDENT SUMMARY
    # =====================================================

    summary = db.session.execute(
        text("""
            SELECT
                COUNT(*) AS total_incidents,

                COUNT(*) FILTER (
                    WHERE status = 'OPEN'
                ) AS active_incidents,

                COUNT(*) FILTER (
                    WHERE status = 'RESOLVED'
                ) AS resolved_incidents,

                COALESCE(
                    AVG(duration_seconds)
                    FILTER (
                        WHERE status = 'RESOLVED'
                    ),
                    0
                ) AS avg_resolution_seconds

            FROM incidents

            WHERE started_at >= NOW() - INTERVAL '30 days'
        """)
    ).mappings().first()


    total_incidents = summary["total_incidents"] or 0
    active_incidents = summary["active_incidents"] or 0
    resolved_incidents = summary["resolved_incidents"] or 0

    avg_resolution_seconds = float(
        summary["avg_resolution_seconds"] or 0
    )


    # =====================================================
    # 2. RESOLVED PERCENTAGE
    # =====================================================

    if total_incidents > 0:

        resolved_percent = round(
            (resolved_incidents / total_incidents) * 100,
            1
        )

    else:

        resolved_percent = 0


    # =====================================================
    # 3. FORMAT AVERAGE RESOLUTION TIME
    # =====================================================

    if avg_resolution_seconds < 60:

        avg_resolution_time = (
            f"{round(avg_resolution_seconds)} sec"
        )

    elif avg_resolution_seconds < 3600:

        minutes = int(avg_resolution_seconds // 60)
        seconds = int(avg_resolution_seconds % 60)

        avg_resolution_time = (
            f"{minutes}m {seconds}s"
        )

    else:

        hours = int(avg_resolution_seconds // 3600)
        minutes = int(
            (avg_resolution_seconds % 3600) // 60
        )

        avg_resolution_time = (
            f"{hours}h {minutes}m"
        )


    # =====================================================
    # 4. GET ALL APIS
    # =====================================================

    api_rows = db.session.execute(
        text("""
            SELECT
                id,
                name
            FROM apis
            ORDER BY name
        """)
    ).mappings().all()


    apis = []

    for api in api_rows:

        apis.append({
            "id": api["id"],
            "name": api["name"]
        })


    # =====================================================
    # 5. GET INCIDENT HISTORY
    # =====================================================

    incident_rows = db.session.execute(
        text("""
            SELECT
                i.id,
                i.incident_code,
                i.api_id,
                i.reason,
                i.started_at,
                i.resolved_at,
                i.duration_seconds,
                i.status,

                a.name AS api_name,
                a.url AS api_url,

                COUNT(al.id) AS alerts_sent

            FROM incidents i

            JOIN apis a
                ON a.id = i.api_id

            LEFT JOIN alerts al
                ON al.incident_id = i.id

            WHERE i.started_at >= NOW() - INTERVAL '30 days'

            GROUP BY
                i.id,
                i.incident_code,
                i.api_id,
                i.reason,
                i.started_at,
                i.resolved_at,
                i.duration_seconds,
                i.status,
                a.name,
                a.url

            ORDER BY i.started_at DESC
        """)
    ).mappings().all()


    incidents_data = []


    for incident in incident_rows:

        # -------------------------------------------------
        # STATUS FOR FRONTEND
        # -------------------------------------------------

        if incident["status"] == "OPEN":
            display_status = "Active"
        else:
            display_status = "Resolved"


        # -------------------------------------------------
        # ERROR TYPE
        # -------------------------------------------------

        reason = incident["reason"] or ""

        if "timeout" in reason.lower():

            error_type = "Timeout"

        elif "connection" in reason.lower():

            error_type = "Connection Error"

        elif "http" in reason.lower():

            error_type = "HTTP Error"

        else:

            error_type = "API Error"


        # -------------------------------------------------
        # STARTED AT
        # -------------------------------------------------

        started_at = (
            incident["started_at"].strftime(
                "%d %b %Y, %H:%M:%S"
            )
            if incident["started_at"]
            else "—"
        )


        # -------------------------------------------------
        # RESOLVED AT
        # -------------------------------------------------

        resolved_at = (
            incident["resolved_at"].strftime(
                "%d %b %Y, %H:%M:%S"
            )
            if incident["resolved_at"]
            else None
        )


        # -------------------------------------------------
        # DURATION
        # -------------------------------------------------

        duration_seconds = (
            incident["duration_seconds"] or 0
        )


        if duration_seconds < 60:

            duration = (
                f"{duration_seconds} sec"
            )

        elif duration_seconds < 3600:

            minutes = duration_seconds // 60
            seconds = duration_seconds % 60

            duration = (
                f"{minutes}m {seconds}s"
            )

        else:

            hours = duration_seconds // 3600
            minutes = (
                duration_seconds % 3600
            ) // 60

            duration = (
                f"{hours}h {minutes}m"
            )


        # -------------------------------------------------
        # ICON
        # -------------------------------------------------

        icon_class = "bi-cloud"


        # -------------------------------------------------
        # ALERT COUNT
        # -------------------------------------------------

        alerts_sent = int(
            incident["alerts_sent"] or 0
        )


        incidents_data.append({

            "id": incident["id"],

            "incident_code":
                incident["incident_code"],

            "api_id":
                incident["api_id"],

            "api_name":
                incident["api_name"],

            "api_url":
                incident["api_url"],

            "reason":
                incident["reason"],

            "error_type":
                error_type,

            "started_at":
                started_at,

            "resolved_at":
                resolved_at,

            "duration":
                duration,

            "status":
                display_status,

            "icon_class":
                icon_class,

            "alerts_sent":
                alerts_sent,

            # Alert channels will be connected later
            "discord_sent": alerts_sent > 0
                    })


    # =====================================================
    # 6. SELECTED INCIDENT
    # =====================================================

    selected_incident = None


    if incident_id is not None:

        for incident in incidents_data:

            if incident["id"] == incident_id:

                selected_incident = incident

                break


    # =====================================================
    # 7. RENDER INCIDENT PAGE
    # =====================================================

    return render_template(
        "incidents.html",

        total_incidents=total_incidents,

        active_incidents=active_incidents,

        resolved_incidents=resolved_incidents,

        resolved_percent=resolved_percent,

        avg_resolution_time=avg_resolution_time,

        apis=apis,

        incidents=incidents_data,

        selected_incident=selected_incident
    )
# ALERTS
# =========================================================

@app.route("/alerts")
@login_required
def alerts():

    try:
        # -------------------------------------------------
        # GET FILTER VALUES
        # -------------------------------------------------

        selected_channel = request.args.get("channel", "all")
        selected_event = request.args.get("event", "all")
        selected_period = request.args.get("period", "30")

        # -------------------------------------------------
        # VALIDATE PERIOD
        # -------------------------------------------------

        if selected_period not in ["1", "7", "30"]:
            selected_period = "30"

        period_days = int(selected_period)

        # -------------------------------------------------
        # BUILD FILTER CONDITIONS
        # -------------------------------------------------

        conditions = [
            "a.sent_at >= CURRENT_TIMESTAMP - (:period_days * INTERVAL '1 day')"
        ]

        params = {
            "period_days": period_days
        }


        # Channel filter
        if selected_channel == "Discord":
            conditions.append(
                "LOWER(a.channel) = LOWER(:channel)"
            )
            params["channel"] = selected_channel


        # Event filter
        if selected_event in ["Incident", "Recovery"]:
            conditions.append(
                "LOWER(a.alert_type) = LOWER(:event)"
            )
            params["event"] = selected_event

        # IMPORTANT:
        # Build WHERE clause AFTER all filters have been added
        where_clause = " AND ".join(conditions)
        # -------------------------------------------------
        # GET ALERT SUMMARY
        # -------------------------------------------------

        summary = db.session.execute(
            text(f"""
                SELECT
                    COUNT(*) AS total_alerts,

                    COUNT(*) FILTER (
                        WHERE a.status = 'Sent'
                    ) AS alerts_sent,

                    COUNT(*) FILTER (
                        WHERE a.status = 'Failed'
                    ) AS alerts_failed,

                    COUNT(*) FILTER (
                        WHERE a.channel = 'Discord'
                    ) AS discord_alerts

                FROM alerts a

                WHERE {where_clause}
            """),
            params
        ).mappings().first()

        total_alerts = summary["total_alerts"] or 0
        alerts_sent = summary["alerts_sent"] or 0
        alerts_failed = summary["alerts_failed"] or 0
        discord_alerts = summary["discord_alerts"] or 0

        # -------------------------------------------------
        # CALCULATE SUCCESS RATE
        # -------------------------------------------------

        if total_alerts > 0:
            alerts_success_rate = round(
                (alerts_sent / total_alerts) * 100,
                1
            )
        else:
            alerts_success_rate = 0

        # -------------------------------------------------
        # GET FILTERED ALERTS
        # -------------------------------------------------

        alert_rows = db.session.execute(
            text(f"""
                SELECT
                    a.id,
                    a.alert_type,
                    a.channel,
                    a.message,
                    a.sent_at,
                    a.status,
                    i.api_id,
                    ap.name AS api_name

                FROM alerts a

                JOIN incidents i
                    ON a.incident_id = i.id

                JOIN apis ap
                    ON i.api_id = ap.id

                WHERE {where_clause}

                ORDER BY a.sent_at DESC
            """),
            params
        ).mappings().all()

        # -------------------------------------------------
        # FORMAT ALERT DATA FOR TEMPLATE
        # -------------------------------------------------

        alerts_list = []

        for alert in alert_rows:

            alerts_list.append({
                "id": alert["id"],
                "alert_code": f"ALRT-{alert['id']:04d}",
                "api_name": alert["api_name"],
                "event": alert["alert_type"],
                "channel": alert["channel"],
                "sent_at": alert["sent_at"].strftime(
                    "%d %b %Y, %H:%M:%S"
                ),
                "status": alert["status"],
                "details": alert["message"]
            })

        # -------------------------------------------------
        # CHANNEL STATUS
        # -------------------------------------------------

        discord_channel_status = "Connected"        
        # -------------------------------------------------
        # RENDER ALERTS PAGE
        # -------------------------------------------------

        return render_template(
            "alerts.html",

            total_alerts=total_alerts,
            alerts_sent=alerts_sent,
            alerts_success_rate=alerts_success_rate,
            alerts_failed=alerts_failed,
            discord_alerts=discord_alerts,

            discord_channel_status=discord_channel_status,
            
            alerts=alerts_list,

            # Current filter selections
            selected_channel=selected_channel,
            selected_event=selected_event,
            selected_period=selected_period
        )

    except Exception as e:

        db.session.rollback()

        print(f"[ALERTS PAGE ERROR] {e}")

        return render_template(
            "alerts.html",

            total_alerts=0,
            alerts_sent=0,
            alerts_success_rate=0,
            alerts_failed=0,
            discord_alerts=0,

            discord_channel_status="Not Configured",
            
            alerts=[],

            selected_channel="all",
            selected_event="all",
            selected_period="30"
        )
# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
@login_required
def reports():

    # -----------------------------------------------------
    # GET FILTER VALUES
    # -----------------------------------------------------

    api_id = request.args.get(
        "api_id",
        "all"
    )

    time_period = request.args.get(
        "time_period",
        "30d"
    )

    report_type = request.args.get(
        "report_type",
        "performance"
    )

    # -----------------------------------------------------
    # VALIDATE FILTER VALUES
    # -----------------------------------------------------

    valid_periods = [
        "24h",
        "7d",
        "30d",
        "3m"
    ]

    valid_report_types = [
        "performance",
        "uptime",
        "incident"
    ]

    if time_period not in valid_periods:
        time_period = "30d"

    if report_type not in valid_report_types:
        report_type = "performance"

    if api_id != "all":
        try:
            api_id = int(api_id)
        except (ValueError, TypeError):
            api_id = "all"

    # -----------------------------------------------------
    # GET ALL APIS FOR FILTER DROPDOWN
    # -----------------------------------------------------

    api_rows = db.session.execute(
        text("""
            SELECT
                id,
                name
            FROM apis
            ORDER BY name
        """)
    ).mappings().all()

    apis = [
        {
            "id": api["id"],
            "name": api["name"]
        }
        for api in api_rows
    ]

    # -----------------------------------------------------
    # GENERATE REPORT
    # -----------------------------------------------------

    report = generate_report(
        db=db,
        api_id=api_id,
        time_period=time_period
    )

    # -----------------------------------------------------
    # RENDER REPORT PAGE
    # -----------------------------------------------------
    incident_data = report["incident_data"]
    total_incidents = report["total_incidents"]
    resolved_incidents = report["resolved_incidents"]
    open_incidents = report["open_incidents"]
    incident_downtime = report["incident_downtime"]

    return render_template(
        "reports.html",

        overall_uptime=report["overall_uptime"],
        avg_response_time=report["avg_response_time"],
        total_checks=report["total_checks"],
        total_downtime=report["total_downtime"],
        total_downtime_seconds=report[
            "total_downtime_seconds"
        ],

        report_data=report["report_data"],
        chart_data=report["chart_data"],
        incident_data=incident_data,
        report_period_label=report[
            "report_period_label"
        ],

        total_incidents=total_incidents,
        resolved_incidents=resolved_incidents,
        open_incidents=open_incidents,
        incident_downtime=incident_downtime,

        apis=apis,

        selected_api_id=api_id,
        selected_time_period=time_period,
        selected_report_type=report_type
    )
# =========================================================
# SEND REPORT TO DISCORD
# =========================================================

@app.route("/reports/send-discord", methods=["POST"])
@login_required
def send_report_discord():

    api_id = request.form.get("api_id", "all")
    time_period = request.form.get("time_period", "30d")
    report_type = request.form.get("report_type", "performance")

    valid_periods = [
        "24h",
        "7d",
        "30d",
        "3m"
    ]

    valid_report_types = [
        "performance",
        "uptime",
        "incident"
    ]

    if time_period not in valid_periods:
        time_period = "30d"

    if report_type not in valid_report_types:
        report_type = "performance"

    if api_id != "all":
        try:
            api_id = int(api_id)
        except (ValueError, TypeError):
            api_id = "all"

    # -----------------------------------------------------
    # API LABEL
    # -----------------------------------------------------

    if api_id == "all":
        api_label = "All APIs"
    else:
        api_row = db.session.execute(
            text("""
                SELECT name
                FROM apis
                WHERE id = :api_id
            """),
            {"api_id": api_id}
        ).mappings().first()

        if not api_row:
            flash("Selected API was not found.", "danger")
            return redirect(
                url_for(
                    "reports",
                    api_id="all",
                    time_period=time_period,
                    report_type=report_type
                )
            )

        api_label = api_row["name"]

    # -----------------------------------------------------
    # GENERATE THE SAME REPORT AS THE PAGE
    # -----------------------------------------------------

    report = generate_report(
        db=db,
        api_id=api_id,
        time_period=time_period
    )

    discord_sent = send_report_message_to_discord(
        report=report,
        report_type=report_type,
        api_label=api_label
    )

    if discord_sent:
        flash("Report sent to Discord successfully.", "success")
    else:
        flash("Could not send the report to Discord. Check the Discord webhook configuration.", "danger")

    return redirect(
        url_for(
            "reports",
            api_id=api_id,
            time_period=time_period,
            report_type=report_type
        )
    )

# =========================================================
# SETTINGS
# =========================================================

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    try:
        admin = Admin.query.filter_by(id=session["admin_id"]).first()
        if admin is None:
            flash("Administrator account not found.", "danger")
            return redirect(url_for("logout"))

        if request.method == "POST":
            action = request.form.get("action", "")

            # Change administrator username
            if action == "change_username":
                new_username = request.form.get("new_username", "").strip()
                current_password = request.form.get("current_password", "")

                if not new_username:
                    flash("Username cannot be empty.", "danger")
                    return redirect(url_for("settings"))

                if len(new_username) < 3:
                    flash("Username must be at least 3 characters.", "danger")
                    return redirect(url_for("settings"))

                if not check_password_hash(admin.password_hash, current_password):
                    flash("Current password is incorrect.", "danger")
                    return redirect(url_for("settings"))

                existing_admin = Admin.query.filter_by(username=new_username).first()
                if existing_admin and existing_admin.id != admin.id:
                    flash("That username is already in use.", "danger")
                    return redirect(url_for("settings"))

                admin.username = new_username
                db.session.commit()
                flash("Administrator username updated successfully.", "success")
                return redirect(url_for("settings"))

            # Change administrator password
            if action == "change_password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")

                if not check_password_hash(admin.password_hash, current_password):
                    flash("Current password is incorrect.", "danger")
                    return redirect(url_for("settings"))

                if len(new_password) < 8:
                    flash("New password must be at least 8 characters.", "danger")
                    return redirect(url_for("settings"))

                if new_password != confirm_password:
                    flash("New passwords do not match.", "danger")
                    return redirect(url_for("settings"))

                admin.password_hash = generate_password_hash(new_password)
                db.session.commit()
                session.clear()
                flash("Password changed successfully. Please log in again.", "success")
                return redirect(url_for("login"))

        return render_template("settings.html", admin=admin)

    except Exception as e:
        db.session.rollback()
        print(f"[SETTINGS ERROR] {e}")
        flash("Unable to update settings.", "danger")
        return redirect(url_for("dashboard"))

# =========================================================
# MONITORING SCHEDULER
# =========================================================

scheduler = BackgroundScheduler()


def run_monitoring():

    with app.app_context():

        check_all_apis(db)


scheduler.add_job(
    func=run_monitoring,
    trigger="interval",
    seconds=30,
    id="api_monitoring_job",
    replace_existing=True
)
# =========================================================
# APPLICATION START
# =========================================================

if __name__ == "__main__":

    with app.app_context():

        db.create_all()

    scheduler.start()

    print()
    print("==========================================")
    print(" API MONITORING SYSTEM")
    print("==========================================")
    print("Database : api_monitoring")
    print("Server   : http://127.0.0.1:5000")
    print("Monitoring scheduler : ACTIVE")
    print("Monitoring interval  : 30 seconds")
    print("==========================================")
    print()

    try:

        app.run(
            host="127.0.0.1",
            port=5000,
            debug=True,
            use_reloader=False
        )

    finally:

        scheduler.shutdown()
