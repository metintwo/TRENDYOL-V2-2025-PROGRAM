
from models import ShippingLog, ShippingAlarm
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
from models import ShippingLog
from flask import session
from collections import defaultdict
import time

_CREATED_CACHE = {
    "data": None,
    "ts": 0
}


def get_all_created_orders(use_cache=True, cache_ttl=60):
    global _CREATED_CACHE

    now = time.time()
    if use_cache and _CREATED_CACHE["data"] is not None:
        if now - _CREATED_CACHE["ts"] < cache_ttl:
            return _CREATED_CACHE["data"]

    all_orders = []
    seen_ids = set()
    page = 0
    size = 200  # Trendyol genelde 200 güvenli

    while True:
        orders, total = get_orders(status="Created", size=size, page=page)
        if not orders:
            break

        for o in orders:
            oid = o.get("id") or o.get("packageId") or o.get("package_id")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            all_orders.append(o)

        if len(orders) < size:
            break

        page += 1

    _CREATED_CACHE["data"] = all_orders
    _CREATED_CACHE["ts"] = now
    return all_orders


# ===========================
#  PAKETLEME MODÜLÜ IMPORT
# ===========================
import io
import json
import pandas as pd
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

try:
    from barcode import Code128
    from barcode.writer import ImageWriter
    HAS_BARCODE = True
except:
    HAS_BARCODE = False

XML_FILE = Path("Entegra.xml")


DEFAULT_LAYOUT = {
    "dpi": 203,
    "label_width_mm": 50.0,
    "label_height_mm": 30.0,
    "margin_x_mm": 3.0,
    "margin_top_mm": 3.0,
    "margin_bottom_mm": 3.0,
    "barcode_height_mm": 18.0,
    "module_width": 0.35,
    "header_font_size": 18,
    "barcode_text_font_size": 14,
    "product_font_size": 20,
}

# ===========================
#   XML OKUMA
# ===========================
def read_xml_file():
    if not XML_FILE.exists():
        return pd.DataFrame(columns=["Barkod", "StokKodu", "UrunAdi"])

    try:
        tree = ET.parse(str(XML_FILE))
        root = tree.getroot()
    except Exception as e:
        print("XML okunamadı:", e)
        return pd.DataFrame(columns=["Barkod", "StokKodu", "UrunAdi"])

    rows = []

    for tag in ["product", "Product", "urun", "Urun", "URUN"]:
        for p in root.findall(f".//{tag}"):
            barkod = p.findtext("Barkod") or p.findtext("barcode") or ""
            stok = p.findtext("StokKodu") or p.findtext("Kod") or ""
            urun = p.findtext("UrunAdi") or p.findtext("Baslik") or ""
            rows.append({"Barkod": barkod, "StokKodu": stok, "UrunAdi": urun})

    return pd.DataFrame(rows)
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
# ⬇⬇⬇ BUNLAR BURAYA GELECEK ⬇⬇⬇
from yakamel_paketleme import paketleme_blueprint
app.register_blueprint(paketleme_blueprint)
# ⬆⬆⬆ BUNLAR BURAYA GELECEK ⬆⬆⬆
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

# ===========================
#   LOG SİSTEMİ
# ===========================


# ===========================
#  ETİKET OLUŞTURMA
# ===========================
def mm_to_px(mm, dpi):
    return int((mm / 25.4) * dpi)

def load_font(size, bold=False):
    paths = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def render_label(barcode, stok, urun):
    dpi = DEFAULT_LAYOUT["dpi"]
    W = mm_to_px(DEFAULT_LAYOUT["label_width_mm"], dpi)
    H = mm_to_px(DEFAULT_LAYOUT["label_height_mm"], dpi)

    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)

    # Stok kodu
    font_h = load_font(DEFAULT_LAYOUT["header_font_size"], bold=True)
    d.text((10, 5), f"STOK: {stok}", 0, font=font_h)

    # Barkod
    if HAS_BARCODE:
        code = Code128(str(barcode), writer=ImageWriter())
        tmp = io.BytesIO()
        code.write(tmp, options={"module_width": DEFAULT_LAYOUT["module_width"], "font_size": 0})
        bc = Image.open(io.BytesIO(tmp.getvalue()))

        bc = bc.resize((W - 20, 50))
        img.paste(bc, (10, 40))

    # Ürün
    font_u = load_font(DEFAULT_LAYOUT["product_font_size"], bold=True)
    d.text((10, H - 35), urun[:25], 0, font=font_u)

    return img
# ===========================
#  PAKETLEME SAYFASI
# ===========================
@app.route("/paketleme", methods=["GET"])
@login_required
def paketleme():
    from sqlalchemy import func
    from models import PackagingLog

    counter = db.session.query(
        func.coalesce(func.sum(PackagingLog.qty), 0)
    ).filter(
        func.date(PackagingLog.printed_at) == datetime.now(IST).date()
    ).scalar()

    xml_name = XML_FILE.name if XML_FILE.exists() else None
    q = request.args.get("q", "").strip().lower()
    page = int(request.args.get("page", 1))
    per_page = 20

    # Eğer arama yoksa boş liste göster
    if q == "":
        return render_template(
            "paketleme.html",
            xml_name=xml_name,
            rows=[],
            q=q,
            counter=counter,
            total_pages=0,
            page=1
        )

    # Tüm XML'i oku
    df = read_xml_file()

    # lowercase kolonlar
    df["lb"] = df["Barkod"].astype(str).str.lower()
    df["ls"] = df["StokKodu"].astype(str).str.lower()
    df["lu"] = df["UrunAdi"].astype(str).str.lower()

    # Filtre
    filt = df[
        df["lb"].str.contains(q) |
        df["ls"].str.contains(q) |
        df["lu"].str.contains(q)
    ]

    total_rows = len(filt)
    total_pages = (total_rows // per_page) + (1 if total_rows % per_page else 0)

    # Sayfa sınırları
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    start = (page - 1) * per_page
    end = start + per_page

    filt_page = filt.iloc[start:end]

    rows = filt_page[["Barkod", "StokKodu", "UrunAdi"]].to_dict(orient="records")

    return render_template(
        "paketleme.html",
        xml_name=xml_name,
        rows=rows,
        q=q,
        counter=counter,
        page=page,
        total_pages=total_pages
    )


@app.route("/upload_xml", methods=["POST"])
@login_required
def upload_xml():
    f = request.files.get("xml_file")
    if not f:
        flash("XML seçilmedi!", "err")
        return redirect("/paketleme")

    f.save(XML_FILE)
    flash("XML başarıyla yüklendi!", "ok")
    return redirect("/paketleme")


@app.route("/preview")
@login_required
def preview_label_route():
    barcode = request.args.get("barcode")
    stok = request.args.get("stok_kodu")
    urun = request.args.get("urun_adi")

    img = render_label(barcode, stok, urun)
    buf = io.BytesIO()
    img = img.resize((img.width*3, img.height*3))
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


from models import PackagingLog

@app.route("/browser_print", methods=["POST"])
@login_required
def browser_print():
    barcode = request.form["barcode"]
    stok = request.form["stok_kodu"]
    urun = request.form["urun_adi"]
    qty = int(request.form.get("qty", 1))

    log = PackagingLog(
        barcode=barcode,
        stok_kodu=stok,
        urun_adi=urun,
        qty=qty,
        printed_at=datetime.now(IST),
        user=current_user.username
    )

    db.session.add(log)
    db.session.commit()

    return jsonify({"ok": True})


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
    "HRKA","BMBRTK","ETK3I","KFTK","SFTK","FDKY","BSKLE","KIKT","CNT","MTR","ETKP",
    "TAYT","ESF3I","ESPE","SWT3I","PLZO","KSKP","ESFKP","KMTK",
    "BKTK","KKTK","OFBS","BTSH","SBP","SGP","UBP","UGP",
    "KBP","KGP","ULP","KKFE","BSKLTY","TSH","FSAH",
    "KSTK","OFTA","HRTK","EPA","OBSWT","DYTK","SLP","KLP",
    "ELBS","DKP","KMNO","ESTK","SAL","BAT","HRKI","PBK",
    "PLR","KIRUT","DKRT","IPBMR","CETK","PYKP","GUPNY",

    # Ayakkabı / Çanta
    "575 AYAKKABI","4005 AYAKKABI","SR158 AYAKKABI","SR619 AYAKKABI","316 AYAKKABI",
    "123 AYAKKABI",
    "ATHLETIC CANTA",
    "VEBI EMINI ILKOKUL CANTASI"
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
    orders_raw, total_elements = get_orders(status=status, size=per_page, page=page - 1)

    # 🔁 Duplicate (aynı paket) temizleme – sadece bu sayfa için
    unique = {}
    for o in orders_raw:
        oid = o.get("id") or o.get("packageId") or o.get("package_id")
        if oid is None:
            continue
        unique[oid] = o

    orders_raw = list(unique.values())

    # 🔥 MAĞAZA (SUPPLIER) FİLTRESİ – yapıyı bozmadan
    if supplier_filter:
        orders_raw = [
            o for o in orders_raw
            if str(o.get("supplier_id")) == str(supplier_filter)
        ]

    # 🔥 SKU filtresi – SADECE siparişi filtreler, satırları silmez
    if selected_filters and "ALL" not in selected_filters:
        filtered_orders = []

        for o in orders_raw:
            if any(
                    (l.get("merchantSku") or l.get("sku") or "").upper() in selected_filters
                    for l in o.get("lines", [])
            ):
                filtered_orders.append(o)

        orders_raw = filtered_orders

    # 🔥 Renk filtresi (Doğru yöntem)
    if color_filter:
        cf = color_filter.upper()
        filtered_orders = []

        for o in orders_raw:
            # Sipariş içinde eşleşen herhangi bir renk var mı?
            has_color = False

            for l in o.get("lines", []):
                color = (l.get("productColor") or "").upper()
                if color.startswith(cf):
                    has_color = True
                    break

            # Eğer sipariş bu rengi içeriyorsa listeye ekle
            if has_color:
                filtered_orders.append(o)

        # Siparişleri güncelle (içindeki satırları silmeden)
        orders_raw = filtered_orders

    # 🔹 Mağaza adı
    for o in orders_raw:
        o["supplier_name"] = AVAILABLE_SUPPLIERS.get(str(o.get("supplier_id")), "Bilinmeyen")

        # 🔥 Hediye Paketi Talebi kontrolü
        is_gift = o.get("giftBoxRequested", False)

        gift_note = (
                o.get("giftNote") or
                o.get("giftMessage") or
                o.get("customerNote") or
                ""
        )

        o["is_gift"] = is_gift
        o["gift_note"] = gift_note

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

@app.route("/api/available-skus")
@login_required
def api_available_skus():
    # Mevcut siparişlerden SKU'ları topla (Created statüsü üzerinden)
    orders_raw, _ = get_orders(status=request.args.get("status", "Created"), size=500)

    skus = set()
    for o in orders_raw:
        for l in o.get("lines", []):
            sku = (l.get("merchantSku") or l.get("sku") or "").strip()
            if sku:
                # normalize: büyük harf + sadeleştirme
                skus.add(sku.upper())

    return jsonify({"skus": sorted(skus)})

# ---- Kullanıcı Kayıt ----
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash("❌ Bu kullanıcı adı zaten var.", "danger")
            return redirect(url_for("register"))

        new_user = User(username=username)
        new_user.set_password(password)   # ✔️ HASHLİYOR

        db.session.add(new_user)
        db.session.commit()

        flash("✔️ Kayıt başarılı, giriş yapabilirsiniz", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---- Kullanıcı Giriş ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
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

        current_user.set_password(new_password)
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

    print("🔍 /api/line-image İSTEĞİ:")
    print("supplier_id:", supplier_id)
    print("barcode:", barcode)
    print("merchantSku:", merchantSku)
    print("sku:", sku)
    print("productCode:", productCode)

    # 🔥 Barkod veya SKU ile resim çöz
    url = resolve_line_image(
        supplier_id=supplier_id,
        barcode=barcode,
        merchantSku=merchantSku,
        sku=sku,
        productCode=productCode
    )

    # ❗ Eğer bulunamazsa default değer dön
    if not url:
        url = "https://via.placeholder.com/300x300.png?text=BARKOD+YOK"

    return jsonify({"url": url})


@app.route("/isleme-al/<supplier_id>/<int:package_id>", methods=["POST"])
@login_required
def isleme_al(supplier_id, package_id):
    from datetime import datetime, timezone, timedelta
    from models import ShippingLog, ShippingAlarm
    from trendyol_api import get_order_detail

    IST = timezone(timedelta(hours=3))

    # =================================================
    # YETKİ KONTROLÜ
    # =================================================
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Sipariş işleme alma yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    # =================================================
    # SATIR VERİLERİ
    # =================================================
    lines_raw = request.form.get("lines", "[]")
    try:
        lines = json.loads(lines_raw)
    except:
        lines = []

    # =================================================
    # PAKET DURUMU
    # =================================================
    ok = update_package_status(
        supplier_id,
        package_id,
        lines,
        status="Picking"
    )

    if not ok:
        flash("❌ Paket durumu güncellenemedi!", "danger")
        return redirect(url_for("dashboard"))

    try:
        # =================================================
        # 🚨 ALARM 1: AYNI PAKET
        # =================================================
        existing = ShippingLog.query.filter_by(
            supplier_id=supplier_id,
            package_id=str(package_id)
        ).first()

        if existing:
            alarm = ShippingAlarm(
                alarm_type="DUPLICATE_PACKAGE",
                supplier_id=supplier_id,
                package_id=str(package_id),
                tracking_number=existing.tracking_number,
                message="Aynı paket ikinci kez işleme alınmaya çalışıldı",
                created_by=current_user.username,
                created_at=datetime.now(IST)
            )
            db.session.add(alarm)
            db.session.commit()

            flash("🚨 BU KARGO PAKETİ DAHA ÖNCE İŞLEME ALINMIŞ!", "danger")
            return redirect(url_for("dashboard"))

        # =================================================
        # SİPARİŞ DETAYLARI
        # =================================================
        order_detail = get_order_detail(supplier_id, package_id)

        customer_name = f"{order_detail.get('customerFirstName','')} {order_detail.get('customerLastName','')}"
        supplier_name = order_detail.get("supplier_name") or order_detail.get("supplierName") or ""
        order_number = order_detail.get("orderNumber")
        tracking_number = order_detail.get("cargoTrackingNumber")

        # =================================================
        # 🚨 ALARM 2: YANLIŞ BARKOD
        # =================================================
        if tracking_number:
            wrong = ShippingLog.query.filter(
                ShippingLog.tracking_number == tracking_number,
                ShippingLog.package_id != str(package_id)
            ).first()

            if wrong:
                alarm = ShippingAlarm(
                    alarm_type="WRONG_BARCODE",
                    supplier_id=supplier_id,
                    package_id=str(package_id),
                    tracking_number=tracking_number,
                    message="Aynı barkod farklı pakette kullanıldı",
                    created_by=current_user.username,
                    created_at=datetime.now(IST)
                )
                db.session.add(alarm)
                db.session.commit()

                flash("🚨 YANLIŞ KARGO! BU BARKOD BAŞKA PAKETE AİT!", "danger")
                return redirect(url_for("dashboard"))

        # =================================================
        # SİPARİŞ TARİHİ (TR)
        # =================================================
        order_date = None
        order_date_raw = order_detail.get("orderDate")

        if order_date_raw:
            try:
                dt = datetime.fromtimestamp(
                    int(order_date_raw) / 1000,
                    tz=timezone.utc
                )
                order_date = dt.astimezone(IST)
            except:
                order_date = None

        # =================================================
        # PAKET İÇERİĞİ (BİRLEŞTİR)
        # =================================================
        urun_adlari = []
        skular = []
        renkler = []
        bedenler = []
        toplam_adet = 0

        for line in lines:
            urun_adlari.append(str(line.get("productName")))
            skular.append(str(line.get("merchantSku")))
            renkler.append(str(line.get("productColor")))
            bedenler.append(str(line.get("productSize")))
            toplam_adet += int(line.get("quantity", 1))

        # =================================================
        # 🧾 TEK PAKET = TEK LOG
        # =================================================
        log = ShippingLog(
            supplier_id=supplier_id,
            supplier_name=supplier_name,

            order_number=order_number,
            tracking_number=tracking_number,
            package_id=str(package_id),

            customer_name=customer_name,
            order_date=order_date,

            product_name=" | ".join(urun_adlari),
            sku=" | ".join(skular),
            quantity=toplam_adet,
            color=" | ".join(renkler),
            size=" | ".join(bedenler),

            processed_at=datetime.now(IST),
            shipped_at=None,
            created_by=current_user.username
        )

        db.session.add(log)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print("❌ LOG HATASI:", e)
        flash("❌ Kargo işleme sırasında hata oluştu!", "danger")

    # =================================================
    # DASHBOARD PARAMETRELERİ
    # =================================================
    params = {
        "page": request.form.get("page", "1"),
        "status": request.form.get("status", "Created")
    }

    if request.form.get("supplier"):
        params["supplier"] = request.form.get("supplier")

    if request.form.get("color"):
        params["color"] = request.form.get("color")

    for f in request.form.getlist("filter"):
        params.setdefault("filter", []).append(f)

    if request.form.get("urgent"):
        params["urgent"] = request.form.get("urgent")

    if request.form.get("row_index"):
        params["row_index"] = request.form.get("row_index")

    flash("✅ Sipariş başarıyla işleme alındı", "success")
    return redirect(url_for("dashboard", **params))


# ---- Etiket Yazdır ----
@app.route("/etiket-yazdir/<supplier_id>/<int:package_id>")
@login_required
def etiket_yazdir(supplier_id, package_id):
    order = get_order_detail(supplier_id, package_id)
    if not order:
        flash("Paket detayı getirilemedi.", "danger")
        return redirect(url_for("dashboard"))
    return render_template("etiket.html", o=order)

@app.route("/kargo-alarm-gecmisi")
@login_required
def kargo_alarm_gecmisi():
    alarms = ShippingAlarm.query.order_by(
        ShippingAlarm.created_at.desc()
    ).limit(500).all()

    return render_template("kargo_alarm_gecmisi.html", alarms=alarms)

@app.route("/kargo-performans")
@login_required
def kargo_performans():
    from sqlalchemy import func

    today = datetime.now().date()

    data = (
        db.session.query(
            ShippingLog.created_by,
            func.count(ShippingLog.id).label("paket_sayisi")
        )
        .filter(func.date(ShippingLog.processed_at) == today)
        .group_by(ShippingLog.created_by)
        .all()
    )

    return render_template("kargo_performans.html", data=data)

@app.route("/kargo-teslim-pdf")
@login_required
def kargo_teslim_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from sqlalchemy import func

    today = datetime.now().date()
    IST = timezone(timedelta(hours=3))

    logs = ShippingLog.query.filter(
        func.date(ShippingLog.processed_at) == today
    ).all()

    file_path = f"/tmp/kargo_teslim_{today}.pdf"
    c = canvas.Canvas(file_path, pagesize=A4)

    y = 800
    c.setFont("Helvetica", 10)

    c.drawString(40, y, f"GÜNLÜK KARGO TESLİM TUTANAĞI - {today}")
    y -= 30

    for log in logs:
        c.drawString(
            40,
            y,
            f"{log.package_id} | {log.tracking_number} | {log.customer_name}"
        )
        y -= 15
        if y < 50:
            c.showPage()
            y = 800

    y -= 30
    c.drawString(40, y, "Yukarıda listelenen kargolar eksiksiz teslim alınmıştır.")
    y -= 40
    c.drawString(40, y, f"Teslim Eden: {current_user.username}")
    c.drawString(300, y, f"Tarih: {datetime.now(IST).strftime('%d.%m.%Y')}")

    c.save()
    return send_file(file_path, as_attachment=True)



@app.route("/etiket_rapor_toplama")
@login_required
def kargo_toplama():
    if current_user.role not in ["kargo", "ofis", "admin"]:
        flash("❌ Bu sayfaya erişim yetkiniz yok.", "danger")
        return redirect(url_for("dashboard"))

    try:
        all_orders = get_all_created_orders()

        from collections import defaultdict
        import re, unicodedata

        # 🔥 Doğru toplama yapısı (stok + renk bazlı, bedenler normalize)
        toplu_liste = defaultdict(lambda: {
            "urun_adi": "",
            "stok": "",
            "renk_ad": "",
            "renk_kodu": "#cccccc",
            "adetler": {"S": 0, "M": 0, "L": 0, "XL": 0}
        })

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

        # 🔧 Renk normalize
        def normalize_color_name(name):
            if not name:
                return {"kod": "#cccccc", "ad": "Belirsiz", "key": "belirsiz"}

            raw = unicodedata.normalize("NFKD", name)
            raw = raw.encode("ascii", "ignore").decode("utf-8", "ignore")
            raw = raw.strip().upper()

            raw = re.sub(r"\((.*?)\)", "", raw)
            raw = re.sub(r"\s+", " ", raw)

            if re.search(r"FUME|SMOKE|CHARCOAL|DARK GREY", raw): raw = "FÜME"
            elif re.search(r"GRI|GREY|GRAY", raw): raw = "GRİ"
            elif re.search(r"SAKS", raw): raw = "SAKS MAVİSİ"
            elif re.search(r"BEBE|BABY", raw): raw = "BEBE MAVİSİ"
            elif re.search(r"BLACK|SIYAH", raw): raw = "SİYAH"
            elif re.search(r"LACI|LACIVERT", raw): raw = "LACİVERT"
            elif re.search(r"HAKI|KHAKI", raw): raw = "HAKİ"
            elif re.search(r"KAHVE|BROWN", raw): raw = "KAHVERENGİ"
            elif re.search(r"BEIGE", raw): raw = "BEJ"
            elif re.search(r"BORDO", raw): raw = "BORDO"
            elif re.search(r"ORANGE", raw): raw = "TURUNCU"

            renk_ad = raw.title()
            renk_key = raw.lower().replace(" ", "")

            renkler = {
                "beyaz": "#ffffff",
                "siyah": "#000000",
                "lacivert": "#001f3f",
                "gri": "#b0b0b0",
                "füme": "#5a5a5a",
                "bordo": "#800020",
                "haki": "#6b705c",
                "bej": "#f5f0d0",
                "kahverengi": "#6f4e37",
                "turuncu": "#ff7b00",
            }

            kod = renkler.get(renk_key, "#cccccc")
            return {"kod": kod, "ad": renk_ad, "key": renk_key}

        # 🔧 Beden normalize (asıl hata buradaydı)
        def normalize_beden(b):
            if not b:
                return "BELİRSİZ"
            b = b.strip().upper()
            if b in ["S", "SMALL"]:
                return "S"
            if b in ["M", "MEDIUM"]:
                return "M"
            if b in ["L", "LARGE"]:
                return "L"
            if b in ["XL", "X-LARGE", "EXTRA LARGE"]:
                return "XL"
            return b

        # 🔹 Siparişleri birleştir (DOĞRU SAYIM)
        for order in all_orders:
            for l in order.get("lines", []):
                stok = str(l.get("merchantSku") or l.get("productCode") or "BELİRSİZ").strip().upper()

                renk_raw = str(l.get("productColor") or "BELİRSİZ")
                beden_raw = str(l.get("productSize") or "BELİRSİZ")

                beden = normalize_beden(beden_raw)
                urun_adi = STK_TO_NAME.get(stok, str(l.get("productName") or "").strip())

                renk_bilgi = normalize_color_name(renk_raw)
                renk_ad = renk_bilgi["ad"]
                renk_kodu = renk_bilgi["kod"]
                renk_key = renk_bilgi["key"]

                try:
                    adet = int(l.get("quantity"))
                except:
                    adet = 1

                key = (stok, renk_key)

                toplu_liste[key]["urun_adi"] = urun_adi
                toplu_liste[key]["stok"] = stok
                toplu_liste[key]["renk_ad"] = renk_ad
                toplu_liste[key]["renk_kodu"] = renk_kodu

                if beden not in toplu_liste[key]["adetler"]:
                    toplu_liste[key]["adetler"][beden] = 0

                toplu_liste[key]["adetler"][beden] += adet

        SKU_ORDER = ["ETK3I","BMBRTK","HRKA","FDKY","KFTK","BSKLE","SWT3I","ESF3I","ESPE","KMTK","BKTK","KKTK","DYTK","PLR"]

        def sort_key(x):
            try:
                sku_index = SKU_ORDER.index(x["stok"])
            except ValueError:
                sku_index = 999
            return (sku_index, x["renk_ad"].lower())

        tablo = sorted(toplu_liste.values(), key=sort_key)

        # 🧪 Debug – gerçek kontrol
        print("TOPLAM SİPARİŞ:", len(all_orders))
        print("TOPLAM SATIR:", sum(len(o.get("lines", [])) for o in all_orders))
        print("TOPLAM ÜRÜN ADEDİ (TOPLAMA):", sum(sum(v["adetler"].values()) for v in tablo))

        return render_template("kargo_toplama.html", tablo=tablo, total=len(tablo))

    except Exception as e:
        import traceback
        print("❌ Kargo Toplama Hatası:", e)
        traceback.print_exc()
        flash(f"Kargo toplama hatası: {e}", "danger")
        return redirect(url_for("dashboard"))



# ---- Excel Raporu İçin Genel Importlar ----
from flask import send_file
import pandas as pd
from io import BytesIO


@app.route("/kargo-raporu")
@login_required
def kargo_raporu():
    import pandas as pd
    from datetime import datetime, timedelta
    import os, tempfile
    from flask import send_file, request
    from openpyxl import load_workbook
    from openpyxl.styles import Font

    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")
    sheet_name = now.strftime("%Y-%m-%d")

    # ✅ geçici dosya yolu
    tmp_dir = tempfile.gettempdir()
    excel_path = os.path.join(tmp_dir, f"kargo_raporu_{sheet_name}.xlsx")

    # =========================
    # 📅 TARİH FİLTRESİ (URL)
    # =========================
    date_from = request.args.get("from")  # YYYY-MM-DD
    date_to = request.args.get("to")      # YYYY-MM-DD

    q = ShippingLog.query

    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            q = q.filter(ShippingLog.processed_at >= dt_from)
        except:
            pass

    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(ShippingLog.processed_at < dt_to)
        except:
            pass

    # 🔥 İşleme alınan kayıtlar (DASHBOARD GERÇEĞİ)
    logs = q.order_by(ShippingLog.processed_at.asc()).all()

    rows = []
    for log in logs:
        rows.append({
            "Mağaza": log.supplier_name,
            "Order No": log.order_number,
            "Kargo Barkod": log.tracking_number,
            "Müşteri": log.customer_name,
            "Sipariş Tarihi": log.order_date,
            "İşleme Alınma Tarihi": log.processed_at,
            "Ürün Adı": str(log.product_name),
            "SKU": str(log.sku),
            "Renk": str(log.color),
            "Beden": str(log.size),
            "Adet": int(log.quantity or 1),
        })

    if not rows:
        pd.DataFrame().to_excel(excel_path, index=False)
        return send_file(excel_path, as_attachment=True)

    df = pd.DataFrame(rows)

    # ✅ KESİN DOĞRU SAYI
    total_kargo = len(df)
    teslim_eden = "Baran Özkaya"

    # =========================
    # 📦 EXCEL YAZ
    # =========================
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=2
        )

    # =========================
    # ✍️ ÜST / ALT YAZILAR
    # =========================
    wb = load_workbook(excel_path)
    ws = wb[sheet_name]

    # ÜST
    ws["A1"] = f"Toplam Kargo: {total_kargo}"
    ws["A1"].font = Font(bold=True)

    # ALT
    last_row = ws.max_row + 2

    ws[f"A{last_row}"] = (
        "Yukarıda listelenen kargo paketlerini eksiksiz ve sağlam şekilde teslim aldım."
    )
    ws[f"A{last_row}"].font = Font(bold=True)

    ws[f"A{last_row + 2}"] = f"Teslim Eden: {teslim_eden}"
    ws[f"D{last_row + 2}"] = f"Tarih: {today_str}"
    ws[f"A{last_row + 4}"] = "Teslim Alan: ____________________"

    wb.save(excel_path)

    return send_file(excel_path, as_attachment=True)


# ---- Main ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

