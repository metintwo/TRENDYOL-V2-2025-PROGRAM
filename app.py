import os, json, time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from dotenv import load_dotenv
from trendyol_api import (
    get_orders, update_package_status, get_order_detail, resolve_line_image,
    get_all_questions, answer_question
)

# .env yükle
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecret")

PAGE_SIZE = 20

# ---- Ana Menü ----
@app.route("/")
def index():
    return render_template("index.html")

# ---- Siparişler ----
@app.route("/dashboard")
def dashboard():
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
def questions():
    try:
        product_questions, order_questions = get_all_questions(status="WAITING_FOR_ANSWER", days=14)
        return render_template(
            "questions.html",
            product_questions=product_questions,
            order_questions=order_questions
        )
    except Exception as e:
        flash(f"Sorular alınamadı: {e}", "danger")
        return redirect(url_for("index"))

@app.route("/cevapla/<question_id>", methods=["POST"])
def cevapla(question_id):
    cevap_text = request.form.get("cevap")
    supplier_id = request.form.get("supplier_id")

    if not cevap_text or len(cevap_text) < 10:
        flash("Cevap en az 10 karakter olmalı.", "warning")
        return redirect(url_for("questions"))

    ok = answer_question(supplier_id, question_id, cevap_text)

    if ok:
        flash("✅ Cevabınız başarıyla gönderildi.", "success")
    else:
        flash("❌ Cevap gönderilemedi.", "danger")

    return redirect(url_for("questions"))

@app.route("/cevaplanan-sorular")
def cevaplanan_sorular():
    product_questions, order_questions = get_all_questions(status="ANSWERED", days=14)
    # ✅ sadece gerçekten cevabı olanlar listelensin
    sorular = [s for s in product_questions + order_questions if s.get("answerText")]
    return render_template("cevaplanan_sorular.html", sorular=sorular)

# ---- API Endpoints ----
@app.route("/api/orders")
def api_orders():
    status = request.args.get("status", "Created")
    page = int(request.args.get("page", 0))
    size = int(request.args.get("size", PAGE_SIZE))
    # ✅ page parametresi eklendi
    orders, total = get_orders(status=status, page=page, size=size)
    return jsonify({"orders": orders, "page": page, "size": size, "total": total})

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

@app.route("/isleme-al/<supplier_id>/<int:package_id>", methods=["POST"])
def isleme_al(supplier_id, package_id):
    lines_raw = request.form.get("lines", "[]")
    try:
        lines = json.loads(lines_raw)
    except Exception:
        lines = []
    ok = update_package_status(supplier_id, package_id, lines, status="Picking")
    flash("Sipariş işleme alındı ✅" if ok else "Sipariş güncellenemedi ❌", "success" if ok else "danger")
    return redirect(url_for("dashboard"))

@app.route("/etiket-yazdir/<supplier_id>/<int:package_id>")
def etiket_yazdir(supplier_id, package_id):
    order = get_order_detail(supplier_id, package_id)
    if not order:
        flash("Paket detayı getirilemedi.", "danger")
        return redirect(url_for("dashboard"))
    return render_template("etiket.html", o=order)

# ---- Main ----
if __name__ == "__main__":
    app.run(debug=True, port=5000)
