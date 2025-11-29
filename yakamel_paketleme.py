# -*- coding: utf-8 -*-
"""
Yakamel Paketleme – FINAL SÜRÜM (Günlük Sayaç + Toplam Rapor)
Tek Ayar Sistemi + XML + Etiket + Log + Günlük Rapor + Toplam Rapor
"""

from flask import Blueprint
paketleme_blueprint = Blueprint(
    "paketleme",
    __name__,
    template_folder="templates",
    static_folder="static"
)

import io
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pandas as pd

from flask import (
    request, render_template, redirect, flash,
    send_file, render_template_string
)
from flask_login import login_required

# ==================================
# PATHLER
# ==================================
BASE_DIR = Path(__file__).resolve().parent
XML_FILE = BASE_DIR / "Entegra.xml"
LOG_FILE = BASE_DIR / "print_log_web.json"
SETTINGS_FILE = BASE_DIR / "settings.json"

ARCHIVE_DIR = BASE_DIR / "logs_archive"
ARCHIVE_DIR.mkdir(exist_ok=True)

# ==================================
# SETTINGS – FINAL TEK SİSTEM
# ==================================

DEFAULT_SETTINGS = {
    "printer_name": "",
    "dpi": 203,
    "label_width_mm": 50,
    "label_height_mm": 30,
    "barcode_height_mm": 18,
    "module_width": 0.35,
    "header_font_size": 18,
    "product_font_size": 20,
    "margin_left": 2,
    "margin_top": 2
}

def load_settings():
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, indent=2), "utf-8")
        return DEFAULT_SETTINGS

    try:
        data = json.loads(SETTINGS_FILE.read_text("utf-8"))
    except:
        data = {}

    updated = False
    for k, v in DEFAULT_SETTINGS.items():
        if k not in data:
            data[k] = v
            updated = True

    if updated:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), "utf-8")

    return data

def save_settings(form):
    data = load_settings()

    for key in DEFAULT_SETTINGS:
        val = form.get(key)
        if val is None:
            continue
        try:
            val = float(val)
        except:
            pass
        data[key] = val

    SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        "utf-8"
    )

# ==================================
# GÜNLÜK ARŞİV SİSTEMİ
# ==================================

def archive_if_new_day():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    archive_file = ARCHIVE_DIR / f"{today}.json"

    if archive_file.exists():
        return

    if LOG_FILE.exists():
        try:
            data = LOG_FILE.read_text("utf-8")
            archive_file.write_text(data, "utf-8")
        except:
            pass

    LOG_FILE.write_text("[]", "utf-8")

def ensure_log():
    if not LOG_FILE.exists():
        LOG_FILE.write_text("[]", "utf-8")

def add_log(barcode, qty, stok, urun):
    ensure_log()
    try:
        data = json.loads(LOG_FILE.read_text("utf-8"))
    except:
        data = []

    data.append({
        "ts": datetime.utcnow().isoformat(),
        "barcode": barcode,
        "qty": qty,
        "stok": stok,
        "urun": urun
    })

    LOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def read_logs():
    ensure_log()
    try:
        return json.loads(LOG_FILE.read_text("utf-8"))
    except:
        return []

# ==================================
# BUGÜN TOPLAM ETİKET SAYISI
# ==================================

def get_today_count():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    archive_file = ARCHIVE_DIR / f"{today}.json"

    if not archive_file.exists():
        return 0

    try:
        logs = json.loads(archive_file.read_text("utf-8"))
    except:
        return 0

    return sum(int(r["qty"]) for r in logs)

# ==================================
# XML OKUMA
# ==================================

def read_xml_file():
    if not XML_FILE.exists():
        return []

    try:
        tree = ET.parse(str(XML_FILE))
        root = tree.getroot()
    except:
        return []

    rows = []
    tags = ["product", "Product", "urun", "Urun", "item", "Item"]

    for tag in tags:
        for p in root.findall(f".//{tag}"):
            barkod = p.findtext("Barkod") or p.findtext("barcode") or ""
            stok = p.findtext("StokKodu") or p.findtext("Kod") or ""
            urun = p.findtext("UrunAdi") or p.findtext("Baslik") or ""

            barkod = barkod.strip()
            stok = stok.strip()
            urun = urun.strip()

            if barkod:
                rows.append({
                    "Barkod": barkod,
                    "StokKodu": stok,
                    "UrunAdi": urun
                })

    return rows
# ==================================
# ETİKET OLUŞTURMA
# ==================================

def mm_to_px(mm, dpi):
    return int((mm / 25.4) * dpi)

def load_font(size, bold=False):
    win_bold = "C:/Windows/Fonts/arialbd.ttf"
    win_norm = "C:/Windows/Fonts/arial.ttf"
    linux_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    linux_norm = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    fp = win_bold if bold else win_norm
    if Path(fp).exists():
        return ImageFont.truetype(fp, size)

    fp = linux_bold if bold else linux_norm
    if Path(fp).exists():
        return ImageFont.truetype(fp, size)

    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""

    for w in words:
        test = current + (" " if current else "") + w
        if draw.textlength(test, font=font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = w

    if current:
        lines.append(current)

    return lines

def render_label(barcode, stok, urun):
    settings = load_settings()

    dpi = int(settings["dpi"])
    W = mm_to_px(settings["label_width_mm"], dpi)
    H = mm_to_px(settings["label_height_mm"], dpi)

    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)

    # Stok kodu
    f_stok = load_font(int(settings["header_font_size"]), bold=True)
    draw.text((settings["margin_left"], settings["margin_top"]), stok, 0, font=f_stok)

    # Barkod
    try:
        from barcode import Code128
        from barcode.writer import ImageWriter

        code = Code128(str(barcode), writer=ImageWriter())
        buf = io.BytesIO()

        code.write(buf, options={"module_width": float(settings["module_width"]), "font_size": 0})

        bc = Image.open(io.BytesIO(buf.getvalue()))
        bc_h = mm_to_px(settings["barcode_height_mm"], dpi)

        bc = bc.resize((W - 20, bc_h))
        img.paste(bc, (10, f_stok.size + 12))

    except Exception as e:
        print("❌ Barkod çizilemedi:", e)

    # Ürün adı
    f_prod = load_font(int(settings["product_font_size"]), bold=True)
    max_width = W - 20

    lines = wrap_text(draw, urun, f_prod, max_width)
    y = H - (len(lines) * (f_prod.size + 4)) - 5

    for line in lines:
        draw.text((10, y), line, 0, font=f_prod)
        y += f_prod.size + 4

    return img

# ==================================
# PAKETLEME SAYFASI
# ==================================

@paketleme_blueprint.route("/paketleme", methods=["GET"])
@login_required
def paketleme_page():
    archive_if_new_day()

    xml_name = XML_FILE.name if XML_FILE.exists() else None
    q = (request.args.get("q") or "").lower()

    page = int(request.args.get("page", 1))
    per_page = 20

    rows = read_xml_file()

    if q:
        rows = [r for r in rows if q in r["Barkod"].lower() or q in r["StokKodu"].lower() or q in r["UrunAdi"].lower()]

    total_count = len(rows)
    total_pages = max((total_count + per_page - 1) // per_page, 1)

    start = (page - 1) * per_page
    rows_page = rows[start:start + per_page]

    return render_template(
        "paketleme.html",
        rows=rows_page,
        q=q,
        counter=get_today_count(),
        xml_name=xml_name,
        total_pages=total_pages,
        page=page,
        total_count=total_count,
        settings=load_settings()
    )

# ==================================
# ÖNİZLEME
# ==================================

@paketleme_blueprint.route("/preview", methods=["GET"])
@login_required
def preview_route():
    barcode = request.args.get("barcode")
    stok = request.args.get("stok_kodu")
    urun = request.args.get("urun_adi")

    img = render_label(barcode, stok, urun)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)

    return send_file(buf, mimetype="image/png")

# ==================================
# YAZDIRMA
# ==================================

@paketleme_blueprint.route("/browser_print", methods=["POST"])
@login_required
def browser_print():
    barcode = request.form.get("barcode")
    stok = request.form.get("stok_kodu")
    urun = request.form.get("urun_adi")
    qty = int(request.form.get("qty", 1))

    add_log(barcode, qty, stok, urun)

    return render_template_string("""
    <html>
    <body onload="window.print(); window.close();">
    {% for i in range(qty) %}
        <img src="/preview?barcode={{barcode}}&stok_kodu={{stok}}&urun_adi={{urun}}">
    {% endfor %}
    </body>
    </html>
    """, barcode=barcode, stok=stok, urun=urun, qty=qty)

# ==================================
# RAPOR – GÜNLÜK KAYIT
# ==================================

@paketleme_blueprint.route("/rapor", methods=["GET"])
@login_required
def rapor_page():
    archive_if_new_day()

    q = (request.args.get("q") or "").lower()
    date_sel = request.args.get("date") or datetime.utcnow().strftime("%Y-%m-%d")

    file_path = ARCHIVE_DIR / f"{date_sel}.json"
    logs = json.loads(file_path.read_text("utf-8")) if file_path.exists() else []

    if q:
        logs = [r for r in logs if q in r["barcode"].lower() or q in r["stok"].lower() or q in r["urun"].lower()]

    return render_template("paketleme_rapor.html", logs=logs, q=q, date_sel=date_sel)

# ==================================
# RAPOR – GÜNLÜK EXCEL
# ==================================

@paketleme_blueprint.route("/rapor-excel", methods=["GET"])
@login_required
def rapor_excel():
    date_sel = request.args.get("date") or datetime.utcnow().strftime("%Y-%m-%d")

    file_path = ARCHIVE_DIR / f"{date_sel}.json"
    logs = json.loads(file_path.read_text("utf-8")) if file_path.exists() else []

    df = pd.DataFrame(logs)

    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"etiket_raporu_{date_sel}.xlsx"
    )

# ==================================
# RAPOR – TOPLAM RAPOR (/rapor-toplam)
# ==================================

@paketleme_blueprint.route("/rapor-toplam", methods=["GET"])
@login_required
def rapor_toplam():
    date_sel = request.args.get("date") or datetime.utcnow().strftime("%Y-%m-%d")

    file_path = ARCHIVE_DIR / f"{date_sel}.json"
    logs = json.loads(file_path.read_text("utf-8")) if file_path.exists() else []

    totals = {}
    for r in logs:
        key = r["barcode"]
        if key not in totals:
            totals[key] = {
                "barcode": r["barcode"],
                "stok": r["stok"],
                "urun": r["urun"],
                "qty": 0
            }
        totals[key]["qty"] += int(r["qty"])

    rows = list(totals.values())
    total_qty = sum(x["qty"] for x in rows)

    return render_template("paketleme_rapor_toplam.html", date_sel=date_sel, rows=rows, total=total_qty)

# ==================================
# RAPOR – TOPLAM EXCEL (/rapor-toplam-excel)
# ==================================

@paketleme_blueprint.route("/rapor-toplam-excel", methods=["GET"])
@login_required
def rapor_toplam_excel():
    date_sel = request.args.get("date") or datetime.utcnow().strftime("%Y-%m-%d")

    file_path = ARCHIVE_DIR / f"{date_sel}.json"
    logs = json.loads(file_path.read_text("utf-8")) if file_path.exists() else []

    totals = {}
    for r in logs:
        key = r["barcode"]
        if key not in totals:
            totals[key] = {
                "Barkod": r["barcode"],
                "Stok": r["stok"],
                "Ürün": r["urun"],
                "Adet": 0
            }
        totals[key]["Adet"] += int(r["qty"])

    df = pd.DataFrame(list(totals.values()))

    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"toplam_rapor_{date_sel}.xlsx"
    )

# ==================================
# AYAR SAYFASI
# ==================================

@paketleme_blueprint.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    settings = load_settings()

    if request.method == "POST":
        save_settings(request.form)
        flash("✔ Ayarlar kaydedildi!", "success")
        return redirect("/settings")

    return render_template("paketleme_settings.html", s=settings)
