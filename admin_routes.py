import csv
import shutil

from flask import Blueprint, current_app, redirect, render_template, request, send_file, session

from db import get_conn
from helpers import admin_required, log_action, super_admin_required

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')


def _ensure_users_role_columns():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(users)")
        cols = [row['name'] if hasattr(row, 'keys') else row[1] for row in cursor.fetchall()]

        if 'admin_level' not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN admin_level TEXT DEFAULT 'user'")

        if 'is_banned' not in cols:
            cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")

        cursor.execute("UPDATE users SET admin_level='sub_admin' WHERE is_admin=1 AND (admin_level IS NULL OR admin_level='user')")
        cursor.execute("UPDATE users SET is_admin=1 WHERE admin_level IN ('super_admin','sub_admin')")
        cursor.execute("UPDATE users SET is_admin=0 WHERE admin_level='user' OR admin_level IS NULL")

        cursor.execute("SELECT COUNT(*) AS c FROM users WHERE admin_level='super_admin'")
        if cursor.fetchone()['c'] == 0:
            cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
            first_user = cursor.fetchone()

            if first_user:
                cursor.execute(
                    "UPDATE users SET is_admin=1, admin_level='super_admin' WHERE id=?",
                    (first_user['id'],)
                )

        conn.commit()
        conn.close()

    except Exception:
        current_app.logger.exception('Ensure users role columns failed')


def _current_actor():
    return session.get('email', 'admin')


def _redirect_users():
    return redirect('/admin/users')


def _get_user_level(cursor, email):
    cursor.execute(
        'SELECT email, verified, role, function, usage, admin_level, is_banned FROM users WHERE email=?',
        (email,)
    )
    return cursor.fetchone()


def _is_self_target(target_email):
    return not target_email or target_email == session.get('email', '').strip().lower()


@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
    _ensure_users_role_columns()

    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) AS total_users FROM users')
        total_users = cursor.fetchone()['total_users']

        cursor.execute('SELECT COUNT(*) AS verified_users FROM users WHERE verified=1')
        verified_users = cursor.fetchone()['verified_users']

        cursor.execute('SELECT COUNT(*) AS total_tasks FROM tasks')
        total_tasks = cursor.fetchone()['total_tasks']

        cursor.execute('SELECT COUNT(*) AS total_profiles FROM profiles')
        total_profiles = cursor.fetchone()['total_profiles']

        cursor.execute('SELECT COUNT(*) AS total_logs FROM audit_logs')
        total_logs = cursor.fetchone()['total_logs']

        cursor.execute("SELECT COUNT(*) AS total_super_admins FROM users WHERE admin_level='super_admin'")
        total_super_admins = cursor.fetchone()['total_super_admins']

        cursor.execute("SELECT COUNT(*) AS total_sub_admins FROM users WHERE admin_level='sub_admin'")
        total_sub_admins = cursor.fetchone()['total_sub_admins']

        cursor.execute("SELECT COUNT(*) AS total_banned FROM users WHERE is_banned=1")
        total_banned = cursor.fetchone()['total_banned']

        cursor.execute("SELECT COUNT(*) AS total_farms FROM farms")
        total_farms = cursor.fetchone()['total_farms']

        cursor.execute("SELECT COUNT(*) AS total_farm_readings FROM farm_readings")
        total_farm_readings = cursor.fetchone()['total_farm_readings']

        cursor.execute("SELECT COUNT(*) AS total_recommendations FROM recommendations")
        total_recommendations = cursor.fetchone()['total_recommendations']

        cursor.execute("SELECT COUNT(*) AS total_high_alerts FROM recommendations WHERE severity='High'")
        total_high_alerts = cursor.fetchone()['total_high_alerts']

        cursor.execute("SELECT COUNT(*) AS total_notifications FROM notifications")
        total_notifications = cursor.fetchone()['total_notifications']

        cursor.execute("SELECT COUNT(*) AS unread_notifications FROM notifications WHERE is_read=0")
        unread_notifications = cursor.fetchone()['unread_notifications']

        cursor.execute("SELECT COUNT(*) AS read_notifications FROM notifications WHERE is_read=1")
        read_notifications = cursor.fetchone()['read_notifications']

        cursor.execute("""
            SELECT 
                recommendations.*,
                farms.farm_name,
                farms.email
            FROM recommendations
            JOIN farms ON recommendations.farm_id = farms.id
            ORDER BY recommendations.id DESC
            LIMIT 5
        """)
        latest_admin_recommendations = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM notifications
            ORDER BY id DESC
            LIMIT 5
        """)
        latest_notifications = cursor.fetchall()

        conn.close()

        return render_template(
            'admin_dashboard.html',
            total_users=total_users,
            verified_users=verified_users,
            total_tasks=total_tasks,
            total_profiles=total_profiles,
            total_logs=total_logs,
            total_super_admins=total_super_admins,
            total_sub_admins=total_sub_admins,
            total_banned=total_banned,
            total_farms=total_farms,
            total_farm_readings=total_farm_readings,
            total_recommendations=total_recommendations,
            total_high_alerts=total_high_alerts,
            latest_admin_recommendations=latest_admin_recommendations,
            total_notifications=total_notifications,
            unread_notifications=unread_notifications,
            read_notifications=read_notifications,
            latest_notifications=latest_notifications
        )

    except Exception:
        current_app.logger.exception('Admin dashboard failed')

        return render_template(
            'admin_dashboard.html',
            total_users=0,
            verified_users=0,
            total_tasks=0,
            total_profiles=0,
            total_logs=0,
            total_super_admins=0,
            total_sub_admins=0,
            total_banned=0,
            total_farms=0,
            total_farm_readings=0,
            total_recommendations=0,
            total_high_alerts=0,
            latest_admin_recommendations=[],
            total_notifications=0,
            unread_notifications=0,
            read_notifications=0,
            latest_notifications=[],
            error='Unable to load admin dashboard right now.'
        )


@admin_bp.route('/users')
@admin_required
def admin_users():
    _ensure_users_role_columns()

    search = request.args.get('q', '').strip()
    verified = request.args.get('verified', '').strip()
    admin_level = request.args.get('admin_level', '').strip()
    banned = request.args.get('banned', '').strip()

    try:
        conn = get_conn()
        cursor = conn.cursor()

        sql = 'SELECT email, verified, role, function, usage, admin_level, is_banned FROM users WHERE 1=1'
        params = []

        if search:
            sql += ' AND (email LIKE ? OR role LIKE ? OR function LIKE ? OR usage LIKE ?)'
            like_value = f'%{search}%'
            params.extend([like_value, like_value, like_value, like_value])

        if verified in ('0', '1'):
            sql += ' AND verified=?'
            params.append(verified)

        if admin_level in ('user', 'sub_admin', 'super_admin'):
            sql += ' AND admin_level=?'
            params.append(admin_level)

        if banned in ('0', '1'):
            sql += ' AND is_banned=?'
            params.append(banned)

        sql += " ORDER BY CASE admin_level WHEN 'super_admin' THEN 0 WHEN 'sub_admin' THEN 1 ELSE 2 END, email ASC"

        cursor.execute(sql, params)
        users = cursor.fetchall()

        conn.close()

        return render_template(
            'admin_users.html',
            users=users,
            search=search,
            error=None,
            current_admin_level=session.get('admin_level', 'user')
        )

    except Exception:
        current_app.logger.exception('Admin users load failed')

        return render_template(
            'admin_users.html',
            users=[],
            search=search,
            error='Unable to load users right now.',
            current_admin_level=session.get('admin_level', 'user')
        )


@admin_bp.route('/promote_to_sub_admin', methods=['POST'])
@admin_required
@super_admin_required
def promote_to_sub_admin():
    _ensure_users_role_columns()

    target_email = request.form.get('email', '').strip().lower()
    actor = _current_actor()

    try:
        if _is_self_target(target_email):
            return _redirect_users()

        conn = get_conn()
        cursor = conn.cursor()

        user = _get_user_level(cursor, target_email)

        if not user or user['admin_level'] != 'user':
            conn.close()
            return _redirect_users()

        cursor.execute(
            "UPDATE users SET is_admin=1, admin_level='sub_admin' WHERE email=?",
            (target_email,)
        )

        conn.commit()
        conn.close()

        log_action(actor, 'sub_admin_granted', f'Sub admin granted to {target_email}.')
        return _redirect_users()

    except Exception:
        current_app.logger.exception('Promote to sub admin failed')
        return _redirect_users()


@admin_bp.route('/demote_to_user', methods=['POST'])
@admin_required
@super_admin_required
def demote_to_user():
    _ensure_users_role_columns()

    target_email = request.form.get('email', '').strip().lower()
    actor = _current_actor()

    try:
        if _is_self_target(target_email):
            return _redirect_users()

        conn = get_conn()
        cursor = conn.cursor()

        user = _get_user_level(cursor, target_email)

        if not user or user['admin_level'] != 'sub_admin':
            conn.close()
            return _redirect_users()

        cursor.execute(
            "UPDATE users SET is_admin=0, admin_level='user' WHERE email=?",
            (target_email,)
        )

        conn.commit()
        conn.close()

        log_action(actor, 'sub_admin_revoked', f'Sub admin revoked from {target_email}.')
        return _redirect_users()

    except Exception:
        current_app.logger.exception('Demote to user failed')
        return _redirect_users()


@admin_bp.route('/ban_user', methods=['POST'])
@admin_required
def ban_user():
    _ensure_users_role_columns()

    target_email = request.form.get('email', '').strip().lower()
    actor = _current_actor()

    try:
        if _is_self_target(target_email):
            return _redirect_users()

        conn = get_conn()
        cursor = conn.cursor()

        user = _get_user_level(cursor, target_email)

        if not user:
            conn.close()
            return _redirect_users()

        if user['admin_level'] == 'super_admin':
            conn.close()
            return _redirect_users()

        if user['admin_level'] == 'sub_admin' and session.get('admin_level') != 'super_admin':
            conn.close()
            return _redirect_users()

        cursor.execute(
            'UPDATE users SET is_banned=1 WHERE email=?',
            (target_email,)
        )

        conn.commit()
        conn.close()

        log_action(actor, 'user_banned', f'User banned: {target_email}.')
        return _redirect_users()

    except Exception:
        current_app.logger.exception('Ban user failed')
        return _redirect_users()


@admin_bp.route('/unban_user', methods=['POST'])
@admin_required
def unban_user():
    _ensure_users_role_columns()

    target_email = request.form.get('email', '').strip().lower()
    actor = _current_actor()

    try:
        conn = get_conn()
        cursor = conn.cursor()

        user = _get_user_level(cursor, target_email)

        if not user:
            conn.close()
            return _redirect_users()

        if user['admin_level'] == 'sub_admin' and session.get('admin_level') != 'super_admin':
            conn.close()
            return _redirect_users()

        cursor.execute(
            'UPDATE users SET is_banned=0 WHERE email=?',
            (target_email,)
        )

        conn.commit()
        conn.close()

        log_action(actor, 'user_unbanned', f'User unbanned: {target_email}.')
        return _redirect_users()

    except Exception:
        current_app.logger.exception('Unban user failed')
        return _redirect_users()


@admin_bp.route('/delete_user', methods=['POST'])
@admin_required
def delete_user():
    _ensure_users_role_columns()

    target_email = request.form.get('email', '').strip().lower()
    actor = _current_actor()

    try:
        if _is_self_target(target_email):
            return _redirect_users()

        conn = get_conn()
        cursor = conn.cursor()

        user = _get_user_level(cursor, target_email)

        if not user:
            conn.close()
            return _redirect_users()

        if user['admin_level'] == 'super_admin':
            conn.close()
            return _redirect_users()

        if user['admin_level'] == 'sub_admin' and session.get('admin_level') != 'super_admin':
            conn.close()
            return _redirect_users()

        cursor.execute('DELETE FROM tasks WHERE email=?', (target_email,))
        cursor.execute('DELETE FROM profiles WHERE email=?', (target_email,))
        cursor.execute('DELETE FROM audit_logs WHERE email=?', (target_email,))
        cursor.execute('DELETE FROM users WHERE email=?', (target_email,))

        conn.commit()
        conn.close()

        log_action(actor, 'user_deleted', f'Admin removed user {target_email}.')
        return _redirect_users()

    except Exception:
        current_app.logger.exception('Delete user failed')
        return _redirect_users()


@admin_bp.route('/audit_logs')
@admin_required
def audit_logs():
    search = request.args.get('q', '').strip()
    action = request.args.get('action', '').strip()

    try:
        conn = get_conn()
        cursor = conn.cursor()

        sql = 'SELECT email, action, details, created_at FROM audit_logs WHERE 1=1'
        params = []

        if search:
            sql += ' AND (email LIKE ? OR details LIKE ?)'
            like_value = f'%{search}%'
            params.extend([like_value, like_value])

        if action:
            sql += ' AND action=?'
            params.append(action)

        sql += ' ORDER BY id DESC LIMIT 300'

        cursor.execute(sql, params)
        logs = cursor.fetchall()

        cursor.execute('SELECT DISTINCT action FROM audit_logs ORDER BY action ASC')
        actions = cursor.fetchall()

        conn.close()

        return render_template(
            'audit_logs.html',
            logs=logs,
            actions=actions,
            error=None
        )

    except Exception:
        current_app.logger.exception('Audit logs failed')

        return render_template(
            'audit_logs.html',
            logs=[],
            actions=[],
            error='Unable to load audit logs right now.'
        )


@admin_bp.route('/user_login_history/<path:email>')
@admin_required
def user_login_history(email):
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT email, action, details, created_at
            FROM audit_logs
            WHERE email=?
            AND action IN ('login_success','admin_login_success','login_failed','banned_login_blocked')
            ORDER BY id DESC
            LIMIT 100
        """, (email,))

        logs = cursor.fetchall()
        conn.close()

        return render_template(
            'audit_logs.html',
            logs=logs,
            actions=[],
            error=None,
            history_title=f'Login History: {email}'
        )

    except Exception:
        current_app.logger.exception('User login history failed')

        return render_template(
            'audit_logs.html',
            logs=[],
            actions=[],
            error='Unable to load user login history right now.',
            history_title='Login History'
        )


@admin_bp.route('/maintenance')
@admin_required
def admin_maintenance():
    return render_template('admin_maintenance.html')


@admin_bp.route('/reports')
@admin_required
def admin_reports():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT email, action, details, created_at FROM audit_logs ORDER BY id DESC LIMIT 200')
        logs = cursor.fetchall()

        conn.close()

        return render_template('admin_reports.html', logs=logs)

    except Exception:
        current_app.logger.exception('Admin reports failed')
        return render_template('admin_reports.html', logs=[])


@admin_bp.route('/export_users_report')
@admin_required
def export_users_report():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT email, verified, role, function, usage, admin_level, is_banned
            FROM users
            ORDER BY email
        """)

        rows = cursor.fetchall()
        conn.close()

        report_path = 'users_report.csv'

        with open(report_path, 'w', newline='', encoding='utf-8') as file_obj:
            writer = csv.writer(file_obj)

            writer.writerow([
                'Email',
                'Verified',
                'Role',
                'Function',
                'Usage',
                'Admin Level',
                'Is Banned'
            ])

            for row in rows:
                writer.writerow([
                    row['email'],
                    row['verified'],
                    row['role'],
                    row['function'],
                    row['usage'],
                    row['admin_level'],
                    row['is_banned']
                ])

        log_action(_current_actor(), 'report_exported', 'Users report exported.')
        return send_file(report_path, as_attachment=True)

    except Exception:
        current_app.logger.exception('Export report failed')

        return render_template(
            'admin_dashboard.html',
            error='Unable to generate users report right now.'
        )


@admin_bp.route('/export_farm_report')
@admin_required
def export_farm_report():
    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                farms.email,
                farms.farm_name,
                farms.crop_type,
                farms.location,
                farm_readings.soil_moisture,
                farm_readings.ph_level,
                farm_readings.nitrogen,
                farm_readings.phosphorus,
                farm_readings.potassium,
                farm_readings.temperature,
                farm_readings.humidity,
                farm_readings.pest_observation,
                farm_readings.fertilizer_used,
                farm_readings.irrigation_status,
                farm_readings.notes,
                farm_readings.created_at
            FROM farm_readings
            JOIN farms ON farm_readings.farm_id = farms.id
            ORDER BY farm_readings.id DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        report_path = 'admin_farm_report.csv'

        with open(report_path, 'w', newline='', encoding='utf-8') as file_obj:
            writer = csv.writer(file_obj)

            writer.writerow([
                'User Email',
                'Farm Name',
                'Crop Type',
                'Location',
                'Soil Moisture',
                'pH Level',
                'Nitrogen',
                'Phosphorus',
                'Potassium',
                'Temperature',
                'Humidity',
                'Pest Observation',
                'Fertilizer Used',
                'Irrigation Status',
                'Notes',
                'Created At'
            ])

            for row in rows:
                writer.writerow([
                    row['email'],
                    row['farm_name'],
                    row['crop_type'],
                    row['location'],
                    row['soil_moisture'],
                    row['ph_level'],
                    row['nitrogen'],
                    row['phosphorus'],
                    row['potassium'],
                    row['temperature'],
                    row['humidity'],
                    row['pest_observation'],
                    row['fertilizer_used'],
                    row['irrigation_status'],
                    row['notes'],
                    row['created_at']
                ])

        log_action(_current_actor(), 'admin_farm_report_exported', 'Admin farm report exported.')

        return send_file(report_path, as_attachment=True)

    except Exception:
        current_app.logger.exception('Admin farm report export failed')

        return render_template(
            'admin_dashboard.html',
            error='Unable to generate farm report right now.'
        )


@admin_bp.route('/backup_database')
@admin_required
def backup_database():
    try:
        shutil.copyfile(current_app.config['DATABASE'], current_app.config['BACKUP_PATH'])

        log_action(_current_actor(), 'database_backup', 'Database backup downloaded.')

        return send_file(current_app.config['BACKUP_PATH'], as_attachment=True)

    except Exception:
        current_app.logger.exception('Backup database failed')

        return render_template(
            'admin_dashboard.html',
            error='Unable to create backup right now.'
        )