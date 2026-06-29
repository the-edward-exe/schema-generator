# Deploying the Schema Generator to DigitalOcean

The web UI (`webapp/app.py`) is a small Flask app over `schemagen`. It serves a
form at `/`, generates the schema set, and returns a ZIP. Health check: `/healthz`.

## Run locally first

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:8080 webapp.app:app      # or: python webapp/app.py
# open http://localhost:8080
```

## Option A — App Platform from GitHub (recommended)

1. Push this repo to GitHub (see "Git setup" below).
2. DigitalOcean → **Apps** → **Create App** → **GitHub** → pick the repo + branch.
3. App Platform auto-detects Python (via `requirements.txt`) and the **`Procfile`**
   (`web: gunicorn ... webapp.app:app`). Confirm:
   - Run command: `gunicorn --workers 2 --bind 0.0.0.0:${PORT:-8080} webapp.app:app`
   - HTTP port: `8080`
   - Health check path: `/healthz`
   - Instance: Basic (smallest is fine).
4. **Create Resources** → wait for build → you get a public `*.ondigitalocean.app` URL.
5. Pushes to the branch auto-redeploy (`deploy_on_push`).

Or do it from the CLI with the included spec:

```bash
doctl apps create --spec .do/app.yaml   # edit github.repo first
```

## Option B — Droplet (full VM)

```bash
# on an Ubuntu droplet
sudo apt update && sudo apt install -y python3-pip python3-venv nginx
git clone <your-repo> /opt/schemagen && cd /opt/schemagen
python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt
gunicorn --workers 2 --bind 127.0.0.1:8080 webapp.app:app   # run under systemd
# nginx: proxy_pass http://127.0.0.1:8080;  then certbot for HTTPS
```

Create a systemd unit so it restarts on boot/crash, and put nginx + certbot in
front for TLS. App Platform (Option A) does all of this for you.

## Git setup (if not already a repo)

```bash
git init && git add . && git commit -m "schema generator + web UI"
git branch -M main
git remote add origin git@github.com:YOUR_USER/schema-generator.git
git push -u origin main
```

`.gitignore` already excludes `Customer outputs/`, `build_*.py`, and caches, so
client output and per-client drivers are not deployed.

## Authentication (HTTP basic)

The app supports optional basic auth via env vars. Set **both** to require login:

```bash
AUTH_USER=admin
AUTH_PASS=<a-strong-password>
```

- On **App Platform**: App → Settings → your service → **Environment Variables** →
  add `AUTH_USER` and `AUTH_PASS` (mark `AUTH_PASS` as **Encrypted**). Redeploy.
  (The `.do/app.yaml` already lists them — change `CHANGE_ME`.)
- Locally: `AUTH_USER=admin AUTH_PASS=secret python webapp/app.py`
- If either var is unset, the app runs **open** (fine for local dev).
- `/healthz` stays open regardless, so platform health checks keep passing.

The browser shows a native login prompt; comparison is constant-time
(`hmac.compare_digest`).

## Notes

- For stronger protection you can still layer App Platform trusted sources / a VPN
  on top of basic auth.
- The app writes only to a temp dir per request and streams the ZIP back —
  nothing is persisted server-side.
- Generated files still follow the convention `Customer outputs/<Business Name>/`
  inside the ZIP.
