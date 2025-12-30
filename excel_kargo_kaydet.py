import pandas as pd
from pathlib import Path
from datetime import datetime

EXCEL_FILE = Path("kargo_raporu.xlsx")

COLUMNS = [
    "order_no",
    "kullanici",
    "stok_kodu",
    "urun_adi",
    "renk",
    "beden",
    "adet",
    "tarih"
]

def excel_yukle():
    if EXCEL_FILE.exists():
        return pd.read_excel(EXCEL_FILE)
    return pd.DataFrame(columns=COLUMNS)

def kayit_var_mi(df, order_no, kullanici):
    if df.empty:
        return False

    return (
        (df["order_no"].astype(str) == str(order_no)) &
        (df["kullanici"] == kullanici)
    ).any()

def excele_ekle(order_no, kullanici, urunler):
    """
    urunler = [
        {
            "stok_kodu": "JG-001",
            "urun_adi": "JAGGER EŞOFMAN",
            "renk": "Siyah",
            "beden": "M",
            "adet": 1
        }
    ]
    """

    df = excel_yukle()

    if kayit_var_mi(df, order_no, kullanici):
        return  # zaten kayıtlı → çık

    yeni_kayitlar = []

    for u in urunler:
        yeni_kayitlar.append({
            "order_no": order_no,
            "kullanici": kullanici,
            "stok_kodu": u["stok_kodu"],
            "urun_adi": u["urun_adi"],
            "renk": u["renk"],
            "beden": u["beden"],
            "adet": u["adet"],
            "tarih": datetime.now().strftime("%Y-%m-%d %H:%M")
        })

    yeni_df = pd.DataFrame(yeni_kayitlar)
    df = pd.concat([df, yeni_df], ignore_index=True)
    df.to_excel(EXCEL_FILE, index=False)
