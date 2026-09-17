from werkzeug.security import generate_password_hash

from app import app
from models import db, Admin


USERNAME = "admin"
PASSWORD = "admin123"


with app.app_context():

    existing_admin = Admin.query.filter_by(
        username=USERNAME
    ).first()

    if existing_admin:

        print("Admin already exists.")

    else:

        password_hash = generate_password_hash(
            PASSWORD
        )

        admin = Admin(
            username=USERNAME,
            password_hash=password_hash
        )

        db.session.add(admin)
        db.session.commit()

        print("Admin account created successfully.")
        print("Username:", USERNAME)
        print("Password:", PASSWORD)
