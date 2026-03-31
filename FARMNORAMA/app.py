from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, random, smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "farmnorama_secret"


# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        otp TEXT,
        otp_expiry TEXT,
        verified INTEGER DEFAULT 0,
        role TEXT,
        function TEXT,
        usage TEXT,
        deleted INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        fullname TEXT,
        phone TEXT,
        address TEXT,
        bio TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        title TEXT,
        status TEXT,
        priority TEXT,
        due_date TEXT
    )
    """)

    conn.commit()
    conn.close()


# ================= EMAIL =================
def send_otp_email(receiver_email, otp):
    sender_email = "greatneo.gil@gmail.com"
    sender_password = "uuzi fafk mdwj yrwc"

    msg = MIMEText(f"Your Farmnorama OTP is: {otp}")
    msg["Subject"] = "Farmnorama OTP"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("EMAIL ERROR:", e)


# ================= AUTH =================
@app.route("/")
def login():
    return render_template("login.html")


@app.route("/login_user", methods=["POST"])
def login_user():
    email = request.form.get("email")
    password = request.form.get("password")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=? AND password=? AND deleted=0", (email, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session["email"] = email

        # check if profile exists
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE email=?", (email,))
        profile = cursor.fetchone()
        conn.close()

        if profile:
            return redirect("/dashboard")
        else:
            return redirect("/create_profile")

    return render_template("login.html", error="wrong")


@app.route("/signup")
def signup():
    return render_template("signup.html")


@app.route("/create_account", methods=["POST"])
def create_account():
    email = request.form.get("email")
    password = request.form.get("password")

    if not email or "@" not in email:
        return render_template("signup.html", error="invalid")

    otp = str(random.randint(100000, 999999))
    expiry = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (email,password,otp,otp_expiry) VALUES (?,?,?,?)",
                       (email, password, otp, expiry))
        conn.commit()
        conn.close()

        send_otp_email(email, otp)
        session["email"] = email
        return redirect("/verify")

    except:
        return render_template("signup.html", error="exists")


# ================= OTP =================
@app.route("/verify")
def verify():
    return render_template("otp.html")


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    otp_input = request.form.get("otp")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT otp,otp_expiry FROM users WHERE email=?", (session["email"],))
    data = cursor.fetchone()

    if not data:
        return redirect("/signup")

    real_otp, expiry = data
    expiry = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")

    if datetime.now() > expiry:
        return render_template("otp.html", error="expired")

    if otp_input == real_otp:
        cursor.execute("UPDATE users SET verified=1 WHERE email=?", (session["email"],))
        conn.commit()
        conn.close()
        return redirect("/work_info")

    return render_template("otp.html", error="wrong")


# ================= WORK INFO =================
@app.route("/work_info")
def work_info():
    return render_template("work_info.html")


@app.route("/save_work", methods=["POST"])
def save_work():
    role = request.form.get("role")
    function = request.form.get("function")
    usage = request.form.get("usage")

    if role == "Other":
        role = request.form.get("role_other")
    if function == "Other":
        function = request.form.get("function_other")
    if usage == "Other":
        usage = request.form.get("usage_other")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role=?,function=?,usage=? WHERE email=?",
                   (role, function, usage, session["email"]))
    conn.commit()
    conn.close()

    return redirect("/create_profile")


# ================= PROFILE =================
@app.route("/create_profile")
def create_profile():
    if "email" not in session:
        return redirect("/")
    return render_template("create_profile.html")


@app.route("/save_profile", methods=["POST"])
def save_profile():
    fullname = request.form.get("fullname")
    phone = request.form.get("phone")
    address = request.form.get("address")
    bio = request.form.get("bio")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO profiles(email, fullname, phone, address, bio)
    VALUES(?,?,?,?,?)
    """, (session["email"], fullname, phone, address, bio))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/profile")
def profile():
    if "email" not in session:
        return redirect("/")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE email=?", (session["email"],))
    profile = cursor.fetchone()
    conn.close()

    return render_template("profile.html", profile=profile)


@app.route("/update_profile", methods=["POST"])
def update_profile():
    fullname = request.form.get("fullname")
    phone = request.form.get("phone")
    address = request.form.get("address")
    bio = request.form.get("bio")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE profiles SET fullname=?, phone=?, address=?, bio=?
    WHERE email=?
    """, (fullname, phone, address, bio, session["email"]))

    conn.commit()
    conn.close()

    return redirect("/profile")


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/")
    return render_template("dashboard.html")


# ================= TASKS =================
@app.route("/get_tasks")
def get_tasks():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE email=?", (session.get("email"),))
    tasks = cursor.fetchall()
    conn.close()
    return {"tasks": tasks}


@app.route("/add_task", methods=["POST"])
def add_task():
    title = request.form.get("title")
    priority = request.form.get("priority")
    due_date = request.form.get("due_date")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO tasks(email,title,status,priority,due_date)
    VALUES(?,?,?,?,?)
    """, (session["email"], title, "To do", priority, due_date))

    conn.commit()
    conn.close()

    return {"status": "success"}


@app.route("/update_task", methods=["POST"])
def update_task():
    task_id = request.form.get("id")
    status = request.form.get("status")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
    conn.commit()
    conn.close()

    return {"status": "updated"}


@app.route("/edit_task", methods=["POST"])
def edit_task():
    task_id = request.form.get("id")
    title = request.form.get("title")
    priority = request.form.get("priority")
    due_date = request.form.get("due_date")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE tasks SET title=?, priority=?, due_date=? WHERE id=?
    """, (title, priority, due_date, task_id))
    conn.commit()
    conn.close()

    return {"status": "edited"}


@app.route("/delete_task", methods=["POST"])
def delete_task():
    task_id = request.form.get("id")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

    return {"status": "deleted"}


# ================= DELETE ACCOUNT =================
@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "email" not in session:
        return {"status":"error"}

    email = session["email"]
    password = request.form.get("password")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = cursor.fetchone()

    if not user:
        return {"status":"wrong_password"}

    cursor.execute("UPDATE users SET deleted=1 WHERE email=?", (email,))
    cursor.execute("DELETE FROM tasks WHERE email=?", (email,))

    conn.commit()
    conn.close()

    session.clear()

    return {"status":"deleted"}


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)