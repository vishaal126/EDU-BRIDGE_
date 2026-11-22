# EduBridge AI

A peer-learning web app. Students find tutors, request sessions and post doubts; tutors accept requests and answer doubts.

**One server does everything:** the Flask backend (`app.py`) exposes a JSON API under `/api` and also serves the frontend
(`static/`). The frontend calls the API with `fetch`, so there is nothing to wire up and no CORS to configure.

```
app.py            Flask backend: auth, tutors, bookings, doubts (SQLite)
static/           index.html, style.css, app.js  (the frontend)
tests/test_api.py end-to-end tests of the API and of the served frontend
```

> **Important:** this is a Python app. Do **not** open `static/index.html` by double-clicking it and do **not** use GitHub Pages;
> there is no backend there. Run the server (below) or deploy it on Render, then use the URL it prints/gives you.

## Run locally
**Windows:** double-click `run_windows.bat`. **Mac/Linux:** `bash run_mac_linux.sh`. Both install what's needed, start the server and open the browser.

Or manually:
```bash
pip install -r requirements.txt
python app.py            # http://localhost:8000
python -m unittest discover -s tests -v
```

## Get a public URL (Render, free)
1. Push this folder to a GitHub repository (files at the repo root).
2. On <https://render.com> choose **New + > Blueprint** (or **Web Service**), pick the repo. `render.yaml` sets everything up.
3. Wait for the build; Render gives you `https://edubridge-ai.onrender.com` (or similar).

Any host that runs `gunicorn app:app` works (Railway, Fly.io, PythonAnywhere...). GitHub Pages can't run a Python backend.

## API
| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/register`, `/api/login` | anyone | returns `{token, user}` |
| POST | `/api/logout`, GET/PUT `/api/me` | signed in | session and profile |
| GET | `/api/tutors?q=` | signed in | search tutors |
| POST/GET | `/api/bookings` | student / both | request a session; list mine |
| POST | `/api/bookings/<id>/status` | tutor or student | Accept/Decline/Complete, Cancel |
| GET/POST | `/api/doubts`, `/api/doubts/<id>/replies` | signed in (posting doubts: students) | doubts board |

Send `Authorization: Bearer <token>`. Errors are `{"error": "..."}` with a proper status code.

## Security notes
Passwords use salted PBKDF2; session tokens are random and only their SHA-256 hash is stored; the frontend never inserts
user text as HTML; every endpoint re-checks role and ownership on the server.

## Known limits
* **SQLite on free hosting is ephemeral**: data can reset on redeploy/restart. Set `DB_PATH` to a persistent disk, or move to Postgres.
* No email verification or password reset yet, no payments, no real-time chat.
