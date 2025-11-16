# app.py — Expansive Tracker (Render-ready, persistent DB)
from functools import wraps
import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# =============================================
# SECURITY + SESSION
# =============================================
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# =============================================
# DATABASE PATH — Render PERMANENT STORAGE
# =============================================
# Render persistent directory
BASE_DIR = "/opt/render/project/data"
os.makedirs(BASE_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "expenses.db")

# =============================================
# DB CONNECTION
# =============================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
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

# =============================================
# INITIAL DATABASE SETUP
# =============================================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Expenses table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    if not table_has_column("expenses", "category"):
        cur.execute("ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'General'")
        conn.commit()

    if not table_has_column("expenses", "user_id"):
        cur.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER DEFAULT NULL")
        conn.commit()

    # Users table
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
    conn.close()

# Ensure tables exist on every startup
init_db()

# =============================================
# AUTH HELPERS
# =============================================
def current_user_id():
    return session.get("user_id")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

# =============================================
# ROUTES
# =============================================
@app.route("/welcome")
def welcome():
    return render_template("welcome.html")

@app.route("/")
def root():
    if not current_user_id():
        return redirect(url_for("welcome"))
    return redirect(url_for("index"))

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

# =============================================
# FETCH DATA
# =============================================
def fetch_all_expenses(uid=None):
    conn = get_conn()
    cur = conn.cursor()
    if uid:
        cur.execute("""
            SELECT id, title, amount, category,
                   strftime('%Y-%m-%d %H:%M', date) AS date_display
            FROM expenses
            WHERE user_id=?
            ORDER BY id DESC
        """, (uid,))
    else:
        cur.execute("""
            SELECT id, title, amount, category,
                   strftime('%Y-%m-%d %H:%M', date) AS date_display
            FROM expenses
            ORDER BY id DESC
        """)
    rows = cur.fetchall()
    conn.close()
    return [(r["id"], r["title"], float(r["amount"]), r["category"], r["date_display"]) for r in rows]

# =============================================
# SUMMARY
# =============================================
def compute_summary(uid=None):
    conn = get_conn()
    cur = conn.cursor()
    if uid:
        cur.execute("SELECT category, SUM(amount) FROM expenses WHERE user_id=? GROUP BY category", (uid,))
    else:
        cur.execute("SELECT category, SUM(amount) FROM expenses GROUP BY category")
    summary = {}
    total_income = 0
    total_expense = 0
    for cat, total in cur.fetchall():
        total = float(total or 0)
        cat = cat or "General"
        summary[cat] = total
        if cat.lower() == "income":
            total_income += total
        else:
            total_expense += total
    conn.close()
    return {"total_income": total_income, "total_expense": total_expense, "balance": total_income-total_expense, "by_category": summary}

# =============================================
# ADD EXPENSE
# =============================================
@app.route("/add", methods=["POST"])
@login_required
def add_expense():
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "General").strip()
    try:
        amount = float(request.form.get("amount", "0"))
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

# =============================================
# DELETE EXPENSE
# =============================================
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

# =============================================
# REGISTER
# =============================================
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        username = request.form.get("username").strip()
        email = request.form.get("email").strip().lower()
        password = request.form.get("password").strip()
        if not username or not email or not password:
            return "Invalid Input", 400
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username,email,password) VALUES (?,?,?)",
                        (username,email,generate_password_hash(password)))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "User Already Exists", 400
        conn.close()
        return redirect(url_for("login"))
    return render_template("register.html")

# =============================================
# LOGIN
# =============================================
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email = request.form.get("email").strip().lower()
        password = request.form.get("password").strip()
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

# =============================================
# LOGOUT
# =============================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =============================================
# API ENDPOINTS
# =============================================
@app.route("/api/add", methods=["POST"])
def api_add():
    uid = current_user_id()
    if not uid:
        return jsonify({"ok":False,"error":"not_logged_in"}),401
    data = request.get_json() or {}
    title = data.get("title","").strip()
    category = data.get("category","General").strip()
    try:
        amount = float(data.get("amount",0))
    except:
        amount=0
    if not title or amount<=0:
        return jsonify({"ok":False,"error":"invalid_input"}),400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO expenses (title,amount,category,date,user_id) VALUES (?,?,?,?,?)",
                (title,amount,category,datetime('now'),uid))
    conn.commit()
    conn.close()
    return jsonify({"ok":True,"summary":compute_summary(uid),"items":[list(r) for r in fetch_all_expenses(uid)]})

@app.route("/api/delete/<int:eid>",methods=["DELETE"])
def api_delete(eid):
    uid = current_user_id()
    if not uid:
        return jsonify({"ok":False,"error":"not_logged_in"}),401
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM expenses WHERE id=?", (eid,))
    row = cur.fetchone()
    if not row or row["user_id"]!=uid:
        conn.close()
        return jsonify({"ok":False}),400
    cur.execute("DELETE FROM expenses WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({"ok":True,"summary":compute_summary(uid),"items":fetch_all_expenses(uid)})

@app.route("/api/expenses")
def api_expenses():
    uid = current_user_id()
    if not uid:
        return jsonify([])
    return jsonify([{"id":r[0],"title":r[1],"amount":r[2],"category":r[3],"date":r[4]} for r in fetch_all_expenses(uid)])

@app.route("/api/summary")
def api_summary():
    uid = current_user_id()
    if not uid:
        return jsonify({})
    return jsonify(compute_summary(uid))

# =============================================
# MAIN ENTRY
# =============================================
if __name__=="__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port,debug=False)
