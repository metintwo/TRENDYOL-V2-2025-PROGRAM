from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)   # hash saklanacak
    role = db.Column(db.String(20), nullable=False, default="üye")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

    # Yeni eklenen metotlar
    def set_password(self, password):
        """Şifreyi hashleyip veritabanına kaydeder."""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Girilen şifre ile hash’i karşılaştırır."""
        return check_password_hash(self.password, password)