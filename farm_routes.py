import csv
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, session, send_file, jsonify

from db import get_conn
from helpers import log_action


farm_bp = Blueprint('farm', __name__)


def login_required():
    return 'email' in session


@farm_bp.route('/farms')
def farms():
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE email = ?
        ORDER BY id DESC
    """, (session['email'],))

    farms = cursor.fetchall()
    conn.close()

    return render_template('farms.html', farms=farms)


@farm_bp.route('/farms/add', methods=['GET', 'POST'])
def add_farm():
    if not login_required():
        return redirect('/login')

    if request.method == 'POST':
        farm_name = request.form.get('farm_name', '').strip()
        location = request.form.get('location', '').strip()
        farm_size = request.form.get('farm_size', '').strip()
        crop_type = request.form.get('crop_type', '').strip()
        planting_date = request.form.get('planting_date', '').strip()
        expected_harvest_date = request.form.get('expected_harvest_date', '').strip()

        if not farm_name:
            return render_template('add_farm.html', error='Farm name is required.')

        conn = get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO farms (
                email,
                farm_name,
                location,
                farm_size,
                crop_type,
                planting_date,
                expected_harvest_date,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session['email'],
            farm_name,
            location,
            farm_size,
            crop_type,
            planting_date,
            expected_harvest_date,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

        conn.commit()
        conn.close()

        log_action(session['email'], 'farm_added', f'Farm added: {farm_name}')

        return redirect('/farms')

    return render_template('add_farm.html')


@farm_bp.route('/farms/<int:farm_id>')
def farm_detail(farm_id):
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE id = ? AND email = ?
    """, (farm_id, session['email']))

    farm = cursor.fetchone()

    if not farm:
        conn.close()
        return redirect('/farms')

    cursor.execute("""
        SELECT *
        FROM farm_readings
        WHERE farm_id = ?
        ORDER BY id DESC
    """, (farm_id,))
    readings = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM recommendations
        WHERE farm_id = ?
        ORDER BY id DESC
    """, (farm_id,))
    recommendations = cursor.fetchall()

    conn.close()

    return render_template(
        'farm_detail.html',
        farm=farm,
        readings=readings,
        recommendations=recommendations
    )


@farm_bp.route('/farms/<int:farm_id>/edit', methods=['GET', 'POST'])
def edit_farm(farm_id):
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE id = ? AND email = ?
    """, (farm_id, session['email']))

    farm = cursor.fetchone()

    if not farm:
        conn.close()
        return redirect('/farms')

    if request.method == 'POST':
        farm_name = request.form.get('farm_name', '').strip()
        location = request.form.get('location', '').strip()
        farm_size = request.form.get('farm_size', '').strip()
        crop_type = request.form.get('crop_type', '').strip()
        planting_date = request.form.get('planting_date', '').strip()
        expected_harvest_date = request.form.get('expected_harvest_date', '').strip()

        if not farm_name:
            conn.close()
            return render_template(
                'edit_farm.html',
                farm=farm,
                error='Farm name is required.'
            )

        cursor.execute("""
            UPDATE farms
            SET farm_name = ?,
                location = ?,
                farm_size = ?,
                crop_type = ?,
                planting_date = ?,
                expected_harvest_date = ?
            WHERE id = ? AND email = ?
        """, (
            farm_name,
            location,
            farm_size,
            crop_type,
            planting_date,
            expected_harvest_date,
            farm_id,
            session['email']
        ))

        conn.commit()
        conn.close()

        log_action(session['email'], 'farm_updated', f'Farm updated: {farm_name}')

        return redirect(f'/farms/{farm_id}')

    conn.close()

    return render_template('edit_farm.html', farm=farm)


@farm_bp.route('/farms/<int:farm_id>/delete', methods=['POST'])
def delete_farm(farm_id):
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE id = ? AND email = ?
    """, (farm_id, session['email']))

    farm = cursor.fetchone()

    if not farm:
        conn.close()
        return redirect('/farms')

    farm_name = farm['farm_name']

    cursor.execute("DELETE FROM recommendations WHERE farm_id = ?", (farm_id,))
    cursor.execute("DELETE FROM farm_readings WHERE farm_id = ?", (farm_id,))
    cursor.execute("DELETE FROM farms WHERE id = ? AND email = ?", (farm_id, session['email']))

    conn.commit()
    conn.close()

    log_action(session['email'], 'farm_deleted', f'Farm deleted: {farm_name}')

    return redirect('/farms')


@farm_bp.route('/farms/<int:farm_id>/readings/add', methods=['GET', 'POST'])
def add_reading(farm_id):
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE id = ? AND email = ?
    """, (farm_id, session['email']))

    farm = cursor.fetchone()

    if not farm:
        conn.close()
        return redirect('/farms')

    if request.method == 'POST':
        soil_moisture = request.form.get('soil_moisture') or None
        ph_level = request.form.get('ph_level') or None
        nitrogen = request.form.get('nitrogen') or None
        phosphorus = request.form.get('phosphorus') or None
        potassium = request.form.get('potassium') or None
        temperature = request.form.get('temperature') or None
        humidity = request.form.get('humidity') or None
        pest_observation = request.form.get('pest_observation', '').strip()
        fertilizer_used = request.form.get('fertilizer_used', '').strip()
        irrigation_status = request.form.get('irrigation_status', '').strip()
        notes = request.form.get('notes', '').strip()

        cursor.execute("""
            INSERT INTO farm_readings (
                farm_id,
                soil_moisture,
                ph_level,
                nitrogen,
                phosphorus,
                potassium,
                temperature,
                humidity,
                pest_observation,
                fertilizer_used,
                irrigation_status,
                notes,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            farm_id,
            soil_moisture,
            ph_level,
            nitrogen,
            phosphorus,
            potassium,
            temperature,
            humidity,
            pest_observation,
            fertilizer_used,
            irrigation_status,
            notes,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

        reading_id = cursor.lastrowid

        generated_recommendations = generate_recommendations(
            soil_moisture=soil_moisture,
            ph_level=ph_level,
            nitrogen=nitrogen,
            phosphorus=phosphorus,
            potassium=potassium,
            temperature=temperature,
            humidity=humidity,
            pest_observation=pest_observation
        )

        high_alert_messages = []

        for recommendation in generated_recommendations:
            cursor.execute("""
                INSERT INTO recommendations (
                    farm_id,
                    reading_id,
                    recommendation_type,
                    message,
                    severity,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                farm_id,
                reading_id,
                recommendation['type'],
                recommendation['message'],
                recommendation['severity'],
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            if recommendation['severity'] == 'High':
                high_alert_messages.append(
                    f"{recommendation['type']}: {recommendation['message']}"
                )

        conn.commit()
        conn.close()

        for alert_message in high_alert_messages:
            create_notification(
                session['email'],
                f'High Farm Alert: {farm["farm_name"]}',
                alert_message
            )

        log_action(session['email'], 'farm_reading_added', f'Reading added for farm: {farm["farm_name"]}')

        return redirect(f'/farms/{farm_id}')

    conn.close()
    return render_template('add_reading.html', farm=farm)


@farm_bp.route('/farms/<int:farm_id>/readings/<int:reading_id>/edit', methods=['GET', 'POST'])
def edit_reading(farm_id, reading_id):
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE id = ? AND email = ?
    """, (farm_id, session['email']))
    farm = cursor.fetchone()

    if not farm:
        conn.close()
        return redirect('/farms')

    cursor.execute("""
        SELECT *
        FROM farm_readings
        WHERE id = ? AND farm_id = ?
    """, (reading_id, farm_id))
    reading = cursor.fetchone()

    if not reading:
        conn.close()
        return redirect(f'/farms/{farm_id}')

    if request.method == 'POST':
        soil_moisture = request.form.get('soil_moisture') or None
        ph_level = request.form.get('ph_level') or None
        nitrogen = request.form.get('nitrogen') or None
        phosphorus = request.form.get('phosphorus') or None
        potassium = request.form.get('potassium') or None
        temperature = request.form.get('temperature') or None
        humidity = request.form.get('humidity') or None
        pest_observation = request.form.get('pest_observation', '').strip()
        fertilizer_used = request.form.get('fertilizer_used', '').strip()
        irrigation_status = request.form.get('irrigation_status', '').strip()
        notes = request.form.get('notes', '').strip()

        cursor.execute("""
            UPDATE farm_readings
            SET soil_moisture = ?,
                ph_level = ?,
                nitrogen = ?,
                phosphorus = ?,
                potassium = ?,
                temperature = ?,
                humidity = ?,
                pest_observation = ?,
                fertilizer_used = ?,
                irrigation_status = ?,
                notes = ?
            WHERE id = ? AND farm_id = ?
        """, (
            soil_moisture,
            ph_level,
            nitrogen,
            phosphorus,
            potassium,
            temperature,
            humidity,
            pest_observation,
            fertilizer_used,
            irrigation_status,
            notes,
            reading_id,
            farm_id
        ))

        cursor.execute("DELETE FROM recommendations WHERE reading_id = ?", (reading_id,))

        generated_recommendations = generate_recommendations(
            soil_moisture=soil_moisture,
            ph_level=ph_level,
            nitrogen=nitrogen,
            phosphorus=phosphorus,
            potassium=potassium,
            temperature=temperature,
            humidity=humidity,
            pest_observation=pest_observation
        )

        high_alert_messages = []

        for recommendation in generated_recommendations:
            cursor.execute("""
                INSERT INTO recommendations (
                    farm_id,
                    reading_id,
                    recommendation_type,
                    message,
                    severity,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                farm_id,
                reading_id,
                recommendation['type'],
                recommendation['message'],
                recommendation['severity'],
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))

            if recommendation['severity'] == 'High':
                high_alert_messages.append(
                    f"{recommendation['type']}: {recommendation['message']}"
                )

        conn.commit()
        conn.close()

        for alert_message in high_alert_messages:
            create_notification(
                session['email'],
                f'High Farm Alert: {farm["farm_name"]}',
                alert_message
            )

        log_action(session['email'], 'farm_reading_updated', f'Reading updated for farm: {farm["farm_name"]}')

        return redirect(f'/farms/{farm_id}')

    conn.close()

    return render_template('edit_reading.html', farm=farm, reading=reading)


@farm_bp.route('/farms/<int:farm_id>/readings/<int:reading_id>/delete', methods=['POST'])
def delete_reading(farm_id, reading_id):
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM farms
        WHERE id = ? AND email = ?
    """, (farm_id, session['email']))
    farm = cursor.fetchone()

    if not farm:
        conn.close()
        return redirect('/farms')

    cursor.execute("DELETE FROM recommendations WHERE reading_id = ?", (reading_id,))
    cursor.execute("DELETE FROM farm_readings WHERE id = ? AND farm_id = ?", (reading_id, farm_id))

    conn.commit()
    conn.close()

    log_action(session['email'], 'farm_reading_deleted', f'Reading deleted for farm: {farm["farm_name"]}')

    return redirect(f'/farms/{farm_id}')


@farm_bp.route('/farm-reports')
def farm_reports():
    if not login_required():
        return redirect('/login')

    report_stats = {
        'total_farms': 0,
        'total_readings': 0,
        'total_recommendations': 0,
        'high_alerts': 0,
        'medium_alerts': 0,
        'normal_alerts': 0
    }

    latest_readings = []
    latest_recommendations = []

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) AS total FROM farms WHERE email = ?", (session['email'],))
    report_stats['total_farms'] = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM farm_readings
        WHERE farm_id IN (
            SELECT id FROM farms WHERE email = ?
        )
    """, (session['email'],))
    report_stats['total_readings'] = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM recommendations
        WHERE farm_id IN (
            SELECT id FROM farms WHERE email = ?
        )
    """, (session['email'],))
    report_stats['total_recommendations'] = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM recommendations
        WHERE severity = 'High'
        AND farm_id IN (
            SELECT id FROM farms WHERE email = ?
        )
    """, (session['email'],))
    report_stats['high_alerts'] = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM recommendations
        WHERE severity = 'Medium'
        AND farm_id IN (
            SELECT id FROM farms WHERE email = ?
        )
    """, (session['email'],))
    report_stats['medium_alerts'] = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM recommendations
        WHERE severity = 'Normal'
        AND farm_id IN (
            SELECT id FROM farms WHERE email = ?
        )
    """, (session['email'],))
    report_stats['normal_alerts'] = cursor.fetchone()['total']

    cursor.execute("""
        SELECT 
            farm_readings.*,
            farms.farm_name,
            farms.crop_type
        FROM farm_readings
        JOIN farms ON farm_readings.farm_id = farms.id
        WHERE farms.email = ?
        ORDER BY farm_readings.id DESC
        LIMIT 5
    """, (session['email'],))
    latest_readings = cursor.fetchall()

    cursor.execute("""
        SELECT
            recommendations.*,
            farms.farm_name
        FROM recommendations
        JOIN farms ON recommendations.farm_id = farms.id
        WHERE farms.email = ?
        ORDER BY recommendations.id DESC
        LIMIT 8
    """, (session['email'],))
    latest_recommendations = cursor.fetchall()

    conn.close()

    return render_template(
        'farm_reports.html',
        report_stats=report_stats,
        latest_readings=latest_readings,
        latest_recommendations=latest_recommendations
    )


@farm_bp.route('/farm-reports/export')
def export_farm_report():
    if not login_required():
        return redirect('/login')

    report_path = 'farm_report.csv'

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
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
        WHERE farms.email = ?
        ORDER BY farm_readings.id DESC
    """, (session['email'],))

    rows = cursor.fetchall()
    conn.close()

    with open(report_path, 'w', newline='', encoding='utf-8') as file_obj:
        writer = csv.writer(file_obj)

        writer.writerow([
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

    log_action(session['email'], 'farm_report_exported', 'Farm report CSV exported.')

    return send_file(report_path, as_attachment=True)


@farm_bp.route('/farm-activity')
def farm_activity():
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT email, action, details, created_at
        FROM audit_logs
        WHERE email = ?
        AND action IN (
            'farm_added',
            'farm_updated',
            'farm_deleted',
            'farm_reading_added',
            'farm_reading_updated',
            'farm_reading_deleted',
            'farm_report_exported'
        )
        ORDER BY id DESC
        LIMIT 100
    """, (session['email'],))

    logs = cursor.fetchall()
    conn.close()

    return render_template('farm_activity.html', logs=logs)


@farm_bp.route('/farm-notifications')
def farm_notifications():
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM notifications
        WHERE email = ?
        ORDER BY id DESC
        LIMIT 100
    """, (session['email'],))

    notifications = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*) AS unread_count
        FROM notifications
        WHERE email = ? AND is_read = 0
    """, (session['email'],))

    unread_count = cursor.fetchone()['unread_count']

    conn.close()

    return render_template(
        'farm_notifications.html',
        notifications=notifications,
        unread_count=unread_count
    )


@farm_bp.route('/farm-notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    if not login_required():
        return redirect('/login')

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE email = ?
    """, (session['email'],))

    conn.commit()
    conn.close()

    return redirect('/farm-notifications')


@farm_bp.route('/farm-notifications/count')
def farm_notifications_count():
    if not login_required():
        return jsonify({'unread_count': 0})

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS unread_count
        FROM notifications
        WHERE email = ? AND is_read = 0
    """, (session['email'],))

    unread_count = cursor.fetchone()['unread_count']

    conn.close()

    return jsonify({'unread_count': unread_count})


def create_notification(email, title, message):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO notifications (
            email,
            title,
            message,
            is_read,
            created_at
        )
        VALUES (?, ?, ?, 0, ?)
    """, (
        email,
        title,
        message,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))

    conn.commit()
    conn.close()


def to_float(value):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except ValueError:
        return None


def generate_recommendations(
    soil_moisture,
    ph_level,
    nitrogen,
    phosphorus,
    potassium,
    temperature,
    humidity,
    pest_observation
):
    recommendations = []

    soil_moisture = to_float(soil_moisture)
    ph_level = to_float(ph_level)
    nitrogen = to_float(nitrogen)
    phosphorus = to_float(phosphorus)
    potassium = to_float(potassium)
    temperature = to_float(temperature)
    humidity = to_float(humidity)

    if soil_moisture is not None:
        if soil_moisture < 30:
            recommendations.append({
                'type': 'Irrigation',
                'message': 'Soil moisture is low. Irrigation is recommended to prevent crop stress.',
                'severity': 'High'
            })
        elif soil_moisture > 80:
            recommendations.append({
                'type': 'Irrigation',
                'message': 'Soil moisture is very high. Reduce watering and check for possible waterlogging.',
                'severity': 'Medium'
            })
        else:
            recommendations.append({
                'type': 'Irrigation',
                'message': 'Soil moisture is within a manageable range.',
                'severity': 'Normal'
            })

    if ph_level is not None:
        if ph_level < 5.5:
            recommendations.append({
                'type': 'Soil pH',
                'message': 'Soil pH is acidic. Consider soil treatment before applying more fertilizer.',
                'severity': 'Medium'
            })
        elif ph_level > 7.5:
            recommendations.append({
                'type': 'Soil pH',
                'message': 'Soil pH is alkaline. Monitor nutrient availability for the crop.',
                'severity': 'Medium'
            })
        else:
            recommendations.append({
                'type': 'Soil pH',
                'message': 'Soil pH is within a generally suitable range for many crops.',
                'severity': 'Normal'
            })

    if nitrogen is not None and nitrogen < 20:
        recommendations.append({
            'type': 'Fertilizer',
            'message': 'Nitrogen level appears low. Consider reviewing fertilizer requirements.',
            'severity': 'Medium'
        })

    if phosphorus is not None and phosphorus < 15:
        recommendations.append({
            'type': 'Fertilizer',
            'message': 'Phosphorus level appears low. Crop root development may be affected.',
            'severity': 'Medium'
        })

    if potassium is not None and potassium < 15:
        recommendations.append({
            'type': 'Fertilizer',
            'message': 'Potassium level appears low. Monitor crop strength and resistance.',
            'severity': 'Medium'
        })

    if temperature is not None and temperature > 35:
        recommendations.append({
            'type': 'Temperature',
            'message': 'High temperature detected. Crops may require additional monitoring and water management.',
            'severity': 'Medium'
        })

    if humidity is not None and humidity > 85:
        recommendations.append({
            'type': 'Pest/Disease Risk',
            'message': 'High humidity may increase the risk of pest or fungal problems. Inspect crops regularly.',
            'severity': 'Medium'
        })

    if pest_observation:
        recommendations.append({
            'type': 'Pest Observation',
            'message': 'Pest observation was recorded. Immediate field inspection is recommended.',
            'severity': 'High'
        })

    if not recommendations:
        recommendations.append({
            'type': 'General',
            'message': 'No critical issue detected from the submitted farm reading.',
            'severity': 'Normal'
        })

    return recommendations