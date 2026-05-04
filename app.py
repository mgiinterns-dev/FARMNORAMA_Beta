from flask import Flask

from admin_routes import admin_bp
from auth_routes import auth_bp
from config import Config
from db import init_db
from profile_routes import profile_bp
from security_routes import security_bp
from task_routes import task_bp
from farm_routes import farm_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(farm_bp)

    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)