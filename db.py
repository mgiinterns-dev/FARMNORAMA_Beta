
import os
import sqlite3
from flask import current_app


def get_conn():
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn


def safe_alter(cursor, table_name, column_name, column_type):
    try:
        cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}')
    except sqlite3.OperationalError:
        pass


def init_db():
    os.makedirs(os.path.dirname(current_app.config['UPLOAD_FOLDER']), exist_ok=True)
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        otp TEXT,
        otp_expiry TEXT,
        verified INTEGER DEFAULT 0,
        role TEXT,
        function TEXT,
        usage TEXT,
        is_admin INTEGER DEFAULT 0,
        admin_level TEXT DEFAULT 'user',
        is_banned INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        fullname TEXT,
        phone TEXT,
        age INTEGER,
        address TEXT,
        bio TEXT,
        company TEXT,
        position TEXT,
        website TEXT,
        gender TEXT,
        photo TEXT,
        FOREIGN KEY(email) REFERENCES users(email) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT DEFAULT 'To do',
        priority TEXT DEFAULT 'Low',
        due_date TEXT,
        FOREIGN KEY(email) REFERENCES users(email) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)

    safe_alter(cursor, 'users', 'is_admin', 'INTEGER DEFAULT 0')
    safe_alter(cursor, 'profiles', 'company', 'TEXT')
    safe_alter(cursor, 'profiles', 'position', 'TEXT')
    safe_alter(cursor, 'profiles', 'website', 'TEXT')
    safe_alter(cursor, 'profiles', 'gender', 'TEXT')
    safe_alter(cursor, 'profiles', 'photo', 'TEXT')
    safe_alter(cursor, 'profiles', 'age', 'INTEGER')
    safe_alter(cursor, 'users', 'admin_level', "TEXT DEFAULT 'user'")
    safe_alter(cursor, 'users', 'is_banned', 'INTEGER DEFAULT 0')


    cursor.execute("UPDATE users SET admin_level='sub_admin' WHERE is_admin=1 AND (admin_level IS NULL OR admin_level='user')")
    cursor.execute("UPDATE users SET is_admin=1 WHERE admin_level IN ('super_admin','sub_admin')")
    cursor.execute("UPDATE users SET is_admin=0 WHERE admin_level='user' OR admin_level IS NULL")
    cursor.execute("SELECT COUNT(*) AS c FROM users WHERE admin_level='super_admin'")
    result = cursor.fetchone()
    if result['c'] == 0:
        cursor.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1")
        first_user = cursor.fetchone()
        if first_user:
            cursor.execute("UPDATE users SET is_admin=1, admin_level='super_admin' WHERE id=?", (first_user['id'],))

    conn.commit()
    conn.close()
