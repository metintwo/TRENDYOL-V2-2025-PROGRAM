

import os, json, time, sys
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from io import BytesIO
from flask_migrate import Migrate
from flask import send_file
import requests
from dotenv import load_dotenv
from trendyol_api import (
    get_orders, update_package_status, get_order_detail, resolve_line_image,
    get_all_questions, answer_question
)
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from flask import session
from datetime import datetime, timedelta
SURAT_KARGO_HESAPLARI = {
    "564724": {  # RUNADES
        "KullaniciAdi": "1500205406",   # ✅ sözleşme kodu artık kullanıcı adı
        "Sifre": "Yunus.5406",          # ✅ senin gerçek şifren
        "SozlesmeKodu": "1500205406",   # aynı kalabilir
        "FirmaAdi": "YUNUS EMRE KAYA"
    },
    "940685": {  # YAKAMEL TEKSTİL - TUĞÇE YILMAZ
        "KullaniciAdi": "1500204598",
        "Sifre": "Yunus.5406",
        "SozlesmeKodu": "1500204598",
        "FirmaAdi": "TUĞÇE YILMAZ"
    },
    "1086036": {  # CMZ COLLECTION
        "KullaniciAdi": "1500200828",
        "Sifre": "Yunus.5406",
        "SozlesmeKodu": "1500200828",
        "FirmaAdi": "CMZ COLLECTION TEKSTİL"
    },
    "1127426": {  # BARLİZ TEKSTİL
        "KullaniciAdi": "1500199645",
        "Sifre": "Yunus.5406",
        "SozlesmeKodu": "1500199645",
        "FirmaAdi": "BARLİZ TEKSTİL"
    },
    "938355": {  # YKML-YAŞAR YILMAZ
        "KullaniciAdi": "1500229286",
        "Sifre": "Yunus.5406",
        "SozlesmeKodu": "1500229286",
        "FirmaAdi": "YKML - YAŞAR YILMAZ"
    },
    "994330": {  # BAY BAYAN
        "KullaniciAdi": "1500228013",
        "Sifre": "Yunus.5406",
        "SozlesmeKodu": "1500228013",
        "FirmaAdi": "BAY BAYAN TEKSTİL"
    }
}

# 🔹 Filtre SKU listesi
FILTER_SKUS = [
    "KFTK", "ETK3I", "BSKLE", "KIKT", "ETKP", "TAYT", "ESF3I", "ESPE", "SWT3I", "PLZO",
    "KSKP", "ESFKP", "KMTK", "BKTK", "KKTK", "OFBS", "BTSH", "SBP", "SGP", "UBP", "UGP",
    "KBP", "KGP", "ULP", "KKFE", "BSKLTY", "TSH", "HRKA", "FDKY", "FSAH", "KSTK", "OFTA",
    "HRTK", "EPA", "OBSWT", "DYTK", "SLP", "KLP", "ELBS", "DKP", "KMNO", "ESTK", "SAL",
    "BAT", "HRKI", "CNT", "MTR", "PBK", "OFT", "PLR"
]
FILTER_SKUS = [sku.upper() for sku in FILTER_SKUS]

from datetime import datetime, timezone

# ⬇️ BURANIN ALTINA EKLE ⬇️

# 🔹 Mağaza ve Renk Filtresi Ayarları
AVAILABLE_SUPPLIERS = {
    "564724": "RUNADES",
    "940685": "YAKAMEL TEKSTİL",
    "938355": "YKML",
    "1086036": "CMZ COLLECTION",
    "1127426": "BARLİZ TEKSTİL",
    "994330": "BAY BAYAN"
}

COLOR_FILTERS = ["SİYAH", "LACİVERT", "FÜME", "KAHVERENGİ", "HAKİ", "BEYAZ", "BEJ", "GRİ", "KIRMIZI", "MAVİ", "YEŞİL"]

def parse_date(dt):
    """Trendyol tarih alanlarını güvenli şekilde datetime objesine çevirir (UTC aware)"""
    if not dt:
        return None
    try:
        if isinstance(dt, str) and dt.isdigit():
            dt = int(dt)

        if isinstance(dt, (int, float)):
            # Trendyol timestamp milisaniye cinsinden geliyor → UTC
            return datetime.fromtimestamp(dt / 1000.0, tz=timezone.utc)
        elif isinstance(dt, str):
            # ISO string format (ör: "2025-10-01T08:55:42.000Z")
            return datetime.fromisoformat(dt.replace("Z", "+00:00")).astimezone(timezone.utc)
        elif isinstance(dt, datetime):
            # Eğer timezone bilgisi yoksa UTC ata
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        print("⚠️ Tarih parse edilemedi:", dt, e)
    return None

# 🔹 Siparişleri filtreleyen fonksiyon
def filter_orders(orders):
    filtered = []
    for order in orders:
        new_lines = []
        for line in order.get("lines", []):
            sku = (line.get("merchantSku") or line.get("sku") or "").upper()
            if sku in FILTER_SKUS:
                new_lines.append(line)
        if new_lines:
            order["lines"] = new_lines
            filtered.append(order)
    return filtered
# 🔹 Trendyol kargo bildirimi fonksiyonu (BURAYA EKLE)
def bildir_trendyol_kargo(supplier_id, package_id, tracking_number):
    url = f"https://api.trendyol.com/sapigw/suppliers/{supplier_id}/shipment-packages"
    payload = [{
        "id": package_id,
        "trackingNumber": tracking_number,
        "shipmentProviderId": 3,  # 3 = Sürat Kargo
        "status": "Shipped"
    }]
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic <API_KEY:SECRET base64>"  # bunu .env'den de çekebiliriz
    }
    r = requests.put(url, json=payload, headers=headers, timeout=15)
    print("📨 Trendyol Kargo Bildirimi:", r.status_code, r.text)
    return r.status_code == 200

# ---- Flask App ----
import os
from dotenv import load_dotenv

load_dotenv()

import sys, os
from flask import Flask

# PyInstaller uyumlu base path
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS  # derlenmiş exe içindeki temp klasör
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Flask Ayarları ----
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = os.getenv("SECRET_KEY", "supersecret")

# ---- DB Ayarları ----
DATABASE_URL = os.getenv("DATABASE_URL")

app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:12345@localhost:5432/trendyol_v2_2025_program"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db)


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
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=3))  # Türkiye saati

@app.route("/")
def index():
    try:
        today = datetime.now(IST).date()  # Türkiye tarihi

        # Created siparişler
        created_orders, created_count = get_orders(status="Created", size=500)

        # Picking siparişler
        picking_orders, picking_count = get_orders(status="Picking", size=500)

        # Shipped siparişler
        shipped_orders, shipped_count = get_orders(status="Shipped", size=500)

        # 🔹 Bugün taşımada olanları yakala
        daily_shipped = []
        for o in shipped_orders:
            # shipmentCreatedDate → varsa
            dt_parsed = parse_date(o.get("shipmentCreatedDate"))
            if not dt_parsed:
                # fallback: orderDate / lastModifiedDate de kontrol et
                dt_parsed = parse_date(o.get("lastModifiedDate") or o.get("orderDate"))

            if dt_parsed:
                if dt_parsed.tzinfo is None:
                    dt_parsed = dt_parsed.replace(tzinfo=timezone.utc)

                dt_local = dt_parsed.astimezone(IST)
                if dt_local.date() == today:
                    daily_shipped.append(o)

        # Günlük shipped sayısı
        shipped_today_count = len(daily_shipped)

        # 📦 Genel toplam
        total_all = created_count + picking_count + shipped_today_count

    except Exception as e:
        print("❌ Kargo istatistikleri alınamadı:", e)
        created_count = picking_count = shipped_today_count = total_all = 0

    return render_template(
        "index.html",
        created_count=created_count,
        picking_count=picking_count,
        shipped_count=shipped_today_count,
        total_all=total_all
    )
# ============================
# 🚀 D A S H B O A R D – MODEL A (SABİT SAYFALAMA)
# ============================
@app.route("/dashboard")
@login_required
def dashboard():
    status = request.args.get("status", "Created")
    page = int(request.args.get("page", 1))
    per_page = 100

    supplier_filter = request.args.get("supplier", "")
    color_filter = request.args.get("color", "")
    search_query = (request.args.get("search") or "").strip().lower()
    selected_filters = request.args.getlist("filter")

    # 🔹 Trendyol’dan sipariş çek
    orders_raw, total_elements = get_orders(status=status, size=500)

    # 🔥 SKU filtreleme (ALL seçilmişse hepsi gelir)
    if selected_filters and "ALL" not in selected_filters:
        new_list = []
        for o in orders_raw:
            valid_lines = []
            for l in o.get("lines", []):
                sku = (l.get("merchantSku") or l.get("sku") or "").upper()
                if sku in selected_filters:
                    valid_lines.append(l)
            if valid_lines:
                o["lines"] = valid_lines
                new_list.append(o)
        orders_raw = new_list

    # 🔥 Mağaza filtresi
    if supplier_filter:
        orders_raw = [o for o in orders_raw if str(o.get("supplier_id")) == supplier_filter]

    # 🔥 Renk filtresi
    if color_filter:
        cf = color_filter.upper()
        for o in orders_raw:
            o["lines"] = [
                l for l in o.get("lines", [])
                if (l.get("productColor") or "").upper().startswith(cf)
            ]
        orders_raw = [o for o in orders_raw if o["lines"]]

    # 🔥 Arama filtresi
    if search_query:
        filtered = []
        for o in orders_raw:
            base = (
                str(o.get("orderNumber", "")) + " " +
                str(o.get("customerFirstName","")) + " " +
                str(o.get("customerLastName",""))
            ).lower()

            found = search_query in base

            if not found:
                for l in o.get("lines", []):
                    if search_query in str(l.get("productName","")).lower():
                        found = True
                        break
                    if search_query in str(l.get("merchantSku","")).lower():
                        found = True
                        break
            if found:
                filtered.append(o)

        orders_raw = filtered

    # 🔹 Mağaza adı
    for o in orders_raw:
        o["supplier_name"] = AVAILABLE_SUPPLIERS.get(str(o.get("supplier_id")), "Bilinmeyen")

    # 🔥 24 saatten az kalanlar
    urgent_orders = []
    now = datetime.now(timezone.utc)

    for o in orders_raw:
        dl = o.get("extendedAgreedDeliveryDate") or o.get("agreedDeliveryDate")
        dt = parse_date(dl)

        if dt:
            diff = (dt - now).total_seconds() / 3600
            if diff <= 24:
                urgent_orders.append(o)

    urgent_count = len(urgent_orders)

    # 🔥 URL parametresine göre listeyi filtrele
    if request.args.get("urgent") == "true":
        orders_raw = urgent_orders

    # 🔹 Kargolanacak Created sipariş sayısı
    total_to_ship = sum(1 for o in orders_raw if o.get("status") == "Created")

    # 🔹 Tarih formatla
    for o in orders_raw:
        dt = parse_date(o.get("orderDate"))
        if dt:
            o["orderDateFormatted"] = dt.astimezone(IST).strftime("%d.%m.%Y %H:%M")
        else:
            o["orderDateFormatted"] = "-"

    # 📌 SAYFALAMA
    total_pages = max((len(orders_raw) // per_page) + (1 if len(orders_raw) % per_page else 0), 1)

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    end = start + per_page
    orders = orders_raw[start:end]
    # --- Pagination Button Range ---
    start_page = max(1, page - 3)
    end_page = min(total_pages, page + 3)
    page_numbers = list(range(start_page, end_page + 1))

    return render_template(
        "dashboard.html",
        orders=orders,
        page=page,
        total_pages=total_pages,
        page_numbers=page_numbers,
        urgent_count=urgent_count,
        total_to_ship=total_to_ship,
        selected_filters=selected_filters,
        supplier_filter=supplier_filter,
        color_filter=color_filter,
        status=status,
        per_page=per_page,
        current_filters={
            "supplier": supplier_filter,
            "color": color_filter,
            "filter": selected_filters,
            "status": status
        }
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
    except:
        lines = []

    ok = update_package_status(
        supplier_id,
        package_id,
        lines,
        status="Picking"
    )

    # LOG YAZ
    print("=== LOG BAŞLIYOR ===")

    if ok:
        print("update_package_status OK ✓")
        from models import ShippingLog
        from trendyol_api import get_order_detail

        try:
            print("→ Sipariş detay çekiliyor...")
            order_detail = get_order_detail(supplier_id, package_id)
            print("order_detail:", order_detail)

            customer_name = None
            supplier_name = None

            if order_detail:
                customer_name = f"{order_detail.get('customerFirstName', '')} {order_detail.get('customerLastName', '')}"
                supplier_name = order_detail.get("supplierName") or ""

            print("→ Line sayısı:", len(lines))

            for line in lines:
                print("→ LOG EKLENİYOR:", line.get("productName"))

                log = ShippingLog(
                    supplier_id=supplier_id,
                    supplier_name=supplier_name,

                    order_number=line.get("orderNumber"),
                    package_id=package_id,

                    customer_name=customer_name,

                    product_name=line.get("productName"),
                    sku=line.get("merchantSku"),
                    quantity=line.get("quantity", 1),
                    color=line.get("productColor"),
                    size=line.get("productSize"),

                    image_url=line.get("imageUrl") or line.get("productImageUrl"),

                    processed_at=datetime.utcnow(),
                    shipped_at=None
                )

                db.session.add(log)

            db.session.commit()
            print("✓ LOG KAYDEDİLDİ")

        except Exception as e:
            print("❌ LOG HATASI:", e)
            db.session.rollback()
    else:
        print("❌ update_package_status başarısız!")

    # 🔥 TÜM PARAMETRELERİ GERİ GÖNDER
    params = {}

    params["page"] = request.form.get("page", "1")
    params["status"] = request.form.get("status", "Created")

    supplier_f = request.form.get("supplier")
    if supplier_f:
        params["supplier"] = supplier_f

    color_f = request.form.get("color")
    if color_f:
        params["color"] = color_f

    # SKU filtreleri
    for f in request.form.getlist("filter"):
        params.setdefault("filter", []).append(f)

    urgent = request.form.get("urgent")
    if urgent:
        params["urgent"] = urgent

    # 🔥 Satır index
    row_index = request.form.get("row_index")
    if row_index:
        params["row_index"] = row_index

    flash("✅ Sipariş işleme alındı", "success")

    return redirect(url_for("dashboard", **params))


# ---- Etiket Yazdır ----
@app.route("/etiket-yazdir/<supplier_id>/<int:package_id>")
@login_required
def etiket_yazdir(supplier_id, package_id):
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Etiket yazdırma yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    print(f"🚀 Etiket Yazdır | supplier_id={supplier_id}, package_id={package_id}")
    sys.stdout.flush()

    try:
        hesap = SURAT_KARGO_HESAPLARI.get(str(supplier_id))
        if not hesap:
            flash("⚠️ Bu mağaza için Sürat Kargo bilgisi bulunamadı.", "warning")
            return redirect(url_for("dashboard"))

        # 🔁 Trendyol'dan 727 kodu için birkaç kez deneme (3 deneme x 2 sn)
        tracking_number = ""
        for attempt in range(3):
            order_detail = get_order_detail(supplier_id, package_id)
            tracking_number = str(order_detail.get("cargoTrackingNumber") or "")
            print(f"🟢 Deneme {attempt+1}/3 → Trendyol kodu: {tracking_number}")

            if tracking_number.startswith("727"):
                break
            time.sleep(2)

        if not tracking_number.startswith("727"):
            flash("⚠️ Trendyol 727 takip kodu henüz oluşturulmamış. Lütfen birkaç dakika sonra tekrar deneyin.", "warning")
            return redirect(url_for("dashboard"))

        # 📦 Adres bilgileri
        shipment = order_detail.get("shipmentAddress") or {}
        isim = (shipment.get("fullName") or f"{shipment.get('firstName','')} {shipment.get('lastName','')}").strip() or "Müşteri"
        adres = (
            f"{shipment.get('fullAddress') or ''} "
            f"{shipment.get('district') or ''} "
            f"{shipment.get('city') or ''}"
        ).strip() or "Adres bulunamadı"
        il = (shipment.get("city") or "İSTANBUL").strip()
        ilce = (shipment.get("district") or "MERKEZ").strip()
        telefon = (shipment.get("phone") or "0000000000").strip()

        # 🧾 Sürat API verisi
        data = {
            "KullaniciAdi": hesap["KullaniciAdi"],
            "Sifre": hesap["Sifre"],
            "SozlesmeKodu": hesap["SozlesmeKodu"],
            "Gonderi": {
                "KisiKurum": isim,
                "AliciAdresi": adres,
                "Il": il,
                "Ilce": ilce,
                "TelefonCep": telefon,
                "Email": "etiket@yakamel.com",
                "KargoIcerigi": "Trendyol Siparişi",
                "KargoTuru": 3,
                "OdemeTipi": 1,
                "OzelKargoTakipNo": tracking_number,  # ✅ Trendyol'un 727 kodu
                "Adet": 1,
                "BirimDesi": 2,
                "BirimKg": 3,
                "TasimaSekli": 1,
                "TeslimSekli": 1,
                "GonderiSekli": 0,
                "Pazaryerimi": 1,
                "EntegrasyonFirmasi": "Trendyol",
                "Iademi": 0
            }
        }

        url = "https://api01.suratkargo.com.tr/api/OrtakBarkodOlustur"

        # 🚀 Etiket isteği gönder
        r = requests.post(url, json=data, timeout=25)
        result = r.json()
        print("📦 Sürat API Yanıtı:", result)
        sys.stdout.flush()

        if result.get("isError"):
            flash(f"Sürat API Hatası: {result.get('Message')}", "danger")
            return redirect(url_for("dashboard"))

        # 🧾 Barkod ZPL verisi
        zpl_data = result.get("Barcode", [None])[0]
        if not zpl_data:
            flash("⚠️ Etiket ZPL verisi alınamadı.", "warning")
            return redirect(url_for("dashboard"))

        zpl_clean = (
            zpl_data.replace("\\r", "")
            .replace("\\n", "")
            .replace("\r", "")
            .replace("\n", "")
            .strip()
        )

        # 🖨 PDF üretimi (Labelary)
        labelary_url = "https://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/"
        pdf_response = requests.post(
            labelary_url,
            data=zpl_clean.encode("utf-8"),
            headers={"Accept": "application/pdf"},
            timeout=25
        )

        if pdf_response.status_code == 200:
            pdf_bytes = BytesIO(pdf_response.content)

            # ✅ Trendyol bildirimi
            try:
                bildir_trendyol_kargo(supplier_id, package_id, tracking_number)
                print(f"📨 Trendyol bildirimi yapıldı: {tracking_number}")
            except Exception as e:
                print("⚠️ Trendyol bildirim hatası:", e)

            return send_file(
                pdf_bytes,
                mimetype="application/pdf",
                as_attachment=False,
                download_name=f"etiket_{package_id}.pdf"
            )
        else:
            print("⚠️ Labelary Hata:", pdf_response.text)
            flash("Labelary PDF dönüşüm hatası.", "warning")
            return redirect(url_for("dashboard"))

    except Exception as e:
        print("❌ Etiket Hata:", e)
        flash(f"❌ Etiket oluşturulamadı: {e}", "danger")
        return redirect(url_for("dashboard"))

# ---- Kargo Toplama (Renk Birleştirme + Toplamlama) ----
from collections import defaultdict

@app.route("/kargo_toplama")
@login_required
def kargo_toplama():
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Bu sayfaya erişim yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    try:
        all_orders, total = get_orders(status="Created", size=500)

        toplu_liste = defaultdict(lambda: {
            "urun_adi": "",
            "adet": 0,
            "renk": "",
            "renk_ad": "",
            "beden": "",
            "stok": "",
            "renk_kodu": "#cccccc"
        })

        # 🔹 STK -> Ürün isimleri
        STK_TO_NAME = {
            "ETK3I": "JAGGER EŞOFMAN TAKIMI",
            "BMBRTK": "BOMBER TAKIM",
            "HRKA": "HIRKA",
            "FDKY": "DİK YAKA",
            "KFTK": "KADIN FİTİLLİ TAKIM",
            "BSKLE": "BİSİKLET YAKA TAKIM",
            "SWT3I": "SWEATSHİRT",
            "ESF3I": "3 İPLİK TEK ALT",
            "ESPE": "PENYE EŞOFMAN ALTI",
            "KMTK": "KİMONO BÜRÜMCÜK TAKIM",
            "BKTK": "BÜRÜMCÜK KISA KOLLU TAKIM",
            "KKTK": "KAŞKORSE TAKIM",
            "DYTK": "DİK YAKA EŞOFMAN TAKIMI",
            "PLR": "POLAR HIRKA"
        }

        # 🔹 Renk normalize fonksiyonu (tüm varyasyonları kapsar)
        import re
        import unicodedata

        def normalize_color_name(name):
            import re
            import unicodedata

            if not name:
                return {"kod": "#cccccc", "ad": "Belirsiz", "key": "belirsiz"}

            # 🔹 Unicode temizliği (örnek: Vi̇zon → Vizon)
            raw = unicodedata.normalize("NFKD", name)
            raw = raw.replace("İ", "i").replace("ı", "i").replace("i̇", "i")
            raw = raw.encode("ascii", "ignore").decode("utf-8", "ignore")
            raw = raw.strip().upper()

            # 🔹 Parantez ve boşluk temizliği
            raw = re.sub(r"\((.*?)\)", "", raw)
            raw = re.sub(r"\s+", " ", raw)

            # 🔹 Gereksiz kelimeler silinsin
            for junk in ["RENK", "RENGI", "RENGİ", "RNG", "MAVI", "MAVİ", "MAVISI", "MAVİSİ", "VERT", "MELANJ",
                         "COLOR"]:
                raw = raw.replace(junk, "")

            # === RENK NORMALİZASYONLARI ===

            # FÜME
            if re.search(r"FÜM|FUME|SMOKE|CHARCOAL|DARK GREY", raw):
                raw = "FÜME"

            # GRİ
            elif re.search(r"GRI|GREY|GRAY", raw):
                raw = "GRİ"

            # SAKS MAVİSİ (tüm varyasyonlar)
            elif re.search(r"SAX|SAKS|SAX BLUE|SAKS MAVI", raw):
                raw = "SAKS MAVİSİ"

            # BEBE MAVİSİ
            elif re.search(r"BEBE|BABY BLUE|BEBEMAVI|BEBEMAVISI", raw):
                raw = "BEBE MAVİSİ"

            # MÜRDÜM
            elif re.search(r"MURDUM|MORDO|MURDUM MELANJ|MURDU", raw):
                raw = "MÜRDÜM"

            # SİYAH
            elif re.search(r"BLACK|SIYAHH|SIYAH|SIAH", raw):
                raw = "SİYAH"

            # LACİVERT
            elif re.search(r"LACI|LACIVERT|NAVY", raw):
                raw = "LACİVERT"

            # HAKİ
            elif re.search(r"HAKI|KHAKI|HACKI", raw):
                raw = "HAKİ"

            # KAHVERENGİ
            elif re.search(r"KAHVE|BROWN|COFFEE|CHOCOLATE", raw):
                raw = "KAHVERENGİ"

            # BEJ
            elif re.search(r"BEIGE|BEIJE|BEYJ", raw):
                raw = "BEJ"

            # VİZON
            elif re.search(r"VIZON|VISON|MINK", raw):
                raw = "VİZON"

            # BORDO
            elif re.search(r"BORDO", raw):
                raw = "BORDO"

            # TURUNCU
            elif re.search(r"ORANGE", raw):
                raw = "TURUNCU"

            # Eğer hiçbirine uymuyorsa ismini olduğu gibi bırak
            raw = raw.strip()
            renk_ad = raw.title()

            # 🔹 Key üret
            renk_key = (
                raw.lower()
                .replace(" ", "")
                .replace("-", "")
                .replace("_", "")
                .replace(".", "")
                .replace("/", "")
                .replace("\\", "")
                .replace("ı", "i").replace("i̇", "i").replace("ş", "s")
                .replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
            )

            # 🔹 Renk kodları
            renkler = {
                "beyaz": "#ffffff",
                "siyah": "#000000",
                "lacivert": "#001f3f",
                "mavi": "#007bff",
                "saksmavisi": "#0066cc",
                "bebemavisi": "#a5d8ff",
                "gri": "#b0b0b0",
                "füme": "#5a5a5a",
                "kirmizi": "#d62828",
                "bordo": "#800020",
                "yesil": "#198754",
                "pembe": "#f472b6",
                "fusya": "#c026d3",
                "mor": "#6d28d9",
                "mürdüm": "#5f0f40",
                "kahverengi": "#6f4e37",
                "bej": "#f5f0d0",
                "vizon": "#c6b299",
                "haki": "#6b705c",
                "camel": "#c19a6b",
                "turuncu": "#ff7b00",
                "tas": "#d6cfc7"
            }

            kod = "#cccccc"
            for key, val in renkler.items():
                if renk_key.endswith(key):
                    kod = val
                    break

            return {"kod": kod, "ad": renk_ad, "key": renk_key}

        # 🔹 Siparişleri birleştiriyoruz
        for order in all_orders:
            for l in order.get("lines", []):
                stok = str(l.get("merchantSku") or l.get("productCode") or "BELİRSİZ").strip().upper()
                renk_raw = str(l.get("productColor") or "BELİRSİZ").strip().upper()
                beden = str(l.get("productSize") or "BELİRSİZ").strip().upper()
                urun_adi = STK_TO_NAME.get(stok, str(l.get("productName") or "").strip())

                renk_bilgi = normalize_color_name(renk_raw)
                renk_ad = renk_bilgi["ad"]
                renk_kodu = renk_bilgi["kod"]
                renk_key = renk_bilgi["key"]

                try:
                    adet = int(l.get("quantity", 1))
                except:
                    adet = 1

                key = (stok, renk_key, beden)

                toplu_liste[key]["urun_adi"] = urun_adi
                toplu_liste[key]["adet"] += adet
                toplu_liste[key]["renk"] = renk_raw
                toplu_liste[key]["renk_ad"] = renk_ad
                toplu_liste[key]["beden"] = beden
                toplu_liste[key]["stok"] = stok
                toplu_liste[key]["renk_kodu"] = renk_kodu

        SKU_ORDER = [
            "ETK3I","BMBRTK","HRKA","FDKY","KFTK","BSKLE","SWT3I","ESF3I","ESPE",
            "KMTK","BKTK","KKTK","DYTK","PLR"
        ]
        BEDEN_ORDER = ["S", "M", "L", "XL"]

        def sort_key(x):
            stok = x["stok"]
            renk = x["renk_ad"]
            beden = x["beden"]

            try:
                sku_index = SKU_ORDER.index(stok)
            except ValueError:
                sku_index = 999

            try:
                beden_index = BEDEN_ORDER.index(beden)
            except ValueError:
                beden_index = len(BEDEN_ORDER)

            return (sku_index, renk.lower(), beden_index)

        tablo = sorted(toplu_liste.values(), key=sort_key)

        return render_template("kargo_toplama.html", tablo=tablo, total=len(tablo))

    except Exception as e:
        import traceback
        print("❌ Kargo Toplama Hatası:", e)
        traceback.print_exc()
        flash(f"Kargo toplama hatası: {e}", "danger")
        return redirect(url_for("dashboard"))
# ---- Excel Raporu ----
from flask import send_file
import pandas as pd
from io import BytesIO

@app.route("/kargo-raporu", methods=["GET"])
@login_required
def kargo_raporu():
    from models import ShippingLog

    # Tarih filtresi (opsiyonel)
    start = request.args.get("start")
    end = request.args.get("end")

    query = ShippingLog.query

    if start:
        query = query.filter(ShippingLog.processed_at >= start)
    if end:
        query = query.filter(ShippingLog.processed_at <= end + " 23:59:59")

    logs = query.order_by(ShippingLog.processed_at.desc()).all()

    # Excel tablosu için liste oluştur
    rows = []
    for log in logs:
        rows.append({
            "Mağaza": log.supplier_name,
            "Order No": log.order_number,
            "Müşteri": log.customer_name,
            "Sipariş Tarihi": log.order_date,
            "Ürün Adı": log.product_name,
            "SKU": log.sku,
            "Renk": log.color,
            "Beden": log.size,
            "Adet": log.quantity,
            "Görsel": log.image_url,
            "İşleme Alınma": log.processed_at.strftime("%d.%m.%Y %H:%M:%S"),
            "Kargo Geçiş (varsa)": log.ship_time.strftime("%d.%m.%Y %H:%M:%S") if log.ship_time else "",
        })

    df = pd.DataFrame(rows)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"kargo_raporu.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ---- Main ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

