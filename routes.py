from datetime import datetime
from math import ceil

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from helpers import (
    delete_cover_file,
    fill_book_from_form,
    get_book_or_404,
    roles_required,
    sanitize_markdown_source,
    save_cover,
)
from models import Book, Cover, Genre, Review, Role, User


class SimplePagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max(ceil(total / per_page), 1) if total else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1


def paginate_list(items, page, per_page):
    page = max(page, 1)
    total = len(items)
    start = (page - 1) * per_page
    return SimplePagination(items[start:start + per_page], page, per_page, total)


def rating_labels():
    return [
        (5, "отлично"),
        (4, "хорошо"),
        (3, "удовлетворительно"),
        (2, "неудовлетворительно"),
        (1, "плохо"),
        (0, "ужасно"),
    ]


def register_routes(app):
    @app.context_processor
    def inject_now():
        return {"now": datetime.utcnow}

    @app.route("/")
    def index():
        page = request.args.get("page", 1, type=int)
        filters = {
            "title": request.args.get("title", "").strip(),
            "author": request.args.get("author", "").strip(),
            "genres": [int(g) for g in request.args.getlist("genres") if g.isdigit()],
            "years": [int(year) for year in request.args.getlist("years") if year.isdigit()],
            "pages_from": request.args.get("pages_from", "").strip(),
            "pages_to": request.args.get("pages_to", "").strip(),
        }

        review_stats = (
            db.session.query(
                Review.book_id.label("book_id"),
                func.round(func.avg(Review.rating), 1).label("avg_rating"),
                func.count(Review.id).label("review_count"),
            )
            .group_by(Review.book_id)
            .subquery()
        )
        query = (
            db.session.query(
                Book,
                func.coalesce(review_stats.c.avg_rating, 0).label("avg_rating"),
                func.coalesce(review_stats.c.review_count, 0).label("review_count"),
            )
            .outerjoin(review_stats, Book.id == review_stats.c.book_id)
            .order_by(Book.year.desc(), Book.title.asc())
        )

        if filters["genres"]:
            query = query.join(Book.genres).filter(Genre.id.in_(filters["genres"])).distinct()
        if filters["years"]:
            query = query.filter(Book.year.in_(filters["years"]))
        pages_from = int(filters["pages_from"]) if filters["pages_from"].isdigit() else None
        pages_to = int(filters["pages_to"]) if filters["pages_to"].isdigit() else None
        if pages_from is not None:
            query = query.filter(Book.pages >= pages_from)
        if pages_to is not None:
            query = query.filter(Book.pages <= pages_to)

        rows = query.all()
        if filters["title"]:
            title = filters["title"].casefold()
            rows = [row for row in rows if title in row[0].title.casefold()]
        if filters["author"]:
            author = filters["author"].casefold()
            rows = [row for row in rows if author in row[0].author.casefold()]

        books = paginate_list(rows, page, 10)
        genres = Genre.query.order_by(Genre.name).all()
        years = [
            year
            for (year,) in db.session.query(Book.year).distinct().order_by(Book.year.desc()).all()
        ]
        return render_template("index.html", books=books, genres=genres, years=years, filters=filters)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            login_value = request.form.get("login", "").strip()
            password = request.form.get("password", "")
            remember = bool(request.form.get("remember"))
            user = User.query.filter_by(login=login_value).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user, remember=remember)
                flash("Вы вошли в систему.", "success")
                return redirect(request.args.get("next") or url_for("index"))
            flash("Невозможно аутентифицироваться с указанными логином и паролем.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Вы вышли из системы.", "info")
        return redirect(url_for("index"))

    @app.route("/users")
    @roles_required("admin")
    def users():
        all_users = User.query.join(Role).order_by(Role.name, User.last_name, User.first_name).all()
        return render_template("users.html", users=all_users)

    @app.route("/users/new", methods=["GET", "POST"])
    @roles_required("admin")
    def user_create():
        roles = Role.query.order_by(Role.name).all()
        if request.method == "POST":
            login_value = request.form.get("login", "").strip()
            password = request.form.get("password", "")
            role_id = request.form.get("role_id", type=int)
            user = User(
                login=login_value,
                password_hash=generate_password_hash(password),
                last_name=request.form.get("last_name", "").strip(),
                first_name=request.form.get("first_name", "").strip(),
                middle_name=request.form.get("middle_name", "").strip(),
                role_id=role_id,
            )
            if not login_value or not password or not user.last_name or not user.first_name or not role_id:
                flash("Заполните обязательные поля пользователя.", "danger")
            elif User.query.filter_by(login=login_value).first():
                flash("Пользователь с таким логином уже существует.", "danger")
            else:
                db.session.add(user)
                db.session.commit()
                flash("Пользователь создан.", "success")
                return redirect(url_for("users"))

        return render_template("user_form.html", roles=roles)

    @app.route("/books/<int:book_id>")
    def book_detail(book_id):
        book = get_book_or_404(book_id)
        user_review = None
        if current_user.is_authenticated:
            user_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        return render_template("book_detail.html", book=book, user_review=user_review)

    @app.route("/books/new", methods=["GET", "POST"])
    @roles_required("admin")
    def book_create():
        genres = Genre.query.order_by(Genre.name).all()
        selected_genre_ids = [int(value) for value in request.form.getlist("genre_ids") if value.isdigit()]
        if request.method == "POST":
            try:
                book = fill_book_from_form(Book())
                cover = save_cover(request.files.get("cover"))
                if not cover:
                    raise ValueError("Загрузите обложку книги.")
                book.cover = cover
                db.session.add(book)
                db.session.commit()
                flash("Книга добавлена.", "success")
                return redirect(url_for("book_detail", book_id=book.id))
            except ValueError as error:
                db.session.rollback()
                flash(str(error), "danger")
        return render_template("book_form.html", book=None, genres=genres, selected_genre_ids=selected_genre_ids)

    @app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
    @roles_required("admin", "moderator")
    def book_edit(book_id):
        book = get_book_or_404(book_id)
        genres = Genre.query.order_by(Genre.name).all()
        selected_genre_ids = [genre.id for genre in book.genres]
        if request.method == "POST":
            selected_genre_ids = [int(value) for value in request.form.getlist("genre_ids") if value.isdigit()]
            try:
                fill_book_from_form(book)
                db.session.commit()
                flash("Книга обновлена.", "success")
                return redirect(url_for("book_detail", book_id=book.id))
            except ValueError as error:
                db.session.rollback()
                flash(str(error), "danger")
        return render_template("book_form.html", book=book, genres=genres, selected_genre_ids=selected_genre_ids)

    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    @roles_required("admin")
    def book_delete(book_id):
        book = get_book_or_404(book_id)
        cover_filename = book.cover.filename if book.cover else None
        cover_is_shared = bool(
            cover_filename
            and Cover.query.filter(Cover.filename == cover_filename, Cover.book_id != book.id).first()
        )
        db.session.delete(book)
        db.session.commit()
        if cover_filename and not cover_is_shared:
            delete_cover_file(cover_filename)
        flash("Книга удалена.", "success")
        return redirect(url_for("index"))

    @app.route("/books/<int:book_id>/reviews/new", methods=["GET", "POST"])
    @login_required
    def review_create(book_id):
        book = get_book_or_404(book_id)
        user_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        if user_review:
            flash("Вы уже оставили рецензию на эту книгу.", "warning")
            return redirect(url_for("book_detail", book_id=book.id))

        rating = request.form.get("rating", default=5, type=int)
        if request.method == "POST":
            text = request.form.get("text", "").strip()
            if rating is None or rating < 0 or rating > 5:
                flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            elif not text:
                flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
            else:
                review = Review(
                    book_id=book.id,
                    user_id=current_user.id,
                    rating=rating,
                    text=sanitize_markdown_source(text),
                )
                db.session.add(review)
                db.session.commit()
                flash("Рецензия добавлена.", "success")
                return redirect(url_for("book_detail", book_id=book.id))

        return render_template(
            "review_form.html",
            book=book,
            rating_labels=rating_labels(),
            selected_rating=rating,
        )

    @app.route("/reviews/<int:review_id>/delete", methods=["POST"])
    @roles_required("admin", "moderator")
    def review_delete(review_id):
        review = Review.query.get_or_404(review_id)
        book_id = review.book_id
        db.session.delete(review)
        db.session.commit()
        flash("Рецензия удалена.", "success")
        return redirect(url_for("book_detail", book_id=book_id))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="Недостаточно прав."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="Страница не найдена."), 404
