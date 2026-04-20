from datetime import datetime, timedelta
from functools import wraps
import os
import random
import smtplib
from email.mime.text import MIMEText

from flask import current_app, jsonify, redirect, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import get_conn


def make_otp():
    return str(random.randint(100000, 999999))


def make_expiry(minutes=5):
    return (datetime.now() + timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def send_otp_email(receiver_email, otp):
    sender_email = current_app.config.get('MAIL_USERNAME')
    sender_password = current_app.config.get('MAIL_PASSWORD')

    if not sender_email or not sender_password:
        current_app.logger.error('Missing MAIL_USERNAME or MAIL_PASSWORD in config')
        return False

    msg = MIMEText(f'Your Farmnorama OTP is: {otp}')
    msg['Subject'] = 'Farmnorama OTP'
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception:
        current_app.logger.exception('Failed to send OTP email')
        return False


def json_error(message, status=400):
    response = jsonify({'status': 'error', 'message': message})
    response.status_code = status
    return response


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('email'):
            return redirect('/')
        return view_func(*args, **kwargs)
    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('email'):
            return redirect('/')

        if session.get('admin_level') not in ('super_admin', 'sub_admin') and session.get('is_admin') != 1:
            return redirect('/dashboard')

        idle_limit_minutes = 15
        last_active = session.get('admin_last_activity')
        if last_active:
            try:
                last_dt = datetime.fromisoformat(last_active)
                if datetime.now() - last_dt > timedelta(minutes=idle_limit_minutes):
                    try:
                        log_action(session.get('email', 'admin'), 'admin_session_timeout', 'Admin session expired due to inactivity.')
                    except Exception:
                        pass
                    session.clear()
                    return redirect('/')
            except Exception:
                pass

        session['admin_last_activity'] = datetime.now().isoformat()
        return view_func(*args, **kwargs)
    return wrapper


def hash_password(password):
    if not password:
        return ''
    return generate_password_hash(password)


def verify_password(stored_password, entered_password):
    if not stored_password:
        return False

    try:
        if str(stored_password).startswith('pbkdf2:') or str(stored_password).startswith('scrypt:'):
            return check_password_hash(stored_password, entered_password)
    except Exception:
        pass

    return stored_password == entered_password


def save_uploaded_photo(file_storage):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None

    upload_folder = current_app.config.get(
        'UPLOAD_FOLDER',
        os.path.join(current_app.root_path, 'static', 'uploads')
    )
    os.makedirs(upload_folder, exist_ok=True)

    name, ext = os.path.splitext(filename)
    unique_name = f"{name}_{int(datetime.now().timestamp())}{ext}"
    save_path = os.path.join(upload_folder, unique_name)
    file_storage.save(save_path)
    return unique_name


def log_action(email, action, details=''):
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (email, action, details, created_at) VALUES (?, ?, ?, ?)",
            (email, action, details, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
    except Exception:
        current_app.logger.exception('Audit log write failed')


def super_admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('email'):
            return redirect('/')
        if session.get('admin_level') != 'super_admin':
            return redirect('/admin/dashboard')
        return view_func(*args, **kwargs)
    return wrapper
