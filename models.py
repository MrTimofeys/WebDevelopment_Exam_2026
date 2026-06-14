from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint

from extensions import db, login_manager


book_genres = db.Table(
    "book_genres",
    db.Column("book_id", db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)

    @property
    def title(self):
        titles = {
            "admin": "Администратор",
            "moderator": "Модератор",
            "user": "Пользователь",
        }
        return titles.get(self.name, self.name)


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(40), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    middle_name = db.Column(db.String(80))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)

    role = db.relationship("Role")
    reviews = db.relationship("Review", back_populates="user")

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part)

    def has_role(self, *roles):
        return self.role and self.role.name in roles


class Genre(db.Model):
    __tablename__ = "genres"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)

    books = db.relationship("Book", secondary=book_genres, back_populates="genres")


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    publisher = db.Column(db.String(160), nullable=False)
    pages = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    genres = db.relationship("Genre", secondary=book_genres, back_populates="books")
    cover = db.relationship("Cover", back_populates="book", uselist=False, cascade="all, delete-orphan")
    reviews = db.relationship("Review", back_populates="book", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("year >= 1", name="book_year_positive"),
        CheckConstraint("pages >= 1", name="book_pages_positive"),
    )

    @property
    def average_rating(self):
        if not self.reviews:
            return None
        return round(sum(review.rating for review in self.reviews) / len(self.reviews), 1)

    @property
    def cover_filename(self):
        return self.cover.filename if self.cover else "default-cover.svg"

    @property
    def genre_names(self):
        return ", ".join(genre.name for genre in sorted(self.genres, key=lambda genre: genre.name))


class Cover(db.Model):
    __tablename__ = "covers"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    md5_hash = db.Column(db.String(32), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, unique=True)

    book = db.relationship("Book", back_populates="cover")


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    book = db.relationship("Book", back_populates="reviews")
    user = db.relationship("User", back_populates="reviews")

    __table_args__ = (
        CheckConstraint("rating BETWEEN 0 AND 5", name="review_rating_range"),
        UniqueConstraint("book_id", "user_id", name="one_review_per_user_book"),
    )


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
