from app import app, db
from models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    username = "EMRE"              # role atamak istediğin kullanıcı
    new_password = "03160316123+"   # istediğin yeni şifre
    user = User.query.filter_by(username=username).first()
    if not user:
        print("Böyle bir kullanıcı bulunamadı:", username)
    else:
        user.password = generate_password_hash(new_password, method="pbkdf2:sha256")
        user.role = "admin"
        db.session.commit()
        print(f"{username} artık admin ve şifre güncellendi.")