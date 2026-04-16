# trendyol_api.py
import datetime as dt
from typing import List, Dict, Any, Optional
import requests
from requests.auth import HTTPBasicAuth
import time
from utils import format_date, calc_remaining_time
from config import magazalar, id_to_name


BASE = "https://apigw.trendyol.com"
QNA_PATH = "/integration/qna"


# ---- Mağazalar / İsim eşlemesi ----
magazalar = [
    {"supplier_id": "938355", "api_key": "a6lCSoQj4OBSbv15PMhN", "api_secret": "R27JqxuoPkME8YBjRzf2"},
    {"supplier_id": "994330", "api_key": "5dZ34lo7p6tFQoRgWAbg", "api_secret": "C0G2cuav4I3hlmFr8v2P"},
    {"supplier_id": "940685", "api_key": "T37ZOZm0Pa18FBCuA2Yu", "api_secret": "aKi797MO3mjfv7bC8Buv"},
    {"supplier_id": "564724", "api_key": "oOiLfMB6LOJbyhVNk9zW", "api_secret": "nJPGoNm81NdHnuuSkpje"},
    {"supplier_id": "1127426", "api_key": "k7wl7ZigesBcjunfN1Zi", "api_secret": "lkiNlWUms04zvSumqHDy"},
    {"supplier_id": "1086036", "api_key": "mTYdRwclOTJ6o17894yG", "api_secret": "jbw0bvLZiILAwSW8uODE"},
    {"supplier_id": "1190254", "api_key": "6KOTo2V0lVp6ENsUZHZh", "api_secret": "FgmQBu5fFAFDVzlX4LKY"},
]

id_to_name = {
    "938355": "YKML-YAŞAR YILMAZ",
    "994330": "BAY BAYAN",
    "940685": "YAKAMEL TEKSTİL - TUĞÇE YILMAZ",
    "564724": "YUNUS EMRE KAYA",
    "1127426": "BARLİZ TEKSTİL",
    "1086036": "CMZ COLLECTION",
    "1190254": "RUNADES",
}

BASE = "https://apigw.trendyol.com"
ORDERS_PATH   = "/integration/order/sellers/{sellerId}/orders"
PACKAGE_PATH  = "/integration/order/sellers/{sellerId}/shipment-packages/{packageId}"
PRODUCTS_PATH = "/integration/product/sellers/{sellerId}/products"
QNA_PATH      = "/integration/qna"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TY-Dashboard/1.0 (+python)"})
TIMEOUT = 30

# ---------- yardımcılar ----------
def _b64(user: str, pwd: str) -> str:
    import base64
    return base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")

def _headers(api_key: str, api_secret: str) -> Dict[str, str]:
    return {
        "Authorization": f"Basic {_b64(api_key, api_secret)}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _ms(d: dt.datetime) -> int:
    return int(d.timestamp() * 1000)

def format_date(ms: Optional[int]) -> str:
    if not ms:
        return "-"
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%d.%m.%Y %H:%M")

# ---------- normalize orders ----------
def _pick_addr(a: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not a:
        return None
    return {
        "fullName": a.get("fullName") or f"{a.get('firstName','')} {a.get('lastName','')}".strip(),
        "firstName": a.get("firstName"),
        "lastName":  a.get("lastName"),
        "address1":  a.get("address1"),
        "address2":  a.get("address2"),
        "fullAddress": a.get("fullAddress"),
        "city":      a.get("city"),
        "district":  a.get("district"),
        "neighborhood": a.get("neighborhood"),
        "postalCode": a.get("postalCode"),
        "phone":     a.get("phone"),
    }

def _normalize_order(pkg: Dict[str, Any], supplier_id: str) -> Dict[str, Any]:
    """
    Trendyol paket JSON'unu normalize eder.
    Sadece işine yarayan alanlar tutulur.
    """
    # Ürün satırlarını toparla
    lines = []
    for li in pkg.get("lines", []) or []:
        lines.append({
            "id": li.get("id"),
            "productName": li.get("productName", ""),
            "productSize": li.get("productSize", ""),
            "productColor": li.get("productColor", ""),
            "quantity": li.get("quantity", 1),
            "price": li.get("price") or li.get("amount"),
            "merchantSku": li.get("merchantSku") or li.get("stockCode", ""),
            "sku": li.get("sku", ""),
            "barcode": li.get("barcode", ""),
            "productCode": li.get("productCode", "")
        })

    # 🎁 Hediye paketi bilgisi
    gift_requested = pkg.get("giftPackageRequested") or pkg.get("giftBoxRequested") or False
    gift_note = pkg.get("giftNote") or pkg.get("giftBoxNote") or pkg.get("message") or ""

    return {
        "supplier_id": supplier_id,
        "supplier_name": id_to_name.get(supplier_id, supplier_id),

        # Temel bilgiler
        "id": pkg.get("shipmentPackageId") or pkg.get("id"),
        "orderNumber": pkg.get("orderNumber", ""),
        "status": pkg.get("status", ""),

        # Tarihler
        "orderDate": pkg.get("originShipmentDate") or pkg.get("orderDate"),
        "orderDateFormatted": format_date(pkg.get("originShipmentDate") or pkg.get("orderDate")),
        "lastModifiedDate": pkg.get("lastModifiedDate"),

        # Müşteri bilgileri
        "customerFirstName": pkg.get("customerFirstName", ""),
        "customerLastName": pkg.get("customerLastName", ""),

        # Kargo bilgileri
        "cargoTrackingNumber": pkg.get("cargoTrackingNumber"),
        "cargoTrackingLink": pkg.get("cargoTrackingLink"),
        "cargoProviderName": pkg.get("cargoProviderName"),
        "cargoSenderNumber": pkg.get("cargoSenderNumber"),

        # Adresler
        "shipmentAddress": _pick_addr(pkg.get("shipmentAddress")),
        "invoiceAddress": _pick_addr(pkg.get("invoiceAddress")),

        # Teslimat
        "agreedDeliveryDate": pkg.get("agreedDeliveryDate"),
        "extendedAgreedDeliveryDate": pkg.get("extendedAgreedDeliveryDate"),

        # Fiyat
        "totalPrice": pkg.get("totalPrice"),
        "grossAmount": pkg.get("grossAmount"),

        # Satır ve notlar
        "lines": lines,
        "giftPackageRequested": gift_requested,
        "giftNote": gift_note,
    }
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
# ---------- orders list ----------
def get_orders(status="Created", size=200):

    all_orders = []
    seen_ids = set()  # 🔥 duplicate engelle

    for magaza in magazalar:

        supplier_id = magaza["supplier_id"]
        api_key = magaza["api_key"]
        api_secret = magaza["api_secret"]

        page = 0
        max_page = 50  # 🔥 güvenlik limiti (sonsuz loop engel)

        while True:

            url = BASE + ORDERS_PATH.format(sellerId=supplier_id)

            params = {
                "status": status,
                "page": page,
                "size": size,
                "orderByField": "PackageLastModifiedDate",
                "orderByDirection": "DESC"
            }

            try:
                r = SESSION.get(
                    url,
                    headers=_headers(api_key, api_secret),
                    params=params,
                    timeout=TIMEOUT
                )

                if r.status_code != 200:
                    print(f"❌ orders hata → mağaza:{supplier_id} code:{r.status_code}")
                    break

                data = r.json()
                content = data.get("content", [])

                # 🔥 VERİ YOKSA BİTİR (DOĞRU BREAK)
                if not content:
                    break

                for pkg in content:

                    order = _normalize_order(pkg, supplier_id)

                    # 🔥 DOĞRU ID
                    order_id = (
                        pkg.get("shipmentPackageId")
                        or pkg.get("packageId")
                        or pkg.get("id")
                    )

                    # 🔥 duplicate engelle
                    if order_id in seen_ids:
                        continue

                    seen_ids.add(order_id)

                    all_orders.append(order)

                print(f"📦 {supplier_id} | page:{page} | gelen:{len(content)}")

                page += 1

                # 🔥 sonsuz loop güvenliği
                if page > max_page:
                    print("⚠️ max page limit aşıldı")
                    break

            except Exception as e:
                print("❌ get_orders exception:", e)
                break

    print("✅ TOPLAM ÇEKİLEN:", len(all_orders))

    return all_orders, len(all_orders)
    def _deadline_sort_key(x):
        dl = x.get("extendedAgreedDeliveryDate") or x.get("agreedDeliveryDate")
        if not dl:
            return (10 ** 15, -(x.get("lastModifiedDate") or 0))
        try:
            rem = int(dl) - now_ms
        except Exception:
            rem = 10 ** 14
        return (rem, -(x.get("lastModifiedDate") or 0))

    result.sort(key=_deadline_sort_key)
    return result, total


# ---------- update status ----------
def update_package_status(supplier_id: str, package_id: int, lines: List[Dict[str, Any]],
                          status: str, invoice_number: Optional[str] = None) -> bool:
    body: Dict[str, Any] = {
        "lines": [{"lineId": l.get("id") or l.get("lineId") or l.get("orderLineId"),
                   "quantity": int(l.get("quantity", 1))} for l in (lines or [])]
    }
    if status == "Invoiced":
        body["params"] = {"invoiceNumber": invoice_number or ""}
    body["status"] = status
    creds = next((m for m in magazalar if m["supplier_id"] == supplier_id), None)
    if not creds:
        return False
    url = BASE + PACKAGE_PATH.format(sellerId=supplier_id, packageId=package_id)
    try:
        r = SESSION.put(url, headers=_headers(creds["api_key"], creds["api_secret"]),
                        json=body, timeout=TIMEOUT)
        if r.status_code == 200:
            return True
        print("❌ update_package_status", r.status_code, r.text[:300])
    except Exception as e:
        print("❌ update_package_status exception:", e)
    return False

# ---------- tek paket detayı ----------
def get_order_detail(supplier_id: str, package_id: int) -> Optional[Dict[str, Any]]:
    creds = next((m for m in magazalar if m["supplier_id"] == supplier_id), None)
    if not creds:
        return None
    url = BASE + ORDERS_PATH.format(sellerId=supplier_id)
    params = {
        "shipmentPackageIds": package_id,
        "size": 1, "page": 0,
        "orderByField": "PackageLastModifiedDate",
        "orderByDirection": "DESC",
        "startDate": _ms(dt.datetime.now() - dt.timedelta(days=90)),
        "endDate": _ms(dt.datetime.now() + dt.timedelta(days=1)),
    }
    try:
        r = SESSION.get(url, headers=_headers(creds["api_key"], creds["api_secret"]), params=params, timeout=TIMEOUT)
        if r.status_code != 200:
            print("❌ get_order_detail", r.status_code, r.text[:300])
            return None
        data = r.json() or {}
        content = data.get("content") or []
        if not content:
            return None
        return _normalize_order(content[0], supplier_id=supplier_id)
    except Exception as e:
        print("❌ get_order_detail exception:", e)
        return None

# ---------- görsel bulucu ----------
def _extract_first_image_from_item(item: Dict[str, Any]) -> Optional[str]:
    candidates = item.get("images") or item.get("image") or item.get("media") or []
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("path") or first.get("thumbnail")
    if isinstance(candidates, str):
        return candidates
    for key in ("variants", "items", "contents"):
        arr = item.get(key)
        if isinstance(arr, list) and arr:
            r = _extract_first_image_from_item(arr[0])
            if r:
                return r
    return None

def resolve_line_image(
    supplier_id: str,
    barcode: Optional[str] = None,
    merchantSku: Optional[str] = None,
    sku: Optional[str] = None,
    productCode: Optional[str] = None
) -> Optional[str]:

    creds = next((m for m in magazalar if m["supplier_id"] == supplier_id), None)
    if not creds:
        return None

    url = BASE + PRODUCTS_PATH.format(sellerId=supplier_id)

    # ---- En doğrudan en zayıfa doğru arama sırası ----
    search_list = []

    # 1) BARCODE → %99 doğru
    if barcode:
        search_list.append({"barcode": barcode})

    # 2) PRODUCT CODE (ör: CMZ-017, ETK3I)
    if productCode:
        search_list.append({"productCode": productCode})

    # 3) productId → productCode rakamsa
    if productCode and str(productCode).isdigit():
        search_list.append({"productId": int(productCode)})

    # 4) merchantSku ile tarama (stokCode DEĞİL!)
    if merchantSku:
        search_list.append({"merchantSku": merchantSku})

    # 5) sku da merchantSku gibi taranır
    if sku:
        search_list.append({"merchantSku": sku})

    # ---- API çağrısı ----
    for q in search_list:
        try:
            params = {**q, "size": 1, "page": 0}
            r = SESSION.get(
                url,
                headers=_headers(creds["api_key"], creds["api_secret"]),
                params=params,
                timeout=TIMEOUT
            )
            if r.status_code != 200:
                continue

            data = r.json() or {}
            items = data.get("items") or data.get("products") or data.get("content") or []

            if not items:
                continue

            img = _extract_first_image_from_item(items[0])
            if img:
                return img

        except Exception as e:
            print("resolve_line_image error:", e)

    return None

# ---------- Sorular & Cevaplar ----------
def calc_remaining_time(ms, hours=12):
    if not ms:
        return "-"
    created = dt.datetime.fromtimestamp(ms / 1000)
    deadline = created + dt.timedelta(hours=hours)
    now = dt.datetime.now()
    kalan = deadline - now
    if kalan.total_seconds() <= 0:
        return "Süre doldu ⏰"
    hours_left, remainder = divmod(int(kalan.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours_left} saat {minutes} dk kaldı"


def get_all_questions(status="WAITING_FOR_ANSWER", days=14):
    product_questions = []
    order_questions = []

    now = int(time.time() * 1000)
    start = now - (days * 24 * 60 * 60 * 1000)
    end = now

    for magaza in magazalar:
        sid = magaza["supplier_id"]
        auth = HTTPBasicAuth(magaza["api_key"], magaza["api_secret"])

        params = {
            "startDate": start,
            "endDate": end,
            "size": 50,
            "page": 0,
            "status": status,
            "orderByField": "CreatedDate",
            "orderByDirection": "DESC"
        }

        # 1) Ürün soruları
        url_products = f"{BASE}{QNA_PATH}/sellers/{sid}/questions/filter"
        r = requests.get(url_products, params=params, auth=auth, timeout=30)
        if r.status_code == 200:
            data = r.json()
            for q in data.get("content", []):
                q["supplier_id"] = sid
                q["supplier_name"] = id_to_name.get(sid, sid)
                q["creationDateFormatted"] = format_date(q.get("creationDate"))
                q["remainingTime"] = calc_remaining_time(q.get("creationDate"))
                q["imageUrl"] = q.get("imageUrl")
                q["productName"] = q.get("productName", "")
                q["userName"] = q.get("userName") or "Müşteri"

                # ✅ sadece cevap metni
                answer_text = ""
                if q.get("answers"):
                    first_answer = q["answers"][0]
                    if isinstance(first_answer, dict):
                        answer_text = first_answer.get("text", "")
                    else:
                        answer_text = str(first_answer)
                elif q.get("answerText"):
                    answer_text = q["answerText"]
                elif q.get("answer"):
                    answer_text = q["answer"]
                q["answerText"] = answer_text

                product_questions.append(q)

        # 2) Sipariş soruları
        url_orders = f"{BASE}{QNA_PATH}/sellers/{sid}/order-questions/filter"
        r2 = requests.get(url_orders, params=params, auth=auth, timeout=30)
        if r2.status_code == 200:
            data = r2.json()
            for q in data.get("content", []):
                q["supplier_id"] = sid
                q["supplier_name"] = id_to_name.get(sid, sid)
                q["creationDateFormatted"] = format_date(q.get("creationDate"))
                q["remainingTime"] = calc_remaining_time(q.get("creationDate"))
                q["orderNumber"] = q.get("orderNumber")
                q["userName"] = q.get("userName") or "Müşteri"

                # ✅ sadece cevap metni
                answer_text = ""
                if q.get("answers"):
                    first_answer = q["answers"][0]
                    if isinstance(first_answer, dict):
                        answer_text = first_answer.get("text", "")
                    else:
                        answer_text = str(first_answer)
                elif q.get("answerText"):
                    answer_text = q["answerText"]
                elif q.get("answer"):
                    answer_text = q["answer"]
                q["answerText"] = answer_text

                order_questions.append(q)

    return product_questions, order_questions

def answer_question(supplier_id, question_id, answer_text):
    magaza = next((m for m in magazalar if m["supplier_id"] == supplier_id), None)
    if not magaza:
        return False
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    url = f"{BASE}{QNA_PATH}/sellers/{supplier_id}/questions/{question_id}/answers"
    payload = {"text": answer_text}
    r = requests.post(url, json=payload, headers=headers, auth=HTTPBasicAuth(magaza["api_key"], magaza["api_secret"]))
    return r.status_code == 200

# ---------- Kargo Bildirimi (etiket yazdırma sonrası) ----------
def bildir_trendyol_kargo(supplier_id: str, package_id: int, tracking_number: str) -> bool:
    """
    Etiket oluşturulduktan sonra Trendyol'a kargo verildi (Shipped) bildirimi yapar.
    """
    try:
        creds = next((m for m in magazalar if m["supplier_id"] == supplier_id), None)
        if not creds:
            print(f"❌ bildir_trendyol_kargo: {supplier_id} için API bilgisi bulunamadı.")
            return False

        url = f"{BASE}/integration/order/sellers/{supplier_id}/shipment-packages"
        payload = [{
            "id": package_id,
            "trackingNumber": tracking_number,
            "shipmentProviderId": 3,  # 3 = Sürat Kargo
            "status": "Shipped"
        }]

        headers = _headers(creds["api_key"], creds["api_secret"])

        r = requests.put(url, json=payload, headers=headers, timeout=30)
        print(f"📨 Trendyol kargo bildirimi ({supplier_id}) → {r.status_code}")
        print("Yanıt:", r.text[:500])

        if r.status_code in (200, 202):
            print("✅ Trendyol kargo bildirimi başarılı.")
            return True
        else:
            print(f"⚠️ Trendyol kargo bildirimi başarısız: {r.status_code} - {r.text[:200]}")
            return False

    except Exception as e:
        print("❌ bildir_trendyol_kargo exception:", e)
        return False