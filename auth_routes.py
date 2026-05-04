from datetime import datetime, timedelta

from flask import Blueprint, current_app, redirect, render_template, request, session
from werkzeug.security import generate_password_hash

from db import get_conn
from helpers import log_action, make_expiry, make_otp, send_otp_email

auth_bp = Blueprint('auth_bp', __name__)

MAX_ADMIN_FAILED_ATTEMPTS = 5
ADMIN_LOCK_MINUTES = 10


def _verify_password(stored_password: str, entered_password: str) -> bool:
    if not stored_password:
        return False
    try:
        from werkzeug.security import check_password_hash
        if stored_password.startswith('pbkdf2:') or stored_password.startswith('scrypt:'):
            return check_password_hash(stored_password, entered_password)
    except Exception:
        pass
    return stored_password == entered_password


def _clear_admin_security_session():
    for key in ('admin_pending_email', 'admin_login_stage', 'admin_login_failed_attempts', 'admin_login_locked_until', 'admin_last_activity'):
        session.pop(key, None)


def _is_admin_locked():
    locked_until = session.get('admin_login_locked_until')
    if not locked_until:
        return False
    try:
        locked_dt = datetime.fromisoformat(locked_until)
    except Exception:
        session.pop('admin_login_locked_until', None)
        return False
    if datetime.now() >= locked_dt:
        session.pop('admin_login_locked_until', None)
        session.pop('admin_login_failed_attempts', None)
        return False
    return True


def _register_admin_failed_attempt(email: str):
    attempts = int(session.get('admin_login_failed_attempts', 0)) + 1
    session['admin_login_failed_attempts'] = attempts
    if attempts >= MAX_ADMIN_FAILED_ATTEMPTS:
        session['admin_login_locked_until'] = (datetime.now() + timedelta(minutes=ADMIN_LOCK_MINUTES)).isoformat()
        log_action(email, 'admin_login_locked', f'Admin login locked for {ADMIN_LOCK_MINUTES} minutes.')
        return True
    return False


def _load_user_by_email(email: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email=?', (email,))
    user = cursor.fetchone()
    conn.close()
    return user


def _begin_admin_otp_flow(email: str):
    otp = make_otp()
    expiry = make_expiry()

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET otp=?, otp_expiry=? WHERE email=?', (otp, expiry, email))
    conn.commit()
    conn.close()

    if not send_otp_email(email, otp):
        log_action(email, 'admin_login_otp_failed', 'Admin OTP email failed to send.')
        return False

    session['admin_pending_email'] = email
    session['admin_login_stage'] = 'otp'
    session['admin_last_activity'] = datetime.now().isoformat()
    log_action(email, 'admin_login_password_verified', 'Admin password accepted, OTP sent.')
    return True


@auth_bp.route('/')
@auth_bp.route('/login')
def login():
    if 'email' in session:
        if session.get('admin_level') in ('super_admin', 'sub_admin') or session.get('is_admin') == 1:
            return redirect('/admin/dashboard')
        return redirect('/dashboard')
    return render_template('login.html')


@auth_bp.route('/login_user', methods=['POST'])
def login_user():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    try:
        user = _load_user_by_email(email)
        if not user or not _verify_password(user['password'], password):
            log_action(email or 'unknown', 'login_failed', 'Invalid login attempt.')
            return render_template('login.html', error='Wrong credentials!')

        if 'is_banned' in user.keys() and user['is_banned'] == 1:
            log_action(email, 'banned_login_blocked', 'Banned user tried to log in.')
            return render_template('login.html', error='This account has been suspended.')

        admin_level = user['admin_level'] if 'admin_level' in user.keys() else ('sub_admin' if user['is_admin'] == 1 else 'user')
        if admin_level in ('super_admin', 'sub_admin') or user['is_admin'] == 1:
            if _is_admin_locked():
                return render_template('login.html', error='Admin login temporarily locked. Try again in a few minutes.')
            if not _begin_admin_otp_flow(email):
                return render_template('login.html', error='Unable to send admin OTP right now.')
            return redirect('/admin/verify')

        session['email'] = user['email']
        session['is_admin'] = 0
        session['admin_level'] = 'user'
        log_action(email, 'login_success', 'User logged in successfully.')

        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM profiles WHERE email=?', (email,))
        profile = cursor.fetchone()
        conn.close()
        return redirect('/dashboard' if profile else '/create_profile')
    except Exception:
        current_app.logger.exception('Login failed')
        return render_template('login.html', error='Something went wrong while logging in.')


@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        if 'email' in session and (session.get('admin_level') in ('super_admin', 'sub_admin') or session.get('is_admin') == 1):
            return redirect('/admin/dashboard')
        return render_template('admin_login.html')

    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    try:
        user = _load_user_by_email(email)
        if not user or not _verify_password(user['password'], password):
            log_action(email or 'unknown', 'admin_login_failed', 'Invalid admin login attempt.')
            return render_template('admin_login.html', error='Wrong credentials!')

        admin_level = user['admin_level'] if 'admin_level' in user.keys() else ('sub_admin' if user['is_admin'] == 1 else 'user')
        if admin_level not in ('super_admin', 'sub_admin') and user['is_admin'] != 1:
            return render_template('admin_login.html', error='This account is not an admin account.')

        if 'is_banned' in user.keys() and user['is_banned'] == 1:
            return render_template('admin_login.html', error='This admin account has been suspended.')

        if _is_admin_locked():
            return render_template('admin_login.html', error='Admin login temporarily locked. Try again later.')

        if not _begin_admin_otp_flow(email):
            return render_template('admin_login.html', error='Unable to send admin OTP right now.')
        return redirect('/admin/verify')
    except Exception:
        current_app.logger.exception('Admin login failed')
        return render_template('admin_login.html', error='Something went wrong while logging in.')


@auth_bp.route('/admin/verify')
def admin_verify():
    if session.get('admin_login_stage') != 'otp' or not session.get('admin_pending_email'):
        return redirect('/')
    return render_template('admin_otp.html')


@auth_bp.route('/admin/verify_otp', methods=['POST'])
def admin_verify_otp():
    pending_email = session.get('admin_pending_email')
    entered_otp = request.form.get('otp', '').strip()
    if not pending_email or session.get('admin_login_stage') != 'otp':
        return redirect('/')

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT otp, otp_expiry, is_admin, admin_level, is_banned FROM users WHERE email=?', (pending_email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            _clear_admin_security_session()
            return redirect('/')
        if ('admin_level' in user.keys() and user['admin_level'] not in ('super_admin', 'sub_admin')) and user['is_admin'] != 1:
            _clear_admin_security_session()
            return redirect('/')
        if 'is_banned' in user.keys() and user['is_banned'] == 1:
            _clear_admin_security_session()
            return render_template('admin_login.html', error='This admin account has been suspended.')

        if not user['otp'] or entered_otp != user['otp']:
            locked = _register_admin_failed_attempt(pending_email)
            log_action(pending_email, 'admin_otp_failed', 'Incorrect admin OTP entered.')
            if locked:
                return render_template('admin_otp.html', error='Too many failed attempts. Admin login is temporarily locked.')
            return render_template('admin_otp.html', error='Invalid OTP.')

        try:
            expiry = datetime.strptime(user['otp_expiry'], '%Y-%m-%d %H:%M:%S')
        except Exception:
            expiry = None
        if not expiry or datetime.now() > expiry:
            log_action(pending_email, 'admin_otp_expired', 'Expired admin OTP used.')
            return render_template('admin_otp.html', error='OTP expired.')

        session['email'] = pending_email
        session['is_admin'] = 1
        session['admin_level'] = user['admin_level'] if 'admin_level' in user.keys() and user['admin_level'] else 'sub_admin'
        session['admin_last_activity'] = datetime.now().isoformat()
        session.pop('admin_login_failed_attempts', None)
        session.pop('admin_login_locked_until', None)
        session.pop('admin_pending_email', None)
        session.pop('admin_login_stage', None)
        log_action(session['email'], 'admin_login_success', 'Admin logged in with OTP.')
        return redirect('/admin/dashboard')
    except Exception:
        current_app.logger.exception('Admin OTP verification failed')
        return render_template('admin_otp.html', error='Unable to verify admin OTP right now.')


@auth_bp.route('/admin/resend_otp')
def admin_resend_otp():
    pending_email = session.get('admin_pending_email')
    if not pending_email or session.get('admin_login_stage') != 'otp':
        return redirect('/')
    if _is_admin_locked():
        return render_template('admin_otp.html', error='Admin login temporarily locked. Try again later.')
    try:
        if not _begin_admin_otp_flow(pending_email):
            return render_template('admin_otp.html', error='Unable to resend admin OTP right now.')
        return render_template('admin_otp.html', message='A new OTP has been sent to your email.')
    except Exception:
        current_app.logger.exception('Admin OTP resend failed')
        return render_template('admin_otp.html', error='Unable to resend admin OTP right now.')


@auth_bp.route('/logout')
def logout():
    try:
        if session.get('email'):
            action = 'admin_logout' if session.get('admin_level') in ('super_admin', 'sub_admin') or session.get('is_admin') == 1 else 'logout'
            log_action(session['email'], action, 'User logged out.')
    except Exception:
        current_app.logger.exception('Logout log failed')
    session.clear()
    return redirect('/')


@auth_bp.route('/signup')
def signup():
    return render_template('signup.html')


@auth_bp.route('/create_account', methods=['POST'])
def create_account():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')

    if not email or '@' not in email or '.' not in email:
        return render_template('signup.html', error='Invalid email format')

    if len(password) < 8:
        return render_template('signup.html', error='Password must be at least 8 characters')

    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE email=?', (email,))
        if cursor.fetchone():
            conn.close()
            return render_template('signup.html', error='exists')

        otp = make_otp()
        expiry = make_expiry()

        cursor.execute(
            "INSERT INTO users (email, password, otp, otp_expiry, verified, is_admin, admin_level, is_banned) VALUES (?, ?, ?, ?, 0, 0, 'user', 0)",
            (email, generate_password_hash(password), otp, expiry)
        )

        conn.commit()
        conn.close()

        if not send_otp_email(email, otp):
            current_app.logger.warning('Signup OTP email failed to send.')

        session['pending_email'] = email
        log_action(email, 'signup_otp_sent', 'Signup OTP sent.')
        return redirect('/verify_otp')

    except Exception:
        current_app.logger.exception('Signup failed')
        return render_template('signup.html', error='Unable to create account right now.')


@auth_bp.route('/verify_otp')
def verify_otp_page():
    if not session.get('pending_email'):
        return redirect('/signup')
    return render_template('verify_otp.html')


@auth_bp.route('/verify_otp', methods=['POST'])
def verify_otp():
    email = session.get('pending_email')
    entered = request.form.get('otp', '').strip()
    if not email:
        return redirect('/signup')
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT otp, otp_expiry FROM users WHERE email=?', (email,))
        user = cursor.fetchone()
        if not user or entered != user['otp']:
            conn.close()
            return render_template('verify_otp.html', error='Invalid OTP')
        try:
            expiry = datetime.strptime(user['otp_expiry'], '%Y-%m-%d %H:%M:%S')
        except Exception:
            expiry = None
        if not expiry or datetime.now() > expiry:
            conn.close()
            return render_template('verify_otp.html', error='OTP expired')
        cursor.execute('UPDATE users SET verified=1 WHERE email=?', (email,))
        conn.commit()
        conn.close()
        session.pop('pending_email', None)
        session['email'] = email
        session['is_admin'] = 0
        session['admin_level'] = 'user'
        log_action(email, 'signup_verified', 'User verified signup OTP.')
        return redirect('/work_info')
    except Exception:
        current_app.logger.exception('OTP verify failed')
        return render_template('verify_otp.html', error='Server error')


@auth_bp.route('/resend_otp')
def resend_otp():
    email = session.get('pending_email')
    if not email:
        return redirect('/signup')
    try:
        otp = make_otp()
        expiry = make_expiry()
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET otp=?, otp_expiry=? WHERE email=?', (otp, expiry, email))
        conn.commit()
        conn.close()
        send_otp_email(email, otp)
        log_action(email, 'signup_otp_resent', 'Signup OTP resent.')
        return render_template('verify_otp.html', message='OTP resent')
    except Exception:
        current_app.logger.exception('Resend OTP failed')
        return render_template('verify_otp.html', error='Failed to resend OTP')


@auth_bp.route('/forgot')
def forgot():
    return render_template('forgot.html')


@auth_bp.route('/forgot_password', methods=['POST'])
def forgot_password():
    email = request.form.get('email', '').strip().lower()
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email=?', (email,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return render_template('forgot.html', message='Email not found.')
        otp = make_otp()
        expiry = make_expiry()
        cursor.execute('UPDATE users SET otp=?, otp_expiry=? WHERE email=?', (otp, expiry, email))
        conn.commit()
        conn.close()
        send_otp_email(email, otp)
        session['reset_email'] = email
        log_action(email, 'forgot_password_otp_sent', 'Password reset OTP sent.')
        return redirect('/reset_password')
    except Exception:
        current_app.logger.exception('Forgot password failed')
        return render_template('forgot.html', message='Unable to process password reset right now.')


@auth_bp.route('/reset_password')
def reset_password_page():
    if not session.get('reset_email'):
        return redirect('/forgot')
    return render_template('reset_password.html')


@auth_bp.route('/reset_password_submit', methods=['POST'])
def reset_password_submit():
    email = session.get('reset_email')
    otp = request.form.get('otp', '').strip()
    password = request.form.get('password', '').strip()
    if not email:
        return redirect('/forgot')
    if len(password) < 8:
        return render_template('reset_password.html', error='Password must be at least 8 characters.')
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT otp, otp_expiry FROM users WHERE email=?', (email,))
        user = cursor.fetchone()
        if not user or otp != user['otp']:
            conn.close()
            return render_template('reset_password.html', error='Invalid OTP.')
        try:
            expiry = datetime.strptime(user['otp_expiry'], '%Y-%m-%d %H:%M:%S')
        except Exception:
            expiry = None
        if not expiry or datetime.now() > expiry:
            conn.close()
            return render_template('reset_password.html', error='OTP expired.')
        cursor.execute('UPDATE users SET password=?, otp=NULL, otp_expiry=NULL WHERE email=?', (generate_password_hash(password), email))
        conn.commit()
        conn.close()
        session.pop('reset_email', None)
        log_action(email, 'password_reset_success', 'Password reset completed.')
        return redirect('/')
    except Exception:
        current_app.logger.exception('Reset password failed')
        return render_template('reset_password.html', error='Unable to reset password right now.')
