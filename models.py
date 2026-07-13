import os
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    email_notifications = db.Column(db.Boolean, default=True, nullable=False)
    email_notification_language = db.Column(db.String(8), default='en', nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    locked = db.Column(db.Boolean, default=True, nullable=False)
    files = db.relationship('File', backref='owner', lazy=True)
    api_tokens = db.relationship('ApiToken', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_active(self):
        return not self.locked

class File(db.Model):
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    notification_email = db.Column(db.String(255), nullable=True)
    notification_email_language = db.Column(db.String(8), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    file_path = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), default='Timestamp requested', nullable=False)
    primary_notification_sent_at = db.Column(db.DateTime, nullable=True)
    secondary_notification_sent_at = db.Column(db.DateTime, nullable=True)
    
    # Add download counters
    file_downloads = db.Column(db.Integer, default=0)
    timestamp_downloads = db.Column(db.Integer, default=0)
    signature_downloads = db.Column(db.Integer, default=0)

    def get_status_badge(self):
        status_classes = {
            'Timestamp requested': 'warning',
            'Timestamp completed': 'success',
            'Error': 'danger'
        }
        return status_classes.get(self.status, 'secondary')

    @property
    def storage_key(self):
        return os.path.splitext(self.filename)[0]

class Symbol(db.Model):
    __tablename__ = 'symbols'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ApiToken(db.Model):
    __tablename__ = 'api_tokens'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    token_prefix = db.Column(db.String(16), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    max_hits = db.Column(db.Integer, nullable=True)
    hits = db.Column(db.Integer, default=0, nullable=False)
    first_used_at = db.Column(db.DateTime, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    locked = db.Column(db.Boolean, default=False, nullable=False)
    can_list_files = db.Column(db.Boolean, default=True, nullable=False)
    can_upload_files = db.Column(db.Boolean, default=True, nullable=False)
    can_download_files = db.Column(db.Boolean, default=True, nullable=False)
    can_download_timestamps = db.Column(db.Boolean, default=True, nullable=False)
    can_download_signatures = db.Column(db.Boolean, default=True, nullable=False)
    can_manage_symbols = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
