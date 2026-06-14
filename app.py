import os

from flask import Flask

from extensions import db, login_manager
from helpers import render_markdown
from routes import register_routes
from seed import seed_database


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "library.sqlite3")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads", "cover")
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    db.init_app(app)
    login_manager.init_app(app)

    app.template_filter("markdown")(render_markdown)
    register_routes(app)
    register_commands(app)

    return app


def register_commands(app):
    @app.cli.command("init-db")
    def init_db_command():
        db.drop_all()
        db.create_all()
        seed_database()
        print("Database initialized. Users: admin/admin, moderator/moderator, user/user")


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
