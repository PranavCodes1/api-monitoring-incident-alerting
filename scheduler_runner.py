import signal
import time

from app import app, scheduler
from models import db
from monitoring_service import check_all_apis

def run_monitoring():
    with app.app_context():
        check_all_apis(db)

with app.app_context():
    db.create_all()

# Dedicated single scheduler process; do not start it in Gunicorn workers.
scheduler.start()
print("APScheduler active; monitoring interval is configured in app.py.")

def shutdown(signum, frame):
    if scheduler.running:
        scheduler.shutdown(wait=False)
    raise SystemExit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

while True:
    time.sleep(60)
