# Aptitude Contest Platform

Django app for weekly multi-round aptitude quizzes (quantitative, logical, verbal), leaderboards, CSV/XLSX question import, and Jazzmin-themed admin.

---

## Requirements

- **Python** 3.10+ (3.12+ recommended)
- Dependencies: see [`requirements.txt`](requirements.txt)

---

## Local development

### 1. Clone and virtual environment

```bash
cd aptitude_contest
py -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Database and static files

```bash
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

Open **http://127.0.0.1:8000/** — public site. **http://127.0.0.1:8000/admin/** — admin.

### 3. First-time admin setup

1. **Weeks (schedule)** — create a week, set dates, mark **one** week as active.
2. Under that week, add **Rounds** (order, timer, question cap, optional promotion cutoff).
3. Activate **one round** per week for play.
4. **Questions** — add manually or use **Import CSV / Excel** (pick target round, upload file).

---

## Configuration reference (`aptitude_contest/settings.py`)

| Setting | Purpose |
|--------|---------|
| `SECRET_KEY` | **Must be unique and secret in production** — never commit a real key to public repos. |
| `DEBUG` | `True` only for local dev. Set **`False`** when hosting publicly. |
| `ALLOWED_HOSTS` | **Hostnames only** (no `https://`). Example: `["yourdomain.com", "www.yourdomain.com"]`. |
| `CSRF_TRUSTED_ORIGINS` | **Full origins with scheme** for HTTPS. Example: `["https://yourdomain.com"]`. |
| `DATABASES` | Default **SQLite** (`db.sqlite3`). Use **PostgreSQL** (or MySQL) in production. |
| `STATIC_ROOT` / `STATIC_URL` | Run `collectstatic` in production; serve via web server or WhiteNoise. |
| `MEDIA_ROOT` / `MEDIA_URL` | User uploads; serve in production (Nginx or Django only behind auth — see below). |
| `TIME_ZONE` | Default `Asia/Kolkata` — change if needed. |

### Environment variables (recommended for hosting)

You can extend `settings.py` to read from the environment (example pattern):

```python
import os
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", SECRET_KEY)
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
```

Then set on the server:

- `DJANGO_SECRET_KEY` — long random string  
- `DJANGO_DEBUG=False`  
- `DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com`  
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com` (already partially supported for CSRF in this project)

---

## HTTPS, ngrok, and CSRF

- **`ALLOWED_HOSTS`**: `example.ngrok-free.dev` (no scheme).  
- **`CSRF_TRUSTED_ORIGINS`**: `https://example.ngrok-free.dev` (with `https://`).  
- For a **new** ngrok URL, add both; or use `.ngrok-free.dev` in `ALLOWED_HOSTS` and set `DJANGO_CSRF_TRUSTED_ORIGINS` for the full `https://…` origin.

---

## Production hosting overview

### 1. Security checklist

- [ ] New **`SECRET_KEY`** (50+ random characters).  
- [ ] **`DEBUG = False`**.  
- [ ] **`ALLOWED_HOSTS`** = your real domain(s).  
- [ ] **`CSRF_TRUSTED_ORIGINS`** = `https://your-domain` entries.  
- [ ] Use **PostgreSQL** (or managed DB) instead of SQLite for concurrent users.  
- [ ] **HTTPS** only (TLS certificate — Let’s Encrypt, Cloudflare, host panel, etc.).

### 2. Install production dependencies

Uncomment in `requirements.txt` or install:

```bash
pip install gunicorn whitenoise
```

**WhiteNoise** serves `staticfiles` from the same process (simple deployments). Configure `MIDDLEWARE` with `SecurityMiddleware` immediately followed by `WhiteNoiseMiddleware`, and run `collectstatic`.

### 3. Collect static files

```bash
py manage.py collectstatic --noinput
```

This fills `STATIC_ROOT` (e.g. `staticfiles/`). Do **not** commit `staticfiles/` to git (see `.gitignore`).

### 4. Run with Gunicorn (Linux example)

From the directory that contains `manage.py`:

```bash
gunicorn aptitude_contest.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Use a process manager (**systemd**, **supervisor**) to restart on boot. Put **Nginx** (or Caddy) in front for TLS and optional media/static:

- Proxy `location /` to `http://127.0.0.1:8000`  
- Serve `/static/` from `STATIC_ROOT`  
- Optionally serve `/media/` from `MEDIA_ROOT` or restrict media via Django

### 5. Example Nginx snippets

**Reverse proxy to Gunicorn:**

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

**Static files:**

```nginx
location /static/ {
    alias /path/to/aptitude_contest/staticfiles/;
}
```

Set **`SECURE_PROXY_SSL_HEADER`** in Django if TLS terminates at Nginx (so `request.is_secure()` is correct):

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

### 6. PostgreSQL (example)

Install `psycopg[binary]` or `psycopg2-binary`, then in `settings.py`:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "aptitude"),
        "USER": os.environ.get("POSTGRES_USER", "aptitude"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}
```

Run `migrate` on the server after switching databases.

---

## PaaS (Railway, Render, Fly.io, etc.)

1. Set **build** command: `pip install -r requirements.txt`  
2. Set **release** command: `python manage.py migrate`  
3. Set **start** command: `gunicorn aptitude_contest.wsgi:application --bind 0.0.0.0:$PORT`  
4. Add env vars: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, database URL if provided.  
5. Use **WhiteNoise** or the platform’s static file handling.  
6. Attach a **persistent disk** or **object storage** if you rely on `MEDIA_ROOT` for uploads.

---

## Useful commands

| Command | Description |
|--------|-------------|
| `py manage.py migrate` | Apply database migrations |
| `py manage.py createsuperuser` | Admin login |
| `py manage.py collectstatic` | Gather static files for production |
| `py manage.py runserver` | Dev server only |

---

## Project layout (short)

| Path | Role |
|------|------|
| `contest/` | App: models, views, URLs, admin, imports |
| `templates/` | HTML (Tailwind CDN) |
| `aptitude_contest/settings.py` | Django settings |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Ignores `db.sqlite3`, `staticfiles/`, `.venv`, etc. |

---

## Support

For Django deployment docs, see: [https://docs.djangoproject.com/en/stable/howto/deployment/](https://docs.djangoproject.com/en/stable/howto/deployment/)
