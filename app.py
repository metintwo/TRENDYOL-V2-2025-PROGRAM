import os, json, time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from trendyol_api import (
    get_orders, update_package_status, get_order_detail, resolve_line_image,
    get_all_questions, answer_question
)
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User


# ---- Flask App ----
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecret")

# ✅ Artık PostgreSQL kullanıyoruz
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)


# ---- Login Manager ----
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ---- .env yükle ----
load_dotenv()

PAGE_SIZE = 20

# ---- Ana Menü ----
from datetime import datetime
@app.route("/")
def index():
    try:
        # Created siparişler
        created_orders, created_count = get_orders(status="Created", size=500)

        # Picking siparişler
        picking_orders, picking_count = get_orders(status="Picking", size=500)

        # Shipped siparişler
        shipped_orders, shipped_count = get_orders(status="Shipped", size=500)

        # Genel toplam
        total_all = created_count + picking_count + shipped_count

    except Exception as e:
        print("❌ Kargo istatistikleri alınamadı:", e)
        created_count = 0
        picking_count = 0
        shipped_count = 0
        total_all = 0

    return render_template(
        "index.html",
        created_count=created_count,
        picking_count=picking_count,
        shipped_count=shipped_count,
        total_all=total_all
    )


# ---- Siparişler ----
@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "üye":
        flash("❌ Yetkiniz yok. Lütfen admin rol atamasını bekleyin.", "danger")
        return redirect(url_for("index"))

    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Sipariş ekranına giriş yetkiniz yok.", "danger")
        return redirect(url_for("index"))

    status = request.args.get("status", "Created")
    orders, total_to_ship = get_orders(status=status, size=200)
    return render_template(
        "dashboard.html",
        orders=orders,
        total_to_ship=total_to_ship,
        has_more=False,
        version=int(time.time())
    )

# ---- Sorular ----
@app.route("/questions")
@login_required
def questions():
    try:
        # Trendyol API’den ürün ve sipariş sorularını çek
        product_questions, order_questions = get_all_questions(
            status="WAITING_FOR_ANSWER", days=14
        )
        return render_template(
            "questions.html",
            product_questions=product_questions,
            order_questions=order_questions
        )
    except Exception as e:
        flash(f"Sorular alınamadı: {e}", "danger")
        return redirect(url_for("index"))


# ---- Kullanıcı Kayıt ----
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash("❌ Bu kullanıcı adı zaten alınmış.", "danger")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")
        new_user = User(username=username, password=hashed_pw, role="üye")
        db.session.add(new_user)
        db.session.commit()
        flash("✅ Kayıt başarılı! Giriş yapabilirsiniz.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# ---- Kullanıcı Giriş ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Hatalı kullanıcı adı veya şifre", "danger")
    return render_template("login.html")

# ---- Çıkış ----
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
# ---- Şifre Değiştir ----
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")

        if not check_password_hash(current_user.password, old_password):
            flash("❌ Mevcut şifre yanlış!", "danger")
            return redirect(url_for("change_password"))

        current_user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
        db.session.commit()
        flash("✅ Şifreniz başarıyla güncellendi.", "success")
        return redirect(url_for("index"))

    return render_template("change_password.html")

# ---- Soruya Cevap Ver ----
@app.route("/cevapla/<question_id>", methods=["POST"])
@login_required
def cevapla(question_id):
    if current_user.role not in ["soru", "ofis", "admin"]:
        flash("❌ Bu soruya cevap verme yetkiniz yok.", "danger")
        return redirect(url_for("questions"))

    cevap_text = request.form.get("cevap")
    supplier_id = request.form.get("supplier_id")

    if not cevap_text or len(cevap_text) < 10:
        flash("⚠️ Cevap en az 10 karakter olmalı.", "warning")
        return redirect(url_for("questions"))

    ok = answer_question(supplier_id, question_id, cevap_text)

    if ok:
        flash("✅ Cevabınız başarıyla gönderildi.", "success")
    else:
        flash("❌ Cevap gönderilemedi.", "danger")

    return redirect(url_for("questions"))

# ---- Cevaplanan Sorular ----
@app.route("/cevaplanan-sorular")
@login_required
def cevaplanan_sorular():
    if current_user.role not in ["soru", "ofis", "admin"]:
        flash("❌ Bu sayfayı görüntüleme yetkiniz yok.", "danger")
        return redirect(url_for("index"))

    product_questions, order_questions = get_all_questions(status="ANSWERED", days=14)
    sorular = [s for s in product_questions + order_questions if s.get("answerText")]
    return render_template("cevaplanan_sorular.html", sorular=sorular)

# ---- Admin Panel ----
@app.route("/admin_panel")
@login_required
def admin_panel():
    if current_user.role != "admin":
        flash("❌ Admin paneline giriş yetkiniz yok.", "danger")
        return redirect(url_for("index"))

    users = User.query.all()
    return render_template("admin_panel.html", users=users)

# ---- Rol Değiştirme ----
@app.route("/change_role/<int:user_id>", methods=["POST"])
@login_required
def change_role(user_id):
    if current_user.role != "admin":
        flash("❌ Rol değiştirme yetkiniz yok.", "danger")
        return redirect(url_for("index"))

    user = User.query.get(user_id)
    if not user:
        flash("❌ Kullanıcı bulunamadı.", "danger")
        return redirect(url_for("admin_panel"))

    new_role = request.form.get("role")
    if new_role not in ["üye", "kargo", "soru", "ofis", "admin"]:
        flash("❌ Geçersiz rol seçildi.", "danger")
        return redirect(url_for("admin_panel"))

    user.role = new_role
    db.session.commit()
    flash(f"✅ {user.username} kullanıcısının rolü '{new_role}' olarak güncellendi.", "success")
    return redirect(url_for("admin_panel"))
# ---- Şifre Sıfırlama (Admin) ----
@app.route("/reset_password/<int:user_id>", methods=["POST"])
@login_required
def reset_password(user_id):
    if current_user.role != "admin":
        flash("❌ Şifre sıfırlama yetkiniz yok.", "danger")
        return redirect(url_for("admin_panel"))

    user = User.query.get(user_id)
    if not user:
        flash("❌ Kullanıcı bulunamadı.", "danger")
        return redirect(url_for("admin_panel"))

    new_password = request.form.get("new_password")
    if not new_password or len(new_password) < 4:
        flash("⚠️ Yeni şifre en az 4 karakter olmalı.", "warning")
        return redirect(url_for("admin_panel"))

    user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
    db.session.commit()
    flash(f"✅ {user.username} için yeni şifre başarıyla güncellendi.", "success")
    return redirect(url_for("admin_panel"))

# ---- API Endpoints ----
@app.route("/api/orders")
def api_orders():
    status = request.args.get("status", "Created")
    page = int(request.args.get("page", 0))
    size = int(request.args.get("size", PAGE_SIZE))
    orders, total = get_orders(status=status, size=size)
    return jsonify({"orders": orders, "size": size, "total": total})

@app.route("/api/line-image")
def api_line_image():
    supplier_id = request.args.get("supplier_id")
    barcode = request.args.get("barcode")
    merchantSku = request.args.get("merchantSku")
    sku = request.args.get("sku")
    productCode = request.args.get("productCode")
    url = resolve_line_image(supplier_id, barcode=barcode, merchantSku=merchantSku,
                             sku=sku, productCode=productCode)
    return jsonify({"url": url})

# ---- Sipariş İşleme ----
@app.route("/isleme-al/<supplier_id>/<int:package_id>", methods=["POST"])
@login_required
def isleme_al(supplier_id, package_id):
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Sipariş işleme alma yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    lines_raw = request.form.get("lines", "[]")
    try:
        lines = json.loads(lines_raw)
    except Exception:
        lines = []
    ok = update_package_status(supplier_id, package_id, lines, status="Picking")
    flash("✅ Sipariş işleme alındı" if ok else "❌ Sipariş güncellenemedi", "success" if ok else "danger")
    return redirect(url_for("dashboard"))

# ---- Etiket Yazdır ----
@app.route("/etiket-yazdir/<supplier_id>/<int:package_id>")
@login_required
def etiket_yazdir(supplier_id, package_id):
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Etiket yazdırma yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    order = get_order_detail(supplier_id, package_id)
    if not order:
        flash("❌ Paket detayı getirilemedi.", "danger")
        return redirect(url_for("dashboard"))
    return render_template("etiket.html", o=order)

# ---- Main ----
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
