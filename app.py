"""EduBridge AI - backend (Flask + SQLite). Serves the JSON API under /api and the frontend from /static."""
import hashlib, hmac, os, re, secrets, sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, g, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN('student','tutor')), skills TEXT DEFAULT '',
  bio TEXT DEFAULT '', city TEXT DEFAULT '', rate INTEGER DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, tutor_id INTEGER NOT NULL,
  topic TEXT NOT NULL, note TEXT DEFAULT '', slot TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS doubts(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL, subject TEXT NOT NULL,
  question TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS replies(id INTEGER PRIMARY KEY, doubt_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  body TEXT NOT NULL, created TEXT NOT NULL);
"""

def now(): return datetime.now(timezone.utc)
def iso(d=None): return (d or now()).isoformat(timespec="seconds")
def h(t): return hashlib.sha256(t.encode()).hexdigest()

def hash_pw(pw):
    salt = secrets.token_hex(16)
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 200_000).hex()}"

def check_pw(pw, stored):
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex(), digest)

class ApiError(Exception):
    def __init__(self, msg, code=400): self.msg, self.code = msg, code

def create_app(db_path=None):
    app = Flask(__name__, static_folder=None)
    app.config["DB"] = db_path or os.environ.get("DB_PATH", os.path.join(BASE, "edubridge.db"))

    def db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB"]); g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys=ON")
        return g.db

    @app.teardown_appcontext
    def close(_):
        c = g.pop("db", None)
        if c: c.close()

    with sqlite3.connect(app.config["DB"]) as c: c.executescript(SCHEMA)

    def public(u): return {k: u[k] for k in ("id", "name", "role", "skills", "bio", "city", "rate")}
    def me_json(u): return dict(public(u), email=u["email"])

    def auth(role=None):
        def deco(fn):
            @wraps(fn)
            def wrap(*a, **kw):
                tok = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                row = db().execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?",
                                   (h(tok), iso())).fetchone() if tok else None
                if not row: raise ApiError("Please sign in.", 401)
                if role and row["role"] != role: raise ApiError(f"Only {role}s can do this.", 403)
                g.user, g.token = row, tok
                return fn(*a, **kw)
            return wrap
        return deco

    def body(*req):
        d = request.get_json(silent=True)
        if not isinstance(d, dict): raise ApiError("Send a JSON body.")
        out = {k: str(d.get(k) or "").strip() for k in d}
        for k in req:
            if not out.get(k): raise ApiError(f"{k.capitalize()} is required.")
        return out

    def new_session(uid):
        tok = secrets.token_urlsafe(32)
        db().execute("INSERT INTO sessions VALUES(?,?,?)", (h(tok), uid, iso(now() + timedelta(days=SESSION_DAYS))))
        db().commit(); return tok

    @app.errorhandler(ApiError)
    def api_err(e): return jsonify(error=e.msg), e.code

    @app.errorhandler(404)
    def nf(_): return (jsonify(error="Not found."), 404) if request.path.startswith("/api") else send_from_directory(os.path.join(BASE, "static"), "index.html")

    @app.errorhandler(500)
    def boom(_): return jsonify(error="Something went wrong on the server."), 500

    # ---- auth ----
    @app.post("/api/register")
    def register():
        d = body("name", "email", "password", "role")
        email = d["email"].lower()
        if not EMAIL_RE.match(email): raise ApiError("Enter a valid email address.")
        if len(d["password"]) < 8: raise ApiError("Password must be at least 8 characters.")
        if d["role"] not in ("student", "tutor"): raise ApiError("Choose student or tutor.")
        try:
            cur = db().execute("INSERT INTO users(name,email,password,role,skills,city,created) VALUES(?,?,?,?,?,?,?)",
                               (d["name"][:100], email, hash_pw(d["password"]), d["role"], d.get("skills", "")[:300], d.get("city", "")[:80], iso()))
            db().commit()
        except sqlite3.IntegrityError:
            raise ApiError("An account with this email already exists.", 409)
        u = db().execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(token=new_session(u["id"]), user=me_json(u)), 201

    @app.post("/api/login")
    def login():
        d = body("email", "password")
        u = db().execute("SELECT * FROM users WHERE email=?", (d["email"].lower(),)).fetchone()
        if not u or not check_pw(d["password"], u["password"]): raise ApiError("Email or password is incorrect.", 401)
        return jsonify(token=new_session(u["id"]), user=me_json(u))

    @app.post("/api/logout")
    @auth()
    def logout():
        db().execute("DELETE FROM sessions WHERE token_hash=?", (h(g.token),)); db().commit(); return jsonify(ok=True)

    @app.get("/api/me")
    @auth()
    def me(): return jsonify(user=me_json(g.user))

    @app.put("/api/me")
    @auth()
    def update_me():
        d = body("name")
        rate = int(d.get("rate") or 0) if str(d.get("rate") or "0").isdigit() else 0
        db().execute("UPDATE users SET name=?,skills=?,bio=?,city=?,rate=? WHERE id=?",
                     (d["name"][:100], d.get("skills", "")[:300], d.get("bio", "")[:1000], d.get("city", "")[:80], min(rate, 100000) if g.user["role"] == "tutor" else 0, g.user["id"]))
        db().commit()
        return jsonify(user=me_json(db().execute("SELECT * FROM users WHERE id=?", (g.user["id"],)).fetchone()))

    # ---- tutors ----
    @app.get("/api/tutors")
    @auth()
    def tutors():
        q = f"%{request.args.get('q', '').strip().lower()}%"
        rows = db().execute("SELECT * FROM users WHERE role='tutor' AND (lower(name) LIKE ? OR lower(skills) LIKE ? OR lower(city) LIKE ?) ORDER BY name", (q, q, q)).fetchall()
        return jsonify(tutors=[public(r) for r in rows])

    # ---- bookings ----
    def booking_json(r): return {k: r[k] for k in r.keys()}

    @app.post("/api/bookings")
    @auth("student")
    def book():
        d = body("tutor_id", "topic")
        t = db().execute("SELECT id FROM users WHERE id=? AND role='tutor'", (d["tutor_id"],)).fetchone() if d["tutor_id"].isdigit() else None
        if not t: raise ApiError("Tutor not found.", 404)
        cur = db().execute("INSERT INTO bookings(student_id,tutor_id,topic,note,slot,created) VALUES(?,?,?,?,?,?)",
                           (g.user["id"], t["id"], d["topic"][:200], d.get("note", "")[:1000], d.get("slot", "")[:100], iso()))
        db().commit()
        return jsonify(id=cur.lastrowid), 201

    @app.get("/api/bookings")
    @auth()
    def bookings():
        col, other = ("student_id", "tutor_id") if g.user["role"] == "student" else ("tutor_id", "student_id")
        rows = db().execute(f"SELECT b.*, u.name AS other_name FROM bookings b JOIN users u ON u.id=b.{other} WHERE b.{col}=? ORDER BY b.id DESC", (g.user["id"],)).fetchall()
        return jsonify(bookings=[booking_json(r) for r in rows])

    @app.post("/api/bookings/<int:bid>/status")
    @auth()
    def booking_status(bid):
        status = body("status")["status"]
        b = db().execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()
        if not b or g.user["id"] not in (b["student_id"], b["tutor_id"]): raise ApiError("Booking not found.", 404)
        is_tutor = g.user["id"] == b["tutor_id"]
        allowed = {("tutor", "Pending"): {"Accepted", "Declined"}, ("tutor", "Accepted"): {"Completed"}, ("student", "Pending"): {"Cancelled"}, ("student", "Accepted"): {"Cancelled"}}
        if status not in allowed.get(("tutor" if is_tutor else "student", b["status"]), set()):
            raise ApiError(f"You can't change a {b['status']} booking to {status}.", 409)
        db().execute("UPDATE bookings SET status=? WHERE id=?", (status, bid)); db().commit()
        return jsonify(ok=True, status=status)

    # ---- doubts ----
    @app.get("/api/doubts")
    @auth()
    def doubts():
        rows = db().execute("SELECT d.*, u.name AS student_name FROM doubts d JOIN users u ON u.id=d.student_id ORDER BY d.id DESC LIMIT 100").fetchall()
        out = []
        for r in rows:
            reps = db().execute("SELECT r.id,r.body,r.created,u.name,u.role FROM replies r JOIN users u ON u.id=r.user_id WHERE r.doubt_id=? ORDER BY r.id", (r["id"],)).fetchall()
            out.append(dict(booking_json(r), replies=[booking_json(x) for x in reps]))
        return jsonify(doubts=out)

    @app.post("/api/doubts")
    @auth("student")
    def post_doubt():
        d = body("subject", "question")
        cur = db().execute("INSERT INTO doubts(student_id,subject,question,created) VALUES(?,?,?,?)", (g.user["id"], d["subject"][:100], d["question"][:2000], iso()))
        db().commit(); return jsonify(id=cur.lastrowid), 201

    @app.post("/api/doubts/<int:did>/replies")
    @auth()
    def reply(did):
        d = body("body")
        if not db().execute("SELECT 1 FROM doubts WHERE id=?", (did,)).fetchone(): raise ApiError("Doubt not found.", 404)
        db().execute("INSERT INTO replies(doubt_id,user_id,body,created) VALUES(?,?,?,?)", (did, g.user["id"], d["body"][:2000], iso()))
        db().commit(); return jsonify(ok=True), 201

    @app.get("/api/health")
    def health(): return jsonify(status="ok")

    # ---- frontend ----
    @app.get("/")
    def index(): return send_from_directory(os.path.join(BASE, "static"), "index.html")

    @app.get("/static/<path:p>")
    def static_files(p): return send_from_directory(os.path.join(BASE, "static"), p)

    return app

app = create_app() if os.environ.get("EDUBRIDGE_NO_AUTOAPP") != "1" else None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
