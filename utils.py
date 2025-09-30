# utils.py
import datetime as dt

def format_date(timestamp: int) -> str:
    """Timestamp'i okunabilir formata çevirir (gg.aa.yyyy ss:dd)"""
    if not timestamp:
        return ""
    try:
        return dt.datetime.fromtimestamp(timestamp / 1000).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(timestamp)

def calc_remaining_time(timestamp: int) -> str:
    """Kalan cevaplama süresini hesaplar (48 saat içinde cevaplanmazsa kapanır gibi)"""
    if not timestamp:
        return "Bilinmiyor"
    try:
        created = dt.datetime.fromtimestamp(timestamp / 1000)
        deadline = created + dt.timedelta(hours=48)  # 48 saat içinde cevaplama süresi
        remaining = deadline - dt.datetime.now()
        if remaining.total_seconds() <= 0:
            return "Süre doldu ⏰"
        hours = remaining.total_seconds() // 3600
        minutes = (remaining.total_seconds() % 3600) // 60
        return f"{int(hours)}s {int(minutes)}dk kaldı"
    except Exception:
        return "Hesaplanamadı"
