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

    # 🔐 hashli şifre
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
    tracking_number = db.Column(db.String(50), nullable=True)

    package_id = db.Column(db.String(50), nullable=True)

    barcode_image = db.Column(db.Text, nullable=True)

    customer_name = db.Column(db.String(200), nullable=True)
    product_name = db.Column(db.String(200), nullable=True)

    sku = db.Column(db.String(100), nullable=True)
    color = db.Column(db.String(100), nullable=True)
    size = db.Column(db.String(50), nullable=True)

    quantity = db.Column(db.Integer, nullable=True)

    image_url = db.Column(db.String(500), nullable=True)

    processed_at = db.Column(db.DateTime, default=datetime.utcnow)
    shipped_at = db.Column(db.DateTime, nullable=True)

    order_date = db.Column(db.DateTime, nullable=True)


# ==============================
#   PACKAGING LOG MODEL
# ==============================
class PackagingLog(db.Model):
    __tablename__ = "packaging_logs"

    id = db.Column(db.Integer, primary_key=True)

    barcode = db.Column(db.String(100), nullable=False)
    stok_kodu = db.Column(db.String(100), nullable=False)
    urun_adi = db.Column(db.Text, nullable=False)

    qty = db.Column(db.Integer, nullable=False)

    printed_at = db.Column(db.DateTime, nullable=False)

    user = db.Column(db.String(50), nullable=True)


# ==============================
#   SHIPPING ALARM MODEL
# ==============================
class ShippingAlarm(db.Model):
    __tablename__ = "shipping_alarms"

    id = db.Column(db.Integer, primary_key=True)

    alarm_type = db.Column(db.String(50))  # DUPLICATE_PACKAGE | WRONG_BARCODE
    supplier_id = db.Column(db.String(30))
    package_id = db.Column(db.String(50))
    tracking_number = db.Column(db.String(50))

    message = db.Column(db.String(255))

    created_by = db.Column(db.String(50))

    created_at = db.Column(db.DateTime)


# ==============================
#   ORDER MODEL (TOPLAMA SİSTEMİ)
# ==============================
class Order(db.Model):

    __tablename__ = "orders"

    id = db.Column(db.BigInteger, primary_key=True)

    order_number = db.Column(db.String(50))
    package_id = db.Column(db.String(50), index=True)

    # waiting_pick | picked
    order_stage = db.Column(db.String(20), default="waiting_pick")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship(
        "OrderItem",
        backref="order",
        lazy=True,
        cascade="all, delete-orphan"
    )


# ==============================
#   ORDER ITEM MODEL (TOPLAMA)
# ==============================
class OrderItem(db.Model):

    __tablename__ = "order_items"

    id = db.Column(db.BigInteger, primary_key=True)

    order_id = db.Column(
        db.BigInteger,
        db.ForeignKey("orders.id"),
        nullable=False,
        index=True
    )

    barcode = db.Column(db.String(100))
    product_name = db.Column(db.String(200))

    quantity = db.Column(db.Integer)

    picked_qty = db.Column(db.Integer, default=0)