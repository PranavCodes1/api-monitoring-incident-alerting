# API Monitoring, Incident Management & Alerting System

A Flask-based web application for monitoring APIs, tracking their health and performance, automatically managing incidents, and sending alerts through Discord.

The system provides a centralized dashboard for API management, monitoring, incidents, alerts, and reports.

## Features

- Admin authentication
- API registration and management
- Configurable HTTP method and expected status code
- Configurable monitoring interval and request timeout
- Automatic monitoring of active APIs
- Monitoring logs with status code, response time, success status, error message, and timestamp
- Automatic incident creation when an API health check fails
- Automatic incident resolution when an API recovers
- Incident duration tracking
- Discord notifications for API incidents and recoveries
- Alert history and delivery status
- Performance reports
- Uptime reports
- Incident reports
- API-specific or all-API reporting
- Multiple report time periods
- Performance response-time visualization
- Ability to send generated reports to Discord

## Technology Stack

### Backend

- Python
- Flask
- SQLAlchemy
- PostgreSQL
- APScheduler
- Requests
- python-dotenv

### Frontend

- HTML
- CSS
- Bootstrap
- Jinja2

### Notifications

- Discord Webhooks

### Version Control

- Git
- GitHub

## System Architecture

```text
                    +----------------------+
                    |   Registered APIs   |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |     APScheduler      |
                    | Monitoring Scheduler |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |   Monitoring Service |
                    |      Requests        |
                    +----------+-----------+
                               |
                    +----------+-----------+
                    |                      |
                    v                      v
                 API UP                 API DOWN
                    |                      |
                    v                      v
             Monitoring Log         Monitoring Log
                                           |
                                           v
                                  +----------------+
                                  |    Incident    |
                                  |    Service     |
                                  +-------+--------+
                                          |
                                          v
                                  +----------------+
                                  | Alert Service  |
                                  +-------+--------+
                                          |
                                          v
                                  +----------------+
                                  |    Discord     |
                                  |    Webhook     |
                                  +----------------+

                    API becomes healthy again
                               |
                               v
                       Incident Resolved
                               |
                               v
                       Recovery Alert
```

## Monitoring Workflow

1. APIs are registered through the API Management page.
2. Active APIs are periodically checked by the monitoring scheduler.
3. The monitoring service sends HTTP requests using the configured method.
4. The response status code and response time are recorded.
5. The result is stored in `monitoring_logs`.
6. If the result does not satisfy the expected status code, an incident is created.
7. An incident alert is sent through Discord.
8. When the API becomes healthy again, the active incident is resolved.
9. The incident duration is calculated.
10. A recovery notification is sent through Discord.
11. Monitoring continues automatically.

## Project Structure

```text
api_monitoring_incident_alerting/
│
├── README.md
├── app.py
├── models.py
├── monitoring_service.py
├── incident_service.py
├── alert_service.py
├── report_service.py
├── report_notification_service.py
├── create_admin.py
├── .gitignore
│
└── flask_jinja_templates/
    ├── templates/
    │   ├── base.html
    │   ├── login.html
    │   ├── dashboard.html
    │   ├── api_management.html
    │   ├── monitoring.html
    │   ├── incidents.html
    │   ├── alerts.html
    │   └── reports.html
    │
    └── static/
        └── css/
            └── style.css
```

## Database

The application uses PostgreSQL for persistent storage.

### Database Tables

#### `admins`

Stores administrator account information.

| Column | Description |
|---|---|
| `id` | Unique administrator ID |
| `username` | Administrator username |
| `password_hash` | Hashed administrator password |
| `created_at` | Account creation timestamp |

#### `apis`

Stores APIs configured for monitoring.

| Column | Description |
|---|---|
| `id` | Unique API ID |
| `name` | API name |
| `url` | API endpoint |
| `method` | HTTP method |
| `expected_status` | Expected HTTP status code |
| `interval_seconds` | Monitoring interval |
| `timeout_seconds` | Request timeout |
| `is_active` | Whether monitoring is enabled |
| `created_at` | API creation timestamp |

#### `monitoring_logs`

Stores the result of every API health check.

| Column | Description |
|---|---|
| `id` | Unique log ID |
| `api_id` | Monitored API |
| `status_code` | HTTP response status |
| `response_time_ms` | Response time in milliseconds |
| `success` | Whether the health check succeeded |
| `error_message` | Error details, if any |
| `checked_at` | Time of the health check |

#### `incidents`

Stores API failures and their resolution information.

| Column | Description |
|---|---|
| `id` | Unique incident ID |
| `incident_code` | Unique incident identifier |
| `api_id` | Affected API |
| `reason` | Failure reason |
| `started_at` | Incident start time |
| `resolved_at` | Incident resolution time |
| `duration_seconds` | Incident duration |
| `status` | Incident status |

#### `alerts`

Stores notifications generated for incidents and recoveries.

| Column | Description |
|---|---|
| `id` | Unique alert ID |
| `incident_id` | Related incident |
| `alert_type` | Incident or Recovery |
| `channel` | Notification channel |
| `message` | Alert message |
| `sent_at` | Notification timestamp |
| `status` | Delivery status |

## Reports

The Reports module provides monitoring data based on the selected API, time period, and report type.

### Report Types

- Performance
- Uptime
- Incident

### Time Periods

- Last 24 hours
- Last 7 days
- Last 30 days
- Last 3 months

### Performance Reports

Performance reports use collected monitoring data to display:

- Overall uptime
- Average response time
- Total monitoring checks
- Downtime
- Response-time trends

### Uptime Reports

Uptime reports summarize the availability of the selected API or all monitored APIs during the selected period.

### Incident Reports

Incident reports provide information such as:

- Total incidents
- Resolved incidents
- Open incidents
- Incident downtime
- Incident details

### Discord Report Notifications

Generated reports can be sent to Discord using the configured Discord webhook.

## Discord Alerts

The system uses Discord Webhooks for notifications.

### Incident Notification

When a monitored API fails, the system sends an incident notification.

Example:

```text
API Incident: JSONPlaceholder Test is DOWN.
Reason: Expected HTTP 200 but received HTTP 404
```

### Recovery Notification

When the API becomes healthy again, the system sends a recovery notification.

Example:

```text
API Recovery: JSONPlaceholder Test is UP again.
The previous incident has been resolved.
```

## Installation

### Prerequisites

Make sure the following are installed:

- Python 3
- PostgreSQL
- Git

### 1. Clone the Repository

Using SSH:

```bash
git clone git@github.com:PranavCodes1/api-monitoring-incident-alerting.git
cd api-monitoring-incident-alerting
```

### 2. Create a Virtual Environment

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

### 3. Install Dependencies

Install the required packages:

```bash
pip install flask flask-sqlalchemy psycopg2-binary requests apscheduler python-dotenv werkzeug
```

A `requirements.txt` file can be added later so dependencies can be installed with:

```bash
pip install -r requirements.txt
```

## PostgreSQL Configuration

Create a PostgreSQL database for the application.

Example:

```sql
CREATE DATABASE api_monitoring;
```

Configure the database connection in the environment file used by the application.

## Environment Variables

Create a `.env` file in the project root.

Example:

```env
DATABASE_URL=postgresql://username:password@localhost:5432/api_monitoring
DISCORD_WEBHOOK_URL=your_discord_webhook_url
SECRET_KEY=your_secret_key
```

Replace the example values with your local configuration.

**Do not commit the `.env` file to GitHub.**

The repository's `.gitignore` excludes `.env` and other local/generated files.

## Create an Admin Account

Run:

```bash
python create_admin.py
```

Follow the prompts to create the administrator account.

## Run the Application

Activate the virtual environment:

```bash
source venv/bin/activate
```

Start the Flask application:

```bash
python app.py
```

The application should then be available at:

```text
http://127.0.0.1:5000
```

## Dashboard Modules

### API Management

Used to configure APIs that should be monitored.

Configuration includes:

- API name
- URL
- HTTP method
- Expected status code
- Monitoring interval
- Timeout
- Active/inactive state

### Monitoring

Displays the current monitoring status and collected health-check information.

### Incidents

Displays detected API failures, their status, start time, resolution time, duration, and related alert information.

### Alerts

Displays notifications generated by the monitoring and incident system.

### Reports

Provides performance, uptime, and incident reports using selected API and time-period filters.


## Example Monitoring Scenario

Consider an API configured with:

```text
API Name: JSONPlaceholder Test
Method: GET
Expected Status: 200
```

If the API responds with HTTP `200`, the monitoring check is considered successful.

If the API instead responds with HTTP `404`, the system records the failed check and creates an incident:

```text
Expected HTTP 200 but received HTTP 404
```

The incident is then reported through Discord.

When the API starts returning HTTP `200` again, the incident is automatically resolved and a recovery notification is sent.


## Future Enhancements

Possible future improvements include:

- Docker containerization
- Kubernetes deployment
- CI/CD pipeline
- Prometheus integration
- Grafana dashboards
- Additional notification channels
- Advanced performance analytics
- Scheduled report delivery
- Improved monitoring visualizations
- Production deployment
- Automated testing
- Health-check retry policies

## Author

**Pranav Paralkar**

B.Sc. Computer Science

GitHub: [PranavCodes1](https://github.com/PranavCodes1)

Repository: [API Monitoring, Incident Management & Alerting System](https://github.com/PranavCodes1/api-monitoring-incident-alerting)

## Project Status

The project currently includes API management, automated monitoring, incident detection and resolution, Discord alerting, and report generation.

The system is being developed incrementally with additional DevOps and monitoring capabilities planned for future versions.

## License

This project is currently intended for educational and portfolio purposes.
