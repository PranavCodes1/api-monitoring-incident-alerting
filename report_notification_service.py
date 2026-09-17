from datetime import datetime

from alert_service import send_discord_message


# =========================================================
# BUILD REPORT MESSAGE
# =========================================================

def build_report_message(report, report_type, api_label):
    """Build a concise Discord message for a generated report."""

    period_label = report["report_period_label"]

    lines = [
        "📊 API MONITORING REPORT",
        "",
        f"Report Type: {report_type.title()}",
        f"API: {api_label}",
        f"Period: {period_label}",
        ""
    ]

    if report_type == "performance":
        lines.extend([
            "Performance Summary",
            f"• Overall Uptime: {report['overall_uptime']}%",
            f"• Average Response: {report['avg_response_time']} ms",
            f"• Total Checks: {report['total_checks']}",
            f"• Total Downtime: {report['total_downtime']}",
            "",
            "API Performance:"
        ])

        for api in report["report_data"]:
            lines.append(
                f"• {api['name']}: {api['availability']}% uptime | "
                f"{api['avg_response']} ms avg | "
                f"{api['incident_count']} incidents"
            )

    elif report_type == "uptime":
        lines.extend([
            "Uptime Summary",
            f"• Overall Uptime: {report['overall_uptime']}%",
            f"• Total Checks: {report['total_checks']}",
            f"• Total Downtime: {report['total_downtime']}",
            "",
            "API Uptime:"
        ])

        for api in report["report_data"]:
            lines.append(
                f"• {api['name']}: {api['availability']}% uptime | "
                f"{api['downtime']} downtime"
            )

    elif report_type == "incident":
        lines.extend([
            "Incident Summary",
            f"• Total Incidents: {report['total_incidents']}",
            f"• Resolved: {report['resolved_incidents']}",
            f"• Open: {report['open_incidents']}",
            f"• Incident Downtime: {report['incident_downtime']}",
            ""
        ])

        if report["incident_data"]:
            lines.append("Recent Incidents:")
            for incident in report["incident_data"][:5]:
                lines.append(
                    f"• {incident['incident_code']} | "
                    f"{incident['api_name']} | "
                    f"{incident['status']} | "
                    f"{incident['duration']}"
                )
        else:
            lines.append("No incidents were recorded during this period.")

    lines.extend([
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])

    message = "\n".join(lines)

    # Discord messages have a 2,000-character limit.
    if len(message) > 1900:
        message = message[:1890] + "\n…"

    return message


# =========================================================
# SEND REPORT TO DISCORD
# =========================================================

def send_report_to_discord(report, report_type, api_label):
    """Send a generated report to Discord."""

    message = build_report_message(
        report=report,
        report_type=report_type,
        api_label=api_label
    )

    return send_discord_message(message)
