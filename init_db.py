from app import app
from models import db, User

with app.app_context():
    print("📌 Tablo oluşturma başlatılıyor...")
    db.create_all()
    print("✅ PostgreSQL tabloları başarıyla oluşturuldu!")

    # Admin yoksa oluştur
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        print("👤 Admin kullanıcısı oluşturuluyor...")

        admin_user = User(
            username="admin",
            role="admin"
        )
        admin_user.set_password("12345")  # İstersen değiştir

        db.session.add(admin_user)
        db.session.commit()

        print("✅ Admin kullanıcı eklendi!")
    else:
        print("ℹ Admin zaten mevcut.")
