# Docker setup — API Monitoring System

## What's included
- `web`: Flask app served by Gunicorn
- `db`: PostgreSQL with a persistent named volume
- `scheduler`: dedicated APScheduler process (one instance only)
- `init`: creates SQLAlchemy tables before web/scheduler start

## A. Prerequisites
Install and start Docker Desktop: https://www.docker.com/products/docker-desktop/

## B. First run (your Mac)
1. Extract the project ZIP.
2. Open Terminal and `cd` into the `claude_api_test` folder (the folder containing `compose.yaml`).
3. Create your local environment file:
   ```bash
   cp .env.example .env
   ```
4. Edit `.env`. Set a long random `SECRET_KEY` and a strong alphanumeric `POSTGRES_PASSWORD`. Keep `.env` private.
5. Start the stack:
   ```bash
   docker compose up -d --build
   ```
6. Check status:
   ```bash
   docker compose ps
   docker compose logs -f web
   docker compose logs -f scheduler
   ```
7. Visit http://localhost:5000

## C. Create the initial admin
The existing `create_admin.py` uses a predefined `admin` / `admin123` account. Run it once in the container:
```bash
docker compose exec web python create_admin.py
```
Then log in and immediately change the password in Settings. Do not use the default credentials outside a local demo.

## D. Stop / restart
```bash
docker compose down       # stops/removes containers; preserves database volume
docker compose up -d      # starts again
```
Do NOT run `docker compose down -v` unless you intentionally want to erase the local database.

## E. Move to partner's laptop
1. Send the Dockerized project ZIP, excluding `.env` and database backups.
2. On their laptop, install/start Docker Desktop and extract the ZIP.
3. In the project folder, run `cp .env.example .env`; set unique `SECRET_KEY` and `POSTGRES_PASSWORD`.
4. Run `docker compose up -d --build`.
5. Run `docker compose exec web python create_admin.py`, then change the default password after login.
6. Open http://localhost:5000.

Each laptop has its own PostgreSQL volume. It starts with a fresh database unless you separately migrate a backup.

## F. Backup and restore
Export a running database:
```bash
docker compose exec -T db pg_dump -U api_admin -d api_monitoring > api_monitoring_backup.sql
```
Restore into an empty target database after the target stack is initialized:
```bash
docker compose exec -T db psql -U api_admin -d api_monitoring < api_monitoring_backup.sql
```
Use the actual `POSTGRES_USER` and `POSTGRES_DB` values from `.env`. Backups can contain sensitive data; transfer securely and do not commit them.

## G. Troubleshooting
```bash
docker compose ps
docker compose logs --tail=100 web
docker compose logs --tail=100 scheduler
docker compose logs --tail=100 db
docker compose config
```
If port 5000 is already occupied, change the host side of `ports` to `"5001:5000"` and browse http://localhost:5001.

## Important implementation note
The project schedules monitoring in `app.py`, but its original `if __name__ == "__main__"` block starts the scheduler only when running the development server. In this Docker setup, Gunicorn serves the web app and `scheduler_runner.py` starts one dedicated scheduler container to avoid duplicate monitoring jobs across Gunicorn workers.
