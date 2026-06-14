import os

from flask import current_app
from werkzeug.security import generate_password_hash

from extensions import db
from helpers import build_cover
from models import Book, Genre, Role, User


def seed_database():
    roles = {
        "admin": Role(
            name="admin",
            description="Суперпользователь с полным доступом к системе, включая создание и удаление книг.",
        ),
        "moderator": Role(
            name="moderator",
            description="Может редактировать данные книг и производить модерацию рецензий.",
        ),
        "user": Role(name="user", description="Может оставлять рецензии."),
    }
    db.session.add_all(roles.values())
    db.session.flush()

    users = [
        User(
            login="admin",
            password_hash=generate_password_hash("admin"),
            last_name="Администратор",
            first_name="Системы",
            role_id=roles["admin"].id,
        ),
        User(
            login="moderator",
            password_hash=generate_password_hash("moderator"),
            last_name="Модератор",
            first_name="Рецензий",
            role_id=roles["moderator"].id,
        ),
        User(
            login="user",
            password_hash=generate_password_hash("user"),
            last_name="Иванов",
            first_name="Иван",
            role_id=roles["user"].id,
        ),
    ]
    db.session.add_all(users)

    genre_names = [
        "Антиутопия",
        "Детектив",
        "Классика",
        "Научная фантастика",
        "Нон-фикшн",
        "Приключения",
        "Роман",
        "Фэнтези",
    ]
    genres = {name: Genre(name=name) for name in genre_names}
    db.session.add_all(genres.values())
    db.session.flush()

    default_cover_filename, default_cover_path = create_default_cover()
    books = [
        Book(
            title="1984",
            author="Джордж Оруэлл",
            genres=[genres["Антиутопия"], genres["Классика"]],
            year=1949,
            publisher="Secker & Warburg",
            pages=328,
            description="Классический роман о тотальном контроле, языке власти и хрупкости личной свободы.",
            cover=build_cover(default_cover_filename, default_cover_path),
        ),
        Book(
            title="Мастер и Маргарита",
            author="Михаил Булгаков",
            genres=[genres["Классика"], genres["Роман"], genres["Фэнтези"]],
            year=1967,
            publisher="YMCA Press",
            pages=480,
            description="Мистическая сатира о Москве, любви, творчестве и цене человеческого выбора.",
            cover=build_cover(default_cover_filename, default_cover_path),
        ),
        Book(
            title="Дюна",
            author="Фрэнк Герберт",
            genres=[genres["Научная фантастика"], genres["Приключения"]],
            year=1965,
            publisher="Chilton Books",
            pages=688,
            description="Эпическая история о пустынной планете Арракис, политике, экологии и судьбе.",
            cover=build_cover(default_cover_filename, default_cover_path),
        ),
    ]
    db.session.add_all(books)
    db.session.commit()


def create_default_cover():
    filename = "default-cover.svg"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    path = os.path.join(upload_folder, filename)
    os.makedirs(upload_folder, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as file:
            file.write(
                """<svg xmlns="http://www.w3.org/2000/svg" width="360" height="520" viewBox="0 0 360 520">
<rect width="360" height="520" fill="#f2eadf"/>
<rect x="34" y="38" width="292" height="444" rx="8" fill="#244247"/>
<rect x="58" y="72" width="244" height="90" rx="6" fill="#e9c46a"/>
<rect x="76" y="208" width="208" height="12" fill="#f2eadf"/>
<rect x="76" y="242" width="170" height="12" fill="#f2eadf"/>
<rect x="76" y="276" width="196" height="12" fill="#f2eadf"/>
<text x="180" y="128" font-family="Arial, sans-serif" font-size="28" text-anchor="middle" fill="#244247">BOOK</text>
</svg>"""
            )
    return filename, path
