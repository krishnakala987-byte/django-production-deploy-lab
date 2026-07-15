# Django Production Deployment Lab

This repository contains my hands-on production deployment practice for a Django application on AWS EC2.

The objective of this lab was to understand how a Django application is deployed, managed, monitored, and troubleshot in a Linux production environment rather than only running it locally.

Over five days, I deployed a Django application using MySQL, Gunicorn with Uvicorn ASGI workers, NGINX, Redis, Celery, and Celery Beat while practicing real-world production scenarios: service failures, socket permission issues, Redis outages, disk exhaustion, database indexing at 200,000 rows, backup and restore testing, and production debugging.

---

# Tech Stack

- Python / Django
- MySQL
- Redis
- Celery + Celery Beat
- Gunicorn (WSGI master) + Uvicorn (ASGI workers)
- NGINX
- systemd
- Ubuntu Linux (AWS EC2)
- UFW
- Git + GitHub Actions

---

# Architecture

```
      Internet
          │
          ▼
       NGINX  ── serves /static/ directly
          │
    Reverse Proxy
          │
          ▼
      Gunicorn (3 × Uvicorn ASGI workers)
          │
     UNIX Socket (/run/gunicorn.sock)
          │
          ▼
  Django Application
   ├──────────────┐
   │              │
   ▼              ▼
MySQL          Redis (AOF enabled)
                   │
       ┌───────────┴───────────┐
       ▼                       ▼
Celery Worker          Celery Beat
```

All processes run as hardened systemd services (`Restart=always`, dedicated non-root `deploy` user, secrets loaded from a chmod-600 `.env` via `EnvironmentFile`). The real unit files and NGINX config are in [`deploy/`](deploy/).

---

# Configuration & Secrets

No secrets live in this repository. `config/settings.py` reads everything from environment variables:

```bash
cp .env.example .env   # then fill in real values (chmod 600)
```

Production keeps `.env` at `/srv/myapp/.env`, loaded by every systemd unit. `DEBUG=False`, explicit `ALLOWED_HOSTS`, MySQL with `utf8mb4` and `CONN_MAX_AGE=60`.

---

# What I Implemented

## Day 1 — Production deployment

- Ubuntu server prep, non-root `deploy` user, UFW (OpenSSH + NGINX only)
- Django project + virtualenv
- Gunicorn bound to a unix socket, then switched to **Uvicorn ASGI workers** (`-k uvicorn.workers.UvicornWorker -w 3`)
- Hand-written systemd unit with `Restart=always` — verified self-healing by `kill -9` on the master PID and watching systemd revive it
- NGINX reverse proxy + static file serving (`collectstatic`, alias to `STATIC_ROOT`)
- Production settings: `DEBUG=False`, `ALLOWED_HOSTS` (verified a forged `Host:` header returns 400)
- Debugged real 502s end to end using `nginx error.log` + `journalctl`

## Day 2 — MySQL, indexing at 200K rows, backup & restore

- MySQL database with `utf8mb4`, dedicated least-privilege app user (scoped to one database)
- Bookings app (Trip / Booking models) + Django admin
- Seeded **200,000 rows** with `bulk_create` in batches of 10,000
- Found the slow query with `EXPLAIN`, fixed it with a composite index (details below)
- Enabled the slow query log (`long_query_time=0.5`)
- Automated `mysqldump` backups (gzip, timestamped, 7-day retention, cron at 02:00) — and **tested the restore** into a scratch database, verifying `COUNT(*) = 200000`

## Day 3 — Background processing (Celery + Redis)

- Redis bound to localhost; Celery worker + Beat as systemd services
- Email task with `autoretry_for`, `retry_backoff`, `max_retries=5`; nightly CSV revenue report on a Beat cron schedule
- Load-tested the queue: stopped workers, queued 100 tasks, watched `redis-cli LLEN celery` fill and then drain to 0
- Enabled Redis **AOF persistence** and proved a queued backlog survives a full Redis restart
- Proved a Redis outage only degrades the site (background jobs fail, pages still 200)

## Day 4 — Break everything on purpose

| Failure | Symptom | Diagnosis |
| --- | --- | --- |
| Dead app | 502 | `error.log`: `(111: Connection refused)` |
| Wrong socket path | 502 | `error.log`: `No such file or directory` |
| Socket permissions | 502 | `error.log`: `(13: Permission denied)` |
| Redis outage | jobs fail, site up | `.delay()` raises ConnectionError |
| Disk filled to ~95% | pressure | `df`/`du`, rescued with `journalctl --vacuum-size=200M` |
| Empty ALLOWED_HOSTS | 400 Bad Request | settings misconfiguration |
| Missing staticfiles | unstyled admin | collectstatic / alias path / permissions |
| Runaway query | DB pegged | `SHOW FULL PROCESSLIST` → `KILL <id>` |

## Day 5 — Publish & document

- `.gitignore` for venv, `.env`, staticfiles, dumps; this README; screenshots of every running service

---

# Database Optimization — EXPLAIN before/after (200,000 rows)

The bookings table was deliberately built **without** an index on `(status, created_at)`, then queried:

```sql
SELECT * FROM bookings_booking
WHERE status='confirmed' ORDER BY created_at DESC LIMIT 20;
```

**Before** (no index):

```
type = ALL          -- full table scan
key  = NULL         -- no index used
rows ≈ 200000
Extra = Using filesort
```

**Fix** — composite index added the Django way ([`bookings/models.py`](bookings/models.py)):

```python
class Meta:
    indexes = [models.Index(fields=["status", "-created_at"])]
```

**After:**

```
type = ref          -- index lookup
key  = bookings_bo_status_eb4fb1_idx
Extra = filesort eliminated; LIMIT 20 served in index order
```

The migration is in [`bookings/migrations/0002_...`](bookings/migrations/).

---

# Production Request Flow

```
Browser → NGINX → unix socket → Gunicorn/Uvicorn → Django → MySQL
```

Background tasks

```
Django → Redis → Celery Worker → Task Execution
```

Scheduled tasks

```
Celery Beat → Redis Queue → Celery Worker → Task Execution
```

---

# Repository Structure

```
.
├── bookings/            # Trip/Booking models, Celery tasks, composite-index migration
├── config/              # settings (env-driven), celery app, urls, asgi/wsgi
├── employees/           # simple CRUD app
├── deploy/              # real systemd units + NGINX config used in production
├── templates/
├── screenshots/         # every service running (Gunicorn, NGINX, MySQL, Redis, Celery, Beat, CI)
├── .github/workflows/   # CI: django check + migration sync, fails on error
├── db_backup.sh         # credential-free backup script (reads ~/.my.cnf)
├── requirements.txt
├── .env.example
└── manage.py
```

---

# GitHub Actions

On every push/PR to `main` the workflow installs system MySQL client libs and all requirements, then **fails the build** on:

```
python manage.py check
python manage.py makemigrations --check --dry-run
```

---

# Commands Practiced

### Linux

```
systemctl status|start|stop|restart, journalctl, ps, top, free -h, df -h, du -sh
```

### NGINX

```
sudo nginx -t, sudo systemctl reload nginx
```

### Gunicorn / Celery

```
sudo systemctl status gunicorn, journalctl -u gunicorn, systemctl reload gunicorn (HUP, zero-downtime)
```

### Redis

```
redis-cli ping, redis-cli info persistence, redis-cli LLEN celery
```

### MySQL

```
EXPLAIN, SHOW FULL PROCESSLIST;, KILL <id>;, mysqldump, gunzip | mysql (tested restore)
```

---

# Lessons Learned

- How NGINX communicates with Gunicorn over unix sockets — and how socket path or permission mistakes produce three *different* 502s in `error.log`
- Never commit secrets: settings are fully environment-driven, services load them via `EnvironmentFile`
- An index is proven with `EXPLAIN` before/after, not assumed
- A backup that has never been restored is a hope, not a backup — I test mine
- Redis down should make the site weaker, never dead (AOF + retries + degraded mode)
- systemd is one pattern reused for everything: web server, worker, scheduler

---

# Future Improvements

- HTTPS with Let's Encrypt
- Docker / Docker Compose packaging
- Prometheus + Grafana monitoring
- Terraform-provisioned infrastructure
- Kubernetes deployment
- CI/CD deployment to AWS

---

# Author

**Krishna Kala** — DevOps & Backend Engineer

GitHub: <https://github.com/krishnakala987-byte>
