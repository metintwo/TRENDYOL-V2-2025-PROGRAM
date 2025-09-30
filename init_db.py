from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Veritabanı tablolarını oluştur
    db.create_all()

    # Eğer admin zaten yoksa ekle
    if not User.query.filter_by(username="admin").first():
        admin_user = User(
            username="admin",
            password=generate_password_hash("1234", method="pbkdf2:sha256"),
            role="admin"
        )
        db.session.add(admin_user)
        db.session.commit()
        print("✅ İlk admin kullanıcı oluşturuldu: admin / 1234")
    else:
        print("ℹ️ Admin kullanıcısı zaten mevcut.")
