from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ==============================
#   USER MODEL (ŞİFRELİ)
# ==============================
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)

    # 🔥 Artık password değil → password_hash
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), default="user")

    # --- Şifre belirleme ---
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # --- Şifre kontrolü ---
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# ==============================
#   SHIPPING LOG MODEL
# ==============================
class ShippingLog(db.Model):
    __tablename__ = "shipping_logs"

    id = db.Column(db.Integer, primary_key=True)

    supplier_id = db.Column(db.String(20), nullable=True)
    supplier_name = db.Column(db.String(200), nullable=True)

    order_number = db.Column(db.String(50), nullable=True)
    package_id = db.Column(db.Integer, nullable=True)

    customer_name = db.Column(db.String(200), nullable=True)
    product_name = db.Column(db.String(200), nullable=True)

    sku = db.Column(db.String(100), nullable=True)
    color = db.Column(db.String(100), nullable=True)
    size = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Integer, nullable=True)

    image_url = db.Column(db.String(500), nullable=True)

    processed_at = db.Column(db.DateTime, default=datetime.utcnow)
    shipped_at = db.Column(db.DateTime, nullable=True)
