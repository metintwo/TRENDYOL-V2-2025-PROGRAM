import os, json, time, sys
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from io import BytesIO
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
# ---- Dashboard ----
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
    urgent_mode = request.args.get("urgent", "false").lower() == "true"

    # 🔹 Siparişleri Trendyol API'den çek
    orders, total_to_ship = get_orders(status=status, size=200)

    # 🔹 SKU Filtreleme
    filter_param = request.args.get("filter")
    if filter_param:
        selected_skus = [f.strip().upper() for f in filter_param.split(",") if f.strip()]
        if "ALL" not in selected_skus:
            filtered_orders = []
            for o in orders:
                for l in o.get("lines", []):
                    sku = (l.get("merchantSku") or l.get("sku") or "").upper()
                    if sku in selected_skus:
                        filtered_orders.append(o)
                        break
            orders = filtered_orders
            total_to_ship = len(orders)

    # 🔹 Renk filtresi
    color_filter = request.args.get("color")
    if color_filter:
        color_filter_upper = color_filter.strip().upper()
        filtered_orders = []
        for o in orders:
            new_lines = []
            for l in o.get("lines", []):
                # ürün rengini büyük harfe çevirerek karşılaştır
                product_color = (l.get("productColor") or "").upper()
                if color_filter_upper in product_color:
                    new_lines.append(l)
            if new_lines:
                o["lines"] = new_lines
                filtered_orders.append(o)
        orders = filtered_orders

    # 🔹 Bugün taşımada olan kargolar (status: Picking / Shipped)
    today = datetime.now(IST).date()
    tasimada_orders = []
    for o in orders:
        if o.get("status") in ("Picking", "Shipped"):
            dt_parsed = parse_date(o.get("shipmentCreatedDate"))
            if dt_parsed:
                if dt_parsed.tzinfo is None:
                    dt_parsed = dt_parsed.replace(tzinfo=timezone.utc)
                dt_local = dt_parsed.astimezone(IST)
                if dt_local.date() == today:
                    tasimada_orders.append(o)
    tasimada_count = len(tasimada_orders)

    # 🔸 24 Saatten az kalan & cezai riskli siparişler (Kalan süreye göre)
    urgent_orders = []
    now = datetime.now(IST)

    for o in orders:
        # "Kalan:" kısmında kullanılan deadline — yani teslim için hedef tarih
        deadline_str = o.get("extendedAgreedDeliveryDate") or o.get("agreedDeliveryDate")
        if not deadline_str:
            continue

        dt_deadline = parse_date(deadline_str)
        if not dt_deadline:
            continue

        if dt_deadline.tzinfo is None:
            dt_deadline = dt_deadline.replace(tzinfo=timezone.utc)
        dt_local = dt_deadline.astimezone(IST)

        kalan_saniye = (dt_local - now).total_seconds()

        # 🎯 Ekrandaki “Kalan:” hesaplamasıyla aynı mantık:
        # 24 saatin altına giren (0–86400 sn) veya süresi geçmiş ama Shipped/Delivered olmayan siparişler
        if (0 < kalan_saniye <= 86400) or (kalan_saniye < 0 and o.get("status") not in ("Shipped", "Delivered")):
            urgent_orders.append(o)

    urgent_count = len(urgent_orders)

    # 🔸 Eğer "urgent=true" parametresi geldiyse, sadece kalan süresi 24 saatten az olanları göster
    if urgent_mode:
        orders = urgent_orders
        total_to_ship = urgent_count

    # 🔸 Sayfa render
    return render_template(
        "dashboard.html",
        orders=orders,
        total_to_ship=total_to_ship,
        tasimada_count=tasimada_count,
        urgent_count=urgent_count,
        urgent_mode=urgent_mode,
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
# ---- Sipariş İşleme ----
@app.route("/isleme-al/<supplier_id>/<int:package_id>", methods=["POST"])
@login_required
def isleme_al(supplier_id, package_id):
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Sipariş işleme alma yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    # Satır verileri
    lines_raw = request.form.get("lines", "[]")
    try:
        lines = json.loads(lines_raw)
    except Exception:
        lines = []

    # Paket durumu Picking yap
    ok = update_package_status(
        supplier_id,
        package_id,
        lines,
        status="Picking"
    )

    # Flash mesaj
    flash(
        "✅ Sipariş işleme alındı" if ok else "❌ Sipariş güncellenemedi",
        "success" if ok else "danger"
    )

    # Formdan gelen anchor ve filtre bilgileri
    redirect_to = request.form.get("redirect_to")
    search = request.form.get("search", "")
    status = request.form.get("status", "Created")

    # Redirect parametrelerini hazırla
    params = {"status": status}
    if search:
        params["search"] = search

    if redirect_to:
        return redirect(url_for("dashboard", **params) + f"#{redirect_to}")
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
        if os.getenv("RAILWAY_ENVIRONMENT"):
            url = "https://etiketproxy.yakamel.com/etiket"

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

# ---- Main ----
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)

