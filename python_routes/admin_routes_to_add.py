# Add these routes to your app.py or admin routes file

from flask import render_template, request, redirect, session, flash

@app.route("/admin/users")
def admin_users():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/admin/login")

    q = request.args.get("q", "").strip()
    verified = request.args.get("verified", "").strip()
    admin = request.args.get("admin", "").strip()

    conn = get_conn()
    cursor = conn.cursor()

    sql = "SELECT email, verified, role, is_admin FROM users WHERE 1=1"
    params = []

    if q:
        sql += " AND email LIKE ?"
        params.append(f"%{q}%")

    if verified in ("0", "1"):
        sql += " AND verified=?"
        params.append(verified)

    if admin in ("0", "1"):
        sql += " AND is_admin=?"
        params.append(admin)

    sql += " ORDER BY is_admin DESC, email ASC"

    cursor.execute(sql, params)
    users = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", users=users)

@app.route("/admin/promote_user", methods=["POST"])
def promote_user():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/admin/login")

    email = request.form.get("email", "").strip()
    if not email or email == session.get("email"):
        return redirect("/admin/users")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin=1 WHERE email=?", (email,))
    conn.commit()
    conn.close()
    return redirect("/admin/users")

@app.route("/admin/demote_user", methods=["POST"])
def demote_user():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/admin/login")

    email = request.form.get("email", "").strip()
    if not email or email == session.get("email"):
        return redirect("/admin/users")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_admin=0 WHERE email=?", (email,))
    conn.commit()
    conn.close()
    return redirect("/admin/users")

@app.route("/admin/delete_user", methods=["POST"])
def admin_delete_user():
    if "email" not in session or session.get("is_admin") != 1:
        return redirect("/admin/login")

    email = request.form.get("email", "").strip()
    if not email or email == session.get("email"):
        return redirect("/admin/users")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE email=?", (email,))
    cursor.execute("DELETE FROM profiles WHERE email=?", (email,))
    cursor.execute("DELETE FROM users WHERE email=?", (email,))
    conn.commit()
    conn.close()
    return redirect("/admin/users")

# Also update your admin dashboard route so it passes total_admins:
#
# cursor.execute("SELECT COUNT(*) AS total_admins FROM users WHERE is_admin=1")
# total_admins = cursor.fetchone()["total_admins"]
#
# and in render_template(...):
# total_admins=total_admins
