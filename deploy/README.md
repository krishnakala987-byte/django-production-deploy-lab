# Deployment configuration

These are the exact production configs used on the AWS EC2 (Ubuntu 22.04) instance.

| File | Purpose |
| --- | --- |
| `gunicorn.service` | Gunicorn master + 3 Uvicorn ASGI workers on a unix socket, self-healing (`Restart=always`) |
| `celery.service` | Celery worker (concurrency 2, max 1000 tasks per child) |
| `celery-beat.service` | Celery beat scheduler (single instance) |
| `nginx/myapp.conf` | Reverse proxy + static file serving |

## Install

```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo cp deploy/nginx/myapp.conf /etc/nginx/sites-available/myapp
sudo ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn celery celery-beat
sudo systemctl reload nginx
```

All services read secrets from `/srv/myapp/.env` (chmod 600) via `EnvironmentFile` —
see `.env.example` in the repo root.
