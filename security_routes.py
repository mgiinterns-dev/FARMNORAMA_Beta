from flask import Blueprint, current_app, render_template, request, session

from db import get_conn
from helpers import hash_password, login_required, log_action, verify_password

security_bp = Blueprint('security_bp', __name__)


@security_bp.route('/security_settings')
@login_required
def security_settings():
    return render_template('security_settings.html')


@security_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not current_password or not new_password or not confirm_password:
        return render_template('security_settings.html', error='All fields are required.')

    if len(new_password) < 8:
        return render_template('security_settings.html', error='New password must be at least 8 characters.')

    if new_password != confirm_password:
        return render_template('security_settings.html', error='New passwords do not match.')

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM users WHERE email=?', (session['email'],))
        user = cursor.fetchone()

        if not user or not verify_password(user['password'], current_password):
            conn.close()
            return render_template('security_settings.html', error='Current password is incorrect.')

        cursor.execute('UPDATE users SET password=? WHERE email=?', (hash_password(new_password), session['email']))
        conn.commit()
        conn.close()
        log_action(session['email'], 'password_changed', 'Password updated from Security Settings.')
        return render_template('security_settings.html', success='Password changed successfully.')
    except Exception:
        current_app.logger.exception('Change password failed')
        return render_template('security_settings.html', error='Unable to update password right now.')
