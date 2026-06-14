import os
import uuid
from hashlib import md5
from mimetypes import guess_type
from functools import wraps

import bleach
import markdown
from flask import current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required
from markupsafe import Markup
from werkzeug.utils import secure_filename

from extensions import db
from models import Book, Cover, Genre


ALLOWED_COVER_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_role(*roles):
                flash("У вас недостаточно прав для выполнения данного действия.", "danger")
                return redirect(url_for("index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def int_or_none(value):
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def get_book_or_404(book_id):
    return Book.query.get_or_404(book_id)


def allowed_cover(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_COVER_EXTENSIONS


def save_cover(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_cover(file_storage.filename):
        raise ValueError("Обложка должна быть файлом png, jpg, jpeg, gif, webp или svg.")

    original = secure_filename(file_storage.filename)
    extension = original.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    path = os.path.join(upload_folder, filename)
    file_storage.save(path)
    cover = build_cover(filename, path)
    with db.session.no_autoflush:
        existing_cover = Cover.query.filter_by(md5_hash=cover.md5_hash).first()
    if existing_cover:
        os.remove(path)
        return Cover(
            filename=existing_cover.filename,
            mime_type=existing_cover.mime_type,
            md5_hash=existing_cover.md5_hash,
        )
    return cover


def build_cover(filename, path):
    with open(path, "rb") as file:
        digest = md5(file.read()).hexdigest()
    mime_type = guess_type(filename)[0] or "application/octet-stream"
    return Cover(filename=filename, mime_type=mime_type, md5_hash=digest)


def delete_cover_file(filename):
    if not filename or filename == "default-cover.svg":
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if os.path.exists(path):
        os.remove(path)


def fill_book_from_form(book):
    required = ["title", "author", "publisher", "description"]
    for field in required:
        if not request.form.get(field, "").strip():
            raise ValueError("Заполните все обязательные поля книги.")

    genre_ids = [int(value) for value in request.form.getlist("genre_ids") if value.isdigit()]
    year = request.form.get("year", type=int)
    pages = request.form.get("pages", type=int)
    genres = Genre.query.filter(Genre.id.in_(genre_ids)).order_by(Genre.name).all()
    if not genre_ids or len(genres) != len(set(genre_ids)):
        raise ValueError("Выберите один или несколько жанров.")
    if not year or year < 1:
        raise ValueError("Год выпуска должен быть положительным числом.")
    if not pages or pages < 1:
        raise ValueError("Количество страниц должно быть положительным числом.")

    book.title = request.form["title"].strip()
    book.author = request.form["author"].strip()
    book.genres = genres
    book.year = year
    book.publisher = request.form["publisher"].strip()
    book.pages = pages
    book.description = sanitize_markdown_source(request.form["description"].strip())
    return book


def sanitize_markdown_source(text):
    return bleach.clean(text, tags=[], attributes={}, strip=False)


def render_markdown(text):
    html = markdown.markdown(text or "", extensions=["extra", "sane_lists"])
    allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS) | {
        "p",
        "pre",
        "code",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
        "blockquote",
        "ul",
        "ol",
        "li",
        "strong",
        "em",
    }
    cleaned = bleach.clean(html, tags=allowed_tags, attributes={"a": ["href", "title"]})
    return Markup(cleaned)
