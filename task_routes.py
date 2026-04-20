from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session

from db import get_conn
from helpers import json_error, login_required, log_action

task_bp = Blueprint('task_bp', __name__)


@task_bp.route('/dashboard')
@login_required
def dashboard():
    if session.get('admin_level') in ('super_admin', 'sub_admin') or session.get('is_admin') == 1:
        return redirect('/admin/dashboard')
    return render_template('dashboard.html')


@task_bp.route('/get_tasks')
@login_required
def get_tasks():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE email=? ORDER BY id DESC', (session['email'],))
        tasks = cursor.fetchall()
        conn.close()
        return jsonify({'tasks': [tuple(row) for row in tasks]})
    except Exception:
        current_app.logger.exception('Get tasks failed')
        return jsonify({'tasks': []})


@task_bp.route('/add_task', methods=['POST'])
@login_required
def add_task():
    title = request.form.get('title', '').strip()
    priority = request.form.get('priority', 'Low').strip()
    due_date = request.form.get('due_date', '').strip()

    if not title:
        return json_error('Task title is required.')

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO tasks (email, title, status, priority, due_date) VALUES (?, ?, ?, ?, ?)',
            (session['email'], title, 'To do', priority, due_date),
        )
        conn.commit()
        conn.close()
        log_action(session['email'], 'task_added', f'Task added: {title}')
        return jsonify({'status': 'success'})
    except Exception:
        current_app.logger.exception('Add task failed')
        return json_error('Unable to add task.', status=500)


@task_bp.route('/update_task', methods=['POST'])
@login_required
def update_task():
    task_id = request.form.get('id')
    status = request.form.get('status')

    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET status=? WHERE id=? AND email=?', (status, task_id, session['email']))
        conn.commit()
        conn.close()
        log_action(session['email'], 'task_status_updated', f'Task #{task_id} moved to {status}')
        return jsonify({'status': 'updated'})
    except Exception:
        current_app.logger.exception('Update task failed')
        return json_error('Unable to update task.', status=500)


@task_bp.route('/edit_task', methods=['POST'])
@login_required
def edit_task():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE tasks SET title=?, priority=?, due_date=? WHERE id=? AND email=?',
            (
                request.form.get('title'),
                request.form.get('priority'),
                request.form.get('due_date'),
                request.form.get('id'),
                session['email'],
            ),
        )
        conn.commit()
        conn.close()
        log_action(session['email'], 'task_edited', f'Task updated: {request.form.get('title', '').strip()}')
        return jsonify({'status': 'edited'})
    except Exception:
        current_app.logger.exception('Edit task failed')
        return json_error('Unable to edit task.', status=500)


@task_bp.route('/delete_task', methods=['POST'])
@login_required
def delete_task():
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE id=? AND email=?', (request.form.get('id'), session['email']))
        conn.commit()
        conn.close()
        log_action(session['email'], 'task_deleted', f'Task deleted: #{request.form.get('id')}')
        return jsonify({'status': 'deleted'})
    except Exception:
        current_app.logger.exception('Delete task failed')
        return json_error('Unable to delete task.', status=500)
