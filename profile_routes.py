from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session

from db import get_conn
from helpers import json_error, login_required, log_action, save_uploaded_photo, verify_password

profile_bp = Blueprint('profile_bp', __name__)


def _load_profile_by_email(email):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM profiles WHERE email=?', (email,))
    profile_data = cursor.fetchone()
    conn.close()
    return profile_data


@profile_bp.route('/work_info')
@login_required
def work_info():
    return render_template('work_info.html')


@profile_bp.route('/save_work', methods=['POST'])
@login_required
def save_work():
    role = request.form.get('role')
    function_name = request.form.get('function')
    usage = request.form.get('usage')

    if role == 'Other':
        role = request.form.get('role_other')
    if function_name == 'Other':
        function_name = request.form.get('function_other')
    if usage == 'Other':
        usage = request.form.get('usage_other')

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE users SET role=?, function=?, usage=? WHERE email=?',
            (role, function_name, usage, session['email'])
        )
        conn.commit()
        conn.close()
        return redirect('/create_profile')
    except Exception:
        current_app.logger.exception('Save work info failed')
        return render_template('work_info.html', error='Unable to save work information right now.')


@profile_bp.route('/create_profile')
@login_required
def create_profile():
    return render_template('create_profile.html')


@profile_bp.route('/save_profile', methods=['POST'])
@login_required
def save_profile():
    position = request.form.get('position')
    if position == 'Other':
        position = request.form.get('position_other')

    phone = (request.form.get('phone') or '').strip()
    age = (request.form.get('age') or '').strip()

    if phone and not phone.replace('+', '').isdigit():
        return render_template('create_profile.html', error='Phone number must contain digits only.')

    try:
        age_value = int(age)
        if age_value < 1 or age_value > 120:
            return render_template('create_profile.html', error='Age must be between 1 and 120.')
    except Exception:
        return render_template('create_profile.html', error='Age must be a valid number.')

    photo_file = request.files.get('photo')
    new_photo = save_uploaded_photo(photo_file) if photo_file else None

    try:
        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM profiles WHERE email=?', (session['email'],))
        existing = cursor.fetchone()

        final_photo = new_photo if new_photo else (existing['photo'] if existing else None)

        values = (
            request.form.get('fullname'),
            phone,
            age_value,
            request.form.get('address'),
            request.form.get('bio'),
            request.form.get('company'),
            position,
            request.form.get('website'),
            request.form.get('gender'),
            final_photo,
            session['email'],
        )

        if existing:
            cursor.execute(
                '''
                UPDATE profiles
                SET fullname=?, phone=?, age=?, address=?, bio=?, company=?, position=?, website=?, gender=?, photo=?
                WHERE email=?
                ''',
                values,
            )
        else:
            cursor.execute(
                '''
                INSERT INTO profiles (
                    fullname, phone, age, address, bio, company, position, website, gender, photo, email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                values,
            )

        conn.commit()
        conn.close()
        log_action(session['email'], 'profile_created', 'User created profile.')
        return redirect('/dashboard')
    except Exception:
        current_app.logger.exception('Save profile failed')
        return render_template('create_profile.html', error='Unable to save profile right now.')


@profile_bp.route('/profile')
@login_required
def profile():
    try:
        return render_template('profile.html', profile=_load_profile_by_email(session['email']))
    except Exception:
        current_app.logger.exception('Load profile failed')
        return render_template('profile.html', profile=None, error='Unable to load profile.')


@profile_bp.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    position = request.form.get('position')
    if position == 'Other':
        position = request.form.get('position_other')

    phone = (request.form.get('phone') or '').strip()
    age = (request.form.get('age') or '').strip()

    if phone and not phone.replace('+', '').isdigit():
        return render_template(
            'profile.html',
            profile=_load_profile_by_email(session['email']),
            error='Phone number must contain digits only.'
        )

    try:
        age_value = int(age)
        if age_value < 1 or age_value > 120:
            return render_template(
                'profile.html',
                profile=_load_profile_by_email(session['email']),
                error='Age must be between 1 and 120.'
            )
    except Exception:
        return render_template(
            'profile.html',
            profile=_load_profile_by_email(session['email']),
            error='Age must be a valid number.'
        )

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM profiles WHERE email=?', (session['email'],))
        existing = cursor.fetchone()

        current_photo = existing['photo'] if existing else None
        photo_file = request.files.get('photo')
        new_photo = save_uploaded_photo(photo_file) if photo_file else None
        final_photo = new_photo if new_photo else current_photo

        values = (
            request.form.get('fullname'),
            phone,
            age_value,
            request.form.get('address'),
            request.form.get('bio'),
            request.form.get('company'),
            position,
            request.form.get('website'),
            request.form.get('gender'),
            final_photo,
            session['email'],
        )

        if existing:
            cursor.execute(
                '''
                UPDATE profiles
                SET fullname=?, phone=?, age=?, address=?, bio=?, company=?, position=?, website=?, gender=?, photo=?
                WHERE email=?
                ''',
                values,
            )
        else:
            cursor.execute(
                '''
                INSERT INTO profiles (
                    fullname, phone, age, address, bio, company, position, website, gender, photo, email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                values,
            )

        conn.commit()
        conn.close()
        log_action(session['email'], 'profile_updated', 'User updated profile.')
        return redirect('/profile')
    except Exception:
        current_app.logger.exception('Update profile failed')
        return render_template(
            'profile.html',
            profile=_load_profile_by_email(session['email']),
            error='Unable to update profile.'
        )


@profile_bp.route('/activity')
@login_required
def activity():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT action, details, created_at FROM audit_logs WHERE email=? ORDER BY id DESC LIMIT 30',
            (session['email'],)
        )
        logs = cursor.fetchall()
        conn.close()
        return render_template('activity.html', logs=logs)
    except Exception:
        current_app.logger.exception('Load activity failed')
        return render_template('activity.html', logs=[])


@profile_bp.route('/get_email')
@login_required
def get_email():
    return jsonify({'email': session.get('email')})


@profile_bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    password = request.form.get('password', '').strip()
    email = session['email']
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email=?', (email,))
        user = cursor.fetchone()

        if not user or not verify_password(user['password'], password):
            conn.close()
            return jsonify({'status': 'wrong_password'})

        log_action(email, 'account_deleted', 'User account was permanently deleted.')
        cursor.execute('DELETE FROM tasks WHERE email=?', (email,))
        cursor.execute('DELETE FROM profiles WHERE email=?', (email,))
        cursor.execute('DELETE FROM users WHERE email=?', (email,))
        conn.commit()
        conn.close()
        session.clear()
        return jsonify({'status': 'deleted'})
    except Exception:
        current_app.logger.exception('Delete account failed')
        return json_error('Server error.', status=500)