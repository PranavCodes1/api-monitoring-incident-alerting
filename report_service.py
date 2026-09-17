from sqlalchemy import text


# =========================================================
# REPORT PERIOD CONFIGURATION
# =========================================================

def get_period_config(time_period):
    """
    Return the PostgreSQL interval and display label
    for the selected report period.
    """

    periods = {
        "24h": {
            "interval": "24 hours",
            "label": "Last 24 Hours"
        },
        "7d": {
            "interval": "7 days",
            "label": "Last 7 Days"
        },
        "30d": {
            "interval": "30 days",
            "label": "Last 30 Days"
        },
        "3m": {
            "interval": "3 months",
            "label": "Last 3 Months"
        }
    }

    return periods.get(time_period, periods["30d"])


# =========================================================
# REPORT SUMMARY
# =========================================================

def get_report_summary(db, api_id="all", time_period="30d"):
    """
    Calculate overall report statistics.
    """

    period = get_period_config(time_period)

    # -----------------------------------------------------
    # MONITORING CONDITIONS
    # -----------------------------------------------------

    conditions = [
        "ml.checked_at >= CURRENT_TIMESTAMP - "
        "CAST(:period AS INTERVAL)"
    ]

    params = {
        "period": period["interval"]
    }

    if api_id != "all":
        conditions.append("ml.api_id = :api_id")
        params["api_id"] = int(api_id)

    where_clause = " AND ".join(conditions)

    # -----------------------------------------------------
    # MONITORING SUMMARY
    # -----------------------------------------------------

    result = db.session.execute(
        text(f"""
            SELECT
                COUNT(*) AS total_checks,

                COUNT(*) FILTER (
                    WHERE ml.success = TRUE
                ) AS successful_checks,

                COUNT(*) FILTER (
                    WHERE ml.success = FALSE
                ) AS failed_checks,

                AVG(
                    ml.response_time_ms
                ) FILTER (
                    WHERE ml.response_time_ms IS NOT NULL
                ) AS avg_response_time

            FROM monitoring_logs ml

            WHERE {where_clause}
        """),
        params
    ).mappings().first()

    total_checks = result["total_checks"] or 0
    successful_checks = result["successful_checks"] or 0
    failed_checks = result["failed_checks"] or 0

    avg_response_time = (
        float(result["avg_response_time"])
        if result["avg_response_time"] is not None
        else 0
    )

    # -----------------------------------------------------
    # OVERALL UPTIME
    # -----------------------------------------------------

    if total_checks > 0:
        overall_uptime = round(
            (successful_checks / total_checks) * 100,
            2
        )
    else:
        overall_uptime = 0

    # -----------------------------------------------------
    # INCIDENT CONDITIONS
    # -----------------------------------------------------

    incident_conditions = [
        "i.started_at >= CURRENT_TIMESTAMP - "
        "CAST(:incident_period AS INTERVAL)"
    ]

    incident_params = {
        "incident_period": period["interval"]
    }

    if api_id != "all":
        incident_conditions.append(
            "i.api_id = :incident_api_id"
        )

        incident_params["incident_api_id"] = int(api_id)

    incident_where_clause = " AND ".join(
        incident_conditions
    )

    # -----------------------------------------------------
    # TOTAL DOWNTIME
    # -----------------------------------------------------

    downtime_result = db.session.execute(
        text(f"""
            SELECT
                COALESCE(
                    SUM(
                        CASE

                            WHEN i.duration_seconds IS NOT NULL
                            THEN i.duration_seconds

                            WHEN i.status = 'OPEN'
                            THEN EXTRACT(
                                EPOCH FROM (
                                    CURRENT_TIMESTAMP -
                                    i.started_at
                                )
                            )

                            ELSE 0

                        END
                    ),
                    0
                ) AS total_downtime

            FROM incidents i

            WHERE {incident_where_clause}
        """),
        incident_params
    ).mappings().first()

    total_downtime_seconds = int(
        downtime_result["total_downtime"] or 0
    )

    return {
        "overall_uptime": overall_uptime,

        "avg_response_time": round(
            avg_response_time,
            2
        ),

        "total_checks": total_checks,

        "successful_checks": successful_checks,

        "failed_checks": failed_checks,

        "total_downtime_seconds": (
            total_downtime_seconds
        ),

        "total_downtime": format_duration(
            total_downtime_seconds
        )
    }


# =========================================================
# API PERFORMANCE REPORT
# =========================================================

def get_api_performance(
    db,
    api_id="all",
    time_period="30d"
):
    """
    Generate performance information for each API.
    """

    period = get_period_config(time_period)

    # -----------------------------------------------------
    # API FILTER
    # -----------------------------------------------------

    api_condition = ""
    params = {
        "period": period["interval"]
    }

    if api_id != "all":
        api_condition = "AND a.id = :api_id"
        params["api_id"] = int(api_id)

    # -----------------------------------------------------
    # API PERFORMANCE QUERY
    # -----------------------------------------------------

    rows = db.session.execute(
        text(f"""
            SELECT
                a.id,
                a.name,
                a.url,

                COUNT(ml.id) AS total_checks,

                COUNT(ml.id) FILTER (
                    WHERE ml.success = TRUE
                ) AS successful_checks,

                AVG(
                    ml.response_time_ms
                ) FILTER (
                    WHERE ml.response_time_ms IS NOT NULL
                ) AS avg_response,

                MIN(
                    ml.response_time_ms
                ) FILTER (
                    WHERE ml.response_time_ms IS NOT NULL
                ) AS fastest,

                MAX(
                    ml.response_time_ms
                ) FILTER (
                    WHERE ml.response_time_ms IS NOT NULL
                ) AS slowest

            FROM apis a

            LEFT JOIN monitoring_logs ml
                ON ml.api_id = a.id
                AND ml.checked_at >=
                    CURRENT_TIMESTAMP -
                    CAST(:period AS INTERVAL)

            WHERE 1 = 1
            {api_condition}

            GROUP BY
                a.id,
                a.name,
                a.url

            ORDER BY a.id
        """),
        params
    ).mappings().all()

    report_data = []

    # -----------------------------------------------------
    # PROCESS EACH API
    # -----------------------------------------------------

    for row in rows:

        total_checks = row["total_checks"] or 0

        successful_checks = (
            row["successful_checks"] or 0
        )

        # -------------------------------------------------
        # AVAILABILITY
        # -------------------------------------------------

        if total_checks > 0:

            availability = round(
                (
                    successful_checks /
                    total_checks
                ) * 100,
                2
            )

        else:
            availability = 0

        # -------------------------------------------------
        # AVERAGE RESPONSE
        # -------------------------------------------------

        avg_response = (
            float(row["avg_response"])
            if row["avg_response"] is not None
            else 0
        )

        # -------------------------------------------------
        # FASTEST RESPONSE
        # -------------------------------------------------

        fastest = (
            float(row["fastest"])
            if row["fastest"] is not None
            else 0
        )

        # -------------------------------------------------
        # SLOWEST RESPONSE
        # -------------------------------------------------

        slowest = (
            float(row["slowest"])
            if row["slowest"] is not None
            else 0
        )

        # -------------------------------------------------
        # INCIDENT COUNT
        # -------------------------------------------------

        incident_result = db.session.execute(
            text("""
                SELECT COUNT(*) AS incident_count

                FROM incidents i

                WHERE i.api_id = :api_id

                  AND i.started_at >=
                      CURRENT_TIMESTAMP -
                      CAST(:period AS INTERVAL)
            """),
            {
                "api_id": row["id"],
                "period": period["interval"]
            }
        ).mappings().first()

        incident_count = (
            incident_result["incident_count"] or 0
        )

        # -------------------------------------------------
        # DOWNTIME
        # -------------------------------------------------

        downtime_result = db.session.execute(
            text("""
                SELECT
                    COALESCE(
                        SUM(
                            CASE

                                WHEN i.duration_seconds
                                    IS NOT NULL
                                THEN i.duration_seconds

                                WHEN i.status = 'OPEN'
                                THEN EXTRACT(
                                    EPOCH FROM (
                                        CURRENT_TIMESTAMP -
                                        i.started_at
                                    )
                                )

                                ELSE 0

                            END
                        ),
                        0
                    ) AS downtime

                FROM incidents i

                WHERE i.api_id = :api_id

                  AND i.started_at >=
                      CURRENT_TIMESTAMP -
                      CAST(:period AS INTERVAL)
            """),
            {
                "api_id": row["id"],
                "period": period["interval"]
            }
        ).mappings().first()

        downtime_seconds = int(
            downtime_result["downtime"] or 0
        )

        # -------------------------------------------------
        # PERFORMANCE LABEL
        # -------------------------------------------------

        if (
            availability >= 99
            and avg_response < 500
        ):

            performance_label = "Excellent"

        elif (
            availability >= 97
            and avg_response < 1000
        ):

            performance_label = "Good"

        else:

            performance_label = "Poor"

        # -------------------------------------------------
        # API ICON
        # -------------------------------------------------

        icon_class = "bi-globe2"

        # -------------------------------------------------
        # ADD TO REPORT
        # -------------------------------------------------

        report_data.append({

            "id": row["id"],

            "name": row["name"],

            "url": row["url"],

            "icon_class": icon_class,

            "availability": availability,

            "avg_response": round(
                avg_response,
                2
            ),

            "fastest": round(
                fastest,
                2
            ),

            "slowest": round(
                slowest,
                2
            ),

            "incident_count": incident_count,

            "performance_label": (
                performance_label
            ),

            "downtime": format_duration(
                downtime_seconds
            )

        })

    return report_data

# =========================================================
# INCIDENT REPORT
# =========================================================

def get_incident_report(
    db,
    api_id="all",
    time_period="30d"
):
    """
    Generate incident information for the selected
    API and time period.
    """

    period = get_period_config(time_period)

    conditions = [
        "i.started_at >= CURRENT_TIMESTAMP - "
        "CAST(:period AS INTERVAL)"
    ]

    params = {
        "period": period["interval"]
    }

    if api_id != "all":
        conditions.append(
            "i.api_id = :api_id"
        )
        params["api_id"] = int(api_id)

    where_clause = " AND ".join(conditions)

    rows = db.session.execute(
        text(f"""
            SELECT
                i.id,
                i.incident_code,
                i.api_id,
                a.name AS api_name,
                i.reason,
                i.started_at,
                i.resolved_at,
                i.duration_seconds,
                i.status,
                COUNT(al.id) AS alert_count

            FROM incidents i

            JOIN apis a
                ON a.id = i.api_id

            LEFT JOIN alerts al
                ON al.incident_id = i.id
                AND al.status = 'Sent'

            WHERE {where_clause}

            GROUP BY
                i.id,
                i.incident_code,
                i.api_id,
                a.name,
                i.reason,
                i.started_at,
                i.resolved_at,
                i.duration_seconds,
                i.status

            ORDER BY i.started_at DESC
        """),
        params
    ).mappings().all()

    incident_data = []
    total_incidents = 0
    resolved_incidents = 0
    open_incidents = 0
    total_incident_downtime = 0

    for row in rows:

        duration_seconds = row["duration_seconds"]

        # -------------------------------------------------
        # OPEN INCIDENT
        # -------------------------------------------------

        if (
            duration_seconds is None
            and row["status"] == "OPEN"
        ):
            duration_seconds = int(
                db.session.execute(
                    text("""
                        SELECT EXTRACT(
                            EPOCH FROM (
                                CURRENT_TIMESTAMP -
                                :started_at
                            )
                        )
                    """),
                    {
                        "started_at": row["started_at"]
                    }
                ).scalar() or 0
            )

        duration_seconds = int(
            duration_seconds or 0
        )

        total_incidents += 1

        if row["status"] == "RESOLVED":
            resolved_incidents += 1
        else:
            open_incidents += 1

        total_incident_downtime += duration_seconds

        incident_data.append({

            "id": row["id"],

            "incident_code":
                row["incident_code"],

            "api_id":
                row["api_id"],

            "api_name":
                row["api_name"],

            "reason":
                row["reason"],

            "started_at":
                row["started_at"].strftime(
                    "%d %b %Y, %H:%M:%S"
                )
                if row["started_at"]
                else "—",

            "resolved_at":
                row["resolved_at"].strftime(
                    "%d %b %Y, %H:%M:%S"
                )
                if row["resolved_at"]
                else "Not Resolved",

            "duration":
                format_duration(
                    duration_seconds
                ),

            "status":
                row["status"],

            "alert_count":
                row["alert_count"] or 0

        })

    return {
        "incidents": incident_data,
        "total_incidents": total_incidents,
        "resolved_incidents": resolved_incidents,
        "open_incidents": open_incidents,
        "total_downtime_seconds": total_incident_downtime,
        "total_downtime": format_duration(
            total_incident_downtime
        )
    }

# =========================================================
# PERFORMANCE CHART DATA
# =========================================================

def get_performance_chart_data(db, api_id="all", time_period="30d"):
    """
    Return time-bucketed average response times for the performance chart.
    The chart is rendered as SVG, so no JavaScript chart library is required.
    """

    period = get_period_config(time_period)

    conditions = [
        "ml.checked_at >= CURRENT_TIMESTAMP - "
        "CAST(:period AS INTERVAL)"
    ]

    params = {
        "period": period["interval"]
    }

    if api_id != "all":
        conditions.append("ml.api_id = :api_id")
        params["api_id"] = int(api_id)

    where_clause = " AND ".join(conditions)

    # Hourly points for 24h; daily points for longer periods.
    bucket = "hour" if time_period == "24h" else "day"

    rows = db.session.execute(
        text(f"""
            SELECT
                DATE_TRUNC('{bucket}', ml.checked_at) AS bucket,
                AVG(ml.response_time_ms) FILTER (
                    WHERE ml.response_time_ms IS NOT NULL
                ) AS avg_response
            FROM monitoring_logs ml
            WHERE {where_clause}
            GROUP BY bucket
            ORDER BY bucket
        """),
        params
    ).mappings().all()

    values = [
        float(row["avg_response"])
        for row in rows
        if row["avg_response"] is not None
    ]

    if not values:
        return {
            "has_data": False,
            "points": "",
            "labels": [],
            "max_response": 0,
            "min_response": 0
        }

    chart_left = 60
    chart_right = 940
    chart_top = 35
    chart_bottom = 245
    chart_width = chart_right - chart_left
    chart_height = chart_bottom - chart_top

    min_response = min(values)
    max_response = max(values)

    if max_response == min_response:
        max_response = max_response + 1

    points = []
    labels = []

    total = len(rows)

    for index, row in enumerate(rows):
        if row["avg_response"] is None:
            continue

        value = float(row["avg_response"])

        if total == 1:
            x = (chart_left + chart_right) / 2
        else:
            x = chart_left + (index / (total - 1)) * chart_width

        y = chart_bottom - (
            (value - min_response) /
            (max_response - min_response)
        ) * chart_height

        points.append({
            "x": round(x, 2),
            "y": round(y, 2),
            "value": round(value, 2)
        })

        bucket_time = row["bucket"]
        if time_period == "24h":
            label = bucket_time.strftime("%d %b %H:%M")
        else:
            label = bucket_time.strftime("%d %b")

        # Show only a few readable x-axis labels.
        if index in {0, total // 2, total - 1}:
            labels.append({
                "x": round(x, 2),
                "text": label
            })

    point_string = " ".join(
        f"{point['x']},{point['y']}"
        for point in points
    )

    return {
        "has_data": bool(points),
        "points": point_string,
        "point_data": points,
        "labels": labels,
        "max_response": round(max(values), 2),
        "min_response": round(min(values), 2)
    }


# =========================================================
# COMPLETE REPORT
# =========================================================

def generate_report(
    db,
    api_id="all",
    time_period="30d"
):
    """
    Generate the complete report required by reports.html.
    """

    period = get_period_config(
        time_period
    )

    summary = get_report_summary(
        db=db,
        api_id=api_id,
        time_period=time_period
    )

    report_data = get_api_performance(
        db=db,
        api_id=api_id,
        time_period=time_period
    )

    incident_report = get_incident_report(
        db=db,
        api_id=api_id,
        time_period=time_period
    )    
    return {

        "overall_uptime":
            summary["overall_uptime"],

        "avg_response_time":
            summary["avg_response_time"],

        "total_checks":
            summary["total_checks"],

        "total_downtime":
            summary["total_downtime"],

        "total_downtime_seconds":
            summary["total_downtime_seconds"],

        "report_data":
            report_data,

        "chart_data":
            get_performance_chart_data(
                db=db,
                api_id=api_id,
                time_period=time_period
            ),

        "incident_data":
            incident_report["incidents"],

        "total_incidents":
            incident_report["total_incidents"],

        "resolved_incidents":
            incident_report["resolved_incidents"],

        "open_incidents":
            incident_report["open_incidents"],

        "incident_downtime":
            incident_report["total_downtime"],

        "incident_downtime_seconds":
            incident_report["total_downtime_seconds"],

        "report_period_label":
            period["label"]

    }


# =========================================================
# FORMAT DURATION
# =========================================================

def format_duration(seconds):
    """
    Convert seconds into a readable duration.
    """

    seconds = int(seconds or 0)

    days = seconds // 86400
    seconds %= 86400

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60
    seconds %= 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"

    if hours > 0:
        return f"{hours}h {minutes}m"

    if minutes > 0:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"
