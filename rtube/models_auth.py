import re
from enum import Enum
from datetime import datetime
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from rtube.models import db

# Argon2id password hasher (recommended by OWASP)
# Using secure defaults: time_cost=3, memory_cost=65536, parallelism=4
ph = PasswordHasher()


class UserRole(Enum):
    ANONYMOUS = "anonymous"
    UPLOADER = "uploader"
    ADMIN = "admin"


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __bind_key__ = "auth"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=UserRole.UPLOADER.value)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)

    def set_password(self, password: str) -> None:
        """Hash password using Argon2id (OWASP recommended)."""
        self.password_hash = ph.hash(password)

    def check_password(self, password: str) -> bool:
        """Verify password against stored hash."""
        try:
            ph.verify(self.password_hash, password)
            # Rehash if parameters have changed
            if ph.check_needs_rehash(self.password_hash):
                self.password_hash = ph.hash(password)
            return True
        except VerifyMismatchError:
            return False

    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    def is_uploader(self) -> bool:
        return self.role in (UserRole.UPLOADER.value, UserRole.ADMIN.value)

    def is_online(self, timeout_minutes: int = 5) -> bool:
        """Check if user is considered online (active within timeout)."""
        if not self.last_seen:
            return False
        from datetime import timedelta
        return datetime.utcnow() - self.last_seen < timedelta(minutes=timeout_minutes)

    @staticmethod
    def validate_password(password: str) -> tuple[bool, list[str]]:
        """
        Validate password based on Proton's recommendations:
        - Minimum 12 characters (Proton recommends 12-16+)
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        - No common patterns or sequences
        """
        errors = []

        if len(password) < 12:
            errors.append("Password must be at least 12 characters long")

        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")

        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")

        if not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;\'`~]', password):
            errors.append("Password must contain at least one special character")

        # Check for common patterns
        common_patterns = [
            r'123456', r'password', r'qwerty', r'abc123',
            r'(.)\1{3,}',  # Same character repeated 4+ times
        ]
        for pattern in common_patterns:
            if re.search(pattern, password.lower()):
                errors.append("Password contains a common pattern that is easy to guess")
                break

        # Check for sequential characters
        sequences = ['abcdefghijklmnopqrstuvwxyz', '0123456789']
        for seq in sequences:
            for i in range(len(seq) - 3):
                if seq[i:i+4] in password.lower():
                    errors.append("Password contains sequential characters")
                    break

        return len(errors) == 0, errors

    @staticmethod
    def validate_username(username: str) -> tuple[bool, list[str]]:
        """Validate username."""
        errors = []

        if len(username) < 3:
            errors.append("Username must be at least 3 characters long")

        if len(username) > 30:
            errors.append("Username must be at most 30 characters long")

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append("Username can only contain letters, numbers, and underscores")

        return len(errors) == 0, errors


def create_default_admin(app):
    """Create default admin user if no admin exists."""
    with app.app_context():
        admin = User.query.filter_by(role=UserRole.ADMIN.value).first()
        if not admin:
            admin = User(
                username="admin",
                role=UserRole.ADMIN.value
            )
            admin.set_password("admin")
            db.session.add(admin)
            db.session.commit()
            app.logger.warning(
                "Default admin user created with username 'admin' and password 'admin'. "
                "Please change the password immediately!"
            )
