# app.py — Expansive Tracker (with login/register + user-scoped expenses)
from functools import wraps
import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_key_123"

# ============================
# DATABASE PATH
# ============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "expenses.db")

# ============================
# DB CONNECTION
# ============================
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=3)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except:
        pass
    return conn

def table_has_column(table, column):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r["name"] for r in cur.fetchall()]
    conn.close()
    return column in cols

# ============================
# INITIAL SETUP
# ============================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # main expense table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # add missing category column
    if not table_has_column("expenses", "category"):
        cur.execute("ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'General'")
        conn.commit()
        cur.execute("UPDATE expenses SET category='General' WHERE category IS NULL")
        conn.commit()

    # users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # user_id column for expenses
    if not table_has_column("expenses", "user_id"):
        cur.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER DEFAULT NULL")
        conn.commit()

    conn.close()

# ============================
# AUTH HELPERS
# ============================
def current_user_id():
    return session.get("user_id")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

# ============================
# WELCOME PAGE
# ============================
@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

# ============================
# ROOT REDIRECT
# ============================
@app.route("/")
def root():
    if not current_user_id():
        return redirect(url_for("welcome"))
    return redirect(url_for("index"))

# ============================
# MAIN SECTIONS (RENDER index.html)
# ============================
@app.route("/dashboard")
@login_required
def index():
    uid = current_user_id()
    return render_template("index.html",
                           expenses=fetch_all_expenses(uid),
                           summary=compute_summary(uid),
                           active_section="dashboard")

@app.route("/add")
@login_required
def add_page():
    uid = current_user_id()
    return render_template("index.html",
                           expenses=fetch_all_expenses(uid),
                           summary=compute_summary(uid),
                           active_section="add")

@app.route("/analytics")
@login_required
def analytics_page():
    uid = current_user_id()
    return render_template("index.html",
                           expenses=fetch_all_expenses(uid),
                           summary=compute_summary(uid),
                           active_section="analytics")

@app.route("/history")
@login_required
def history_page():
    uid = current_user_id()
    return render_template("index.html",
                           expenses=fetch_all_expenses(uid),
                           summary=compute_summary(uid),
                           active_section="history")

# ============================
# FETCH EXPENSES
# ============================
def fetch_all_expenses(uid=None):
    conn = get_conn()
    cur = conn.cursor()
    if uid:
        cur.execute("""
            SELECT id, title, amount, category,
            strftime('%Y-%m-%d %H:%M', date) AS date_display
            FROM expenses WHERE user_id=? ORDER BY id DESC
        """, (uid,))
    else:
        cur.execute("""
            SELECT id, title, amount, category,
            strftime('%Y-%m-%d %H:%M', date) AS date_display
            FROM expenses ORDER BY id DESC
        """)

    rows = cur.fetchall()
    conn.close()
    return [(r["id"], r["title"], float(r["amount"]), r["category"], r["date_display"]) for r in rows]

# ============================
# SUMMARY
# ============================
def compute_summary(uid=None):
    conn = get_conn()
    cur = conn.cursor()

    if uid:
        cur.execute("SELECT category, SUM(amount) FROM expenses WHERE user_id=? GROUP BY category", (uid,))
    else:
        cur.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")

    by_cat = {}
    total_income = 0
    total_expense = 0

    for row in cur.fetchall():
        cat = row[0] or "General"
        total = float(row[1] or 0)
        by_cat[cat] = total

        if cat.lower() == "income":
            total_income += total
        else:
            total_expense += total

    conn.close()
    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income - total_expense,
        "by_category": by_cat
    }

# ============================
# OLD POST ADD (ADD PAGE ONLY)
# ============================
@app.route("/add", methods=["POST"])
@login_required
def add_expense():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "General").strip()
    amount_raw = request.form.get("amount", "0").strip()

    try:
        amount = float(amount_raw)
    except:
        amount = 0

    if title and amount > 0:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO expenses (title, amount, category, date, user_id)
            VALUES (?, ?, ?, datetime('now'), ?)
        """, (title, amount, category, current_user_id()))
        conn.commit()
        conn.close()

    return redirect(url_for("index"))

# ============================
# DELETE (FROM HISTORY)
# ============================
@app.route("/delete/<int:eid>")
@login_required
def delete_expense(eid):
    uid = current_user_id()
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM expenses WHERE id=?", (eid,))
    row = cur.fetchone()

    if not row or row["user_id"] != uid:
        conn.close()
        return redirect(url_for("index"))

    cur.execute("DELETE FROM expenses WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# ============================
# AUTH — REGISTER
# ============================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not username or not email or not password:
            return "Invalid Input", 400

        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO users (username, email, password)
                VALUES (?, ?, ?)
            """, (username, email, generate_password_hash(password)))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "User Already Exists", 400

        conn.close()
        return redirect(url_for("login"))

    return render_template("register.html")

# ============================
# AUTH — LOGIN
# ============================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))

        return "Invalid Login", 400

    return render_template("login.html")

# ============================
# LOGOUT
# ============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ============================
# API — ADD EXPENSE (AJAX)
# ============================
@app.route("/api/add", methods=["POST"])
def api_add():
    uid = current_user_id()
    if not uid:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    data = request.get_json(silent=True) or {}

    title = data.get("title", "").strip()
    category = data.get("category", "General").strip()

    try:
        amount = float(data.get("amount", 0))
    except:
        amount = 0

    if not title or amount <= 0:
        return jsonify({"ok": False, "error": "invalid_input"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO expenses (title, amount, category, date, user_id)
        VALUES (?, ?, ?, datetime('now'), ?)
    """, (title, amount, category, uid))
    conn.commit()
    conn.close()

    summary = compute_summary(uid)
    items = [list(r) for r in fetch_all_expenses(uid)]


    return jsonify({
        "ok": True,
        "summary": summary,
        "items": items
    })

# ============================
# API — DELETE (AJAX)
# ============================
@app.route("/api/delete/<int:eid>", methods=["DELETE"])
def api_delete(eid):
    uid = current_user_id()
    if not uid:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    conn = get_conn()
    cur = conn.cursor()

    # verify owner
    cur.execute("SELECT user_id FROM expenses WHERE id=?", (eid,))
    row = cur.fetchone()
    if not row or row["user_id"] != uid:
        conn.close()
        return jsonify({"ok": False}), 400

    cur.execute("DELETE FROM expenses WHERE id=?", (eid,))
    conn.commit()
    conn.close()

    summary = compute_summary(uid)
    items = fetch_all_expenses(uid)

    return jsonify({
        "ok": True,
        "summary": summary,
        "items": items
    })

# ============================
# API — SEND FULL EXPENSE LIST
# ============================
@app.route("/api/expenses")
def api_expenses():
    uid = current_user_id()
    if not uid:
        return jsonify([])

    return jsonify([
        {
            "id": r[0],
            "title": r[1],
            "amount": r[2],
            "category": r[3],
            "date": r[4]
        }
        for r in fetch_all_expenses(uid)
    ])

# ============================
# API — SUMMARY REFRESH
# ============================
@app.route("/api/summary")
def api_summary():
    uid = current_user_id()
    if not uid:
        return jsonify({})
    return jsonify(compute_summary(uid))

# ============================
# MAIN
# ============================
if __name__ == "__main__":
    init_db()
    print("🔥 Expansive Tracker running at: http://127.0.0.1:5000")
    app.run(debug=True)

from flask import Flask
import os

# your existing code (do not remove anything above)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
