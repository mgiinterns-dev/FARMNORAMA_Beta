from flask import Flask, render_template, request, redirect, session, jsonify, send_file
import sqlite3
import random
import smtplib
import csv
import shutil
import os
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "farmnorama_secret"

DATABASE = "database.db"
BACKUP_PATH = "backup_database.db"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ================= DATABASE =================
def get_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def safe_alter(cursor, table_name, column_name, column_type):
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    except sqlite3.OperationalError:
        pass


def init_db():
    conn = get_conn()
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
        usage TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        fullname TEXT,
        phone TEXT,
        address TEXT,
        bio TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        title TEXT,
        status TEXT,
        priority TEXT,
        due_date TEXT
    )
    """)

    # Safe upgrades
    safe_alter(cursor, "users", "is_admin", "INTEGER DEFAULT 0")
    safe_alter(cursor, "profiles", "company", "TEXT")
    safe_alter(cursor, "profiles", "position", "TEXT")
    safe_alter(cursor, "profiles", "website", "TEXT")
    safe_alter(cursor, "profiles", "gender", "TEXT")
    safe_alter(cursor, "profiles", "photo", "TEXT")

    conn.commit()
    conn.close()


# ================= HELPERS =================
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_photo(file_obj, email_prefix="user"):
    if not file_obj or file_obj.filename == "":
        return None

    if not allowed_file(file_obj.filename):
        return None

    filename = secure_filename(file_obj.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    final_name = f"{email_prefix}_{int(datetime.now().timestamp())}.{ext}"
    final_path = os.path.join(app.config["UPLOAD_FOLDER"], final_name)
    file_obj.save(final_path)
    return final_name


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
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False


def make_otp():
    return str(random.randint(100000, 999999))


def make_expiry(minutes=5):
    return (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def ensure_first_admin(email):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS admin_count FROM users WHERE is_admin=1")
    admin_count = cursor.fetchone()["admin_count"]

    if admin_count == 0:
        cursor.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
        conn.commit()

    conn.close()


# ================= AUTH =================
@app.route("/")
def login():
    if "email" in session:
        if session.get("is_admin") == 1:
            return redirect("/admin_dashboard")
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/login_user", methods=["POST"])
def login_user():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return render_template("login.html", error="wrong")

    session["email"] = user["email"]
    session["is_admin"] = user["is_admin"]

    if user["is_admin"] == 1:
        return redirect("/admin_dashboard")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE email=?", (email,))
    profile = cursor.fetchone()
    conn.close()

    if profile:
        return redirect("/dashboard")
    return redirect("/create_profile")


@app.route("/signup")
def signup():
    return render_template("signup.html")


@app.route("/create_account", methods=["POST"])
def create_account():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not email or "@" not in email or not password:
        return render_template("signup.html", error="invalid")

    otp = make_otp()
    expiry = make_expiry()

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO users (email, password, otp, otp_expiry, verified)
        VALUES (?, ?, ?, ?, 0)
        """, (email, password, otp, expiry))
        conn.commit()
        conn.close()

        ensure_first_admin(email)

        send_otp_email(email, otp)
        session["email"] = email
        session["is_admin"] = 0
        return redirect("/verify")

    except sqlite3.IntegrityError:
        return render_template("signup.html", error="exists")


# ================= OTP =================
@app.route("/verify")
def verify():
    if "email" not in session:
        return redirect("/")
    return render_template("otp.html")


@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    if "email" not in session:
        return redirect("/")

    otp_input = request.form.get("otp", "").strip()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT otp, otp_expiry FROM users WHERE email=?", (session["email"],))
    data = cursor.fetchone()

    if not data:
        conn.close()
        return redirect("/signup")

    real_otp = data["otp"]
    expiry = datetime.strptime(data["otp_expiry"], "%Y-%m-%d %H:%M:%S")

    if datetime.now() > expiry:
        conn.close()
        return render_template("otp.html", error="expired")

    if otp_input == real_otp:
        cursor.execute("UPDATE users SET verified=1 WHERE email=?", (session["email"],))
        conn.commit()
        conn.close()
        return redirect("/work_info")

    conn.close()
    return render_template("otp.html", error="wrong")


@app.route("/resend_otp")
def resend_otp():
    if "email" not in session:
        return redirect("/")

    otp = make_otp()
    expiry = make_expiry()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET otp=?, otp_expiry=? WHERE email=?",
        (otp, expiry, session["email"])
    )
    conn.commit()
    conn.close()

    send_otp_email(session["email"], otp)
    return render_template("otp.html", message="OTP resent successfully.")


# ================= FORGOT PASSWORD =================
@app.route("/forgot")
def forgot():
    return render_template("forgot.html")


@app.route("/forgot_password", methods=["POST"])
def forgot_password():
    email = request.form.get("email", "").strip()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return render_template("forgot.html", message="Email not found.")

    otp = make_otp()
    expiry = make_expiry()

    cursor.execute(
        "UPDATE users SET otp=?, otp_expiry=? WHERE email=?",
        (otp, expiry, email)
    )
    conn.commit()
    conn.close()

    session["reset_email"] = email
    send_otp_email(email, otp)

    return render_template("reset_password.html", email=email)


@app.route("/reset_password_submit", methods=["POST"])
def reset_password_submit():
    email = session.get("reset_email")
    otp = request.form.get("otp", "").strip()
    new_password = request.form.get("password", "").strip()

    if not email:
        return redirect("/forgot")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT otp, otp_expiry FROM users WHERE email=?", (email,))
    data = cursor.fetchone()

    if not data:
        conn.close()
        return render_template("reset_password.html", error="Invalid request.", email=email)

    expiry = datetime.strptime(data["otp_expiry"], "%Y-%m-%d %H:%M:%S")

    if datetime.now() > expiry:
        conn.close()
        return render_template("reset_password.html", error="OTP expired.", email=email)

    if otp != data["otp"]:
        conn.close()
        return render_template("reset_password.html", error="Invalid OTP.", email=email)

    cursor.execute("UPDATE users SET password=? WHERE email=?", (new_password, email))
    conn.commit()
    conn.close()

    session.pop("reset_email", None)
    return redirect("/")


# ================= WORK INFO =================
@app.route("/work_info")
def work_info():
    if "email" not in session:
        return redirect("/")
    return render_template("work_info.html")


@app.route("/save_work", methods=["POST"])
def save_work():
    if "email" not in session:
        return redirect("/")

    role = request.form.get("role")
    function_name = request.form.get("function")
    usage = request.form.get("usage")

    if role == "Other":
        role = request.form.get("role_other")
    if function_name == "Other":
        function_name = request.form.get("function_other")
    if usage == "Other":
        usage = request.form.get("usage_other")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE users SET role=?, function=?, usage=?
    WHERE email=?
    """, (role, function_name, usage, session["email"]))
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
    if "email" not in session:
        return redirect("/")

    position = request.form.get("position")
    if position == "Other":
        position = request.form.get("position_other")

    photo_file = request.files.get("photo")
    photo_name = save_uploaded_photo(photo_file, session["email"].split("@")[0])

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR REPLACE INTO profiles (
        email, fullname, phone, address, bio, company, position, website, gender, photo
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["email"],
        request.form.get("fullname"),
        request.form.get("phone"),
        request.form.get("address"),
        request.form.get("bio"),
        request.form.get("company"),
        position,
        request.form.get("website"),
        request.form.get("gender"),
        photo_name
    ))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/profile")
def profile():
    if "email" not in session:
        return redirect("/")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE email=?", (session["email"],))
    profile_data = cursor.fetchone()
    conn.close()

    return render_template("profile.html", profile=profile_data)


@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "email" not in session:
        return redirect("/")

    position = request.form.get("position")
    if position == "Other":
        position = request.form.get("position_other")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE email=?", (session["email"],))
    existing = cursor.fetchone()

    current_photo = existing["photo"] if existing else None
    photo_file = request.files.get("photo")
    new_photo = save_uploaded_photo(photo_file, session["email"].split("@")[0])
    final_photo = new_photo if new_photo else current_photo

    values = (
        request.form.get("fullname"),
        request.form.get("phone"),
        request.form.get("address"),
        request.form.get("bio"),
        request.form.get("company"),
        position,
        request.form.get("website"),
        request.form.get("gender"),
        final_photo,
        session["email"]
    )

    if existing:
        cursor.execute("""
        UPDATE profiles
        SET fullname=?, phone=?, address=?, bio=?, company=?, position=?, website=?, gender=?, photo=?
        WHERE email=?
        """, values)
    else:
        cursor.execute("""
        INSERT INTO profiles (
            fullname, phone, address, bio, company, position, website, gender, photo, email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)

    conn.commit()
    conn.close()

    return redirect("/profile")


@app.route("/get_email")
def get_email():
    return jsonify({"email": session.get("email")})


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect("/")
    if session.get("is_admin") == 1:
        return redirect("/admin_dashboard")
    return render_template("dashboard.html")


@app.route("/admin_dashboard")
def admin_dashboard():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/")

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    cursor.execute("SELECT COUNT(*) AS verified_users FROM users WHERE verified=1")
    verified_users = cursor.fetchone()["verified_users"]

    cursor.execute("SELECT COUNT(*) AS total_tasks FROM tasks")
    total_tasks = cursor.fetchone()["total_tasks"]

    cursor.execute("SELECT COUNT(*) AS total_profiles FROM profiles")
    total_profiles = cursor.fetchone()["total_profiles"]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        verified_users=verified_users,
        total_tasks=total_tasks,
        total_profiles=total_profiles
    )


@app.route("/export_users_report")
def export_users_report():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT email, verified, role, function, usage, is_admin
    FROM users
    ORDER BY email
    """)
    rows = cursor.fetchall()
    conn.close()

    report_path = "users_report.csv"
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Email", "Verified", "Role", "Function", "Usage", "Is Admin"])
        for row in rows:
            writer.writerow([
                row["email"],
                row["verified"],
                row["role"],
                row["function"],
                row["usage"],
                row["is_admin"]
            ])

    return send_file(report_path, as_attachment=True)


@app.route("/backup_database")
def backup_database():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/")

    shutil.copyfile(DATABASE, BACKUP_PATH)
    return send_file(BACKUP_PATH, as_attachment=True)


# ================= TASKS =================
@app.route("/get_tasks")
def get_tasks():
    if "email" not in session:
        return jsonify({"tasks": []})

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE email=?", (session["email"],))
    tasks = cursor.fetchall()
    conn.close()

    return jsonify({"tasks": [tuple(row) for row in tasks]})


@app.route("/add_task", methods=["POST"])
def add_task():
    if "email" not in session:
        return jsonify({"status": "error"})

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO tasks (email, title, status, priority, due_date)
    VALUES (?, ?, ?, ?, ?)
    """, (
        session["email"],
        request.form.get("title"),
        "To do",
        request.form.get("priority"),
        request.form.get("due_date")
    ))
    conn.commit()
    conn.close()

    return jsonify({"status": "success"})


@app.route("/update_task", methods=["POST"])
def update_task():
    if "email" not in session:
        return jsonify({"status": "error"})

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE tasks SET status=? WHERE id=? AND email=?
    """, (
        request.form.get("status"),
        request.form.get("id"),
        session["email"]
    ))
    conn.commit()
    conn.close()

    return jsonify({"status": "updated"})


@app.route("/edit_task", methods=["POST"])
def edit_task():
    if "email" not in session:
        return jsonify({"status": "error"})

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE tasks SET title=?, priority=?, due_date=? WHERE id=? AND email=?
    """, (
        request.form.get("title"),
        request.form.get("priority"),
        request.form.get("due_date"),
        request.form.get("id"),
        session["email"]
    ))
    conn.commit()
    conn.close()

    return jsonify({"status": "edited"})


@app.route("/delete_task", methods=["POST"])
def delete_task():
    if "email" not in session:
        return jsonify({"status": "error"})

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    DELETE FROM tasks WHERE id=? AND email=?
    """, (
        request.form.get("id"),
        session["email"]
    ))
    conn.commit()
    conn.close()

    return jsonify({"status": "deleted"})


# ================= DELETE ACCOUNT =================
@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "email" not in session:
        return jsonify({"status": "error"})

    email = session["email"]
    password = request.form.get("password", "").strip()

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({"status": "wrong_password"})

    cursor.execute("DELETE FROM tasks WHERE email=?", (email,))
    cursor.execute("DELETE FROM profiles WHERE email=?", (email,))
    cursor.execute("DELETE FROM users WHERE email=?", (email,))
    conn.commit()
    conn.close()

    session.clear()
    return jsonify({"status": "deleted"})


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)