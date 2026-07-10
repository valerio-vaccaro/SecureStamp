import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

def get_app_version():
    """Version from the latest git tag, suffixing -dev when ahead of the tag."""
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--long'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=5
        )
        description = result.stdout.strip()
        if not description:
            return 'unknown'

        parts = description.rsplit('-', 2)
        if len(parts) == 3 and parts[1].isdigit() and parts[2].startswith('g'):
            base_version, commits_since_tag, _git_hash = parts
            if int(commits_since_tag) > 0:
                return f'{base_version}-dev'
            return base_version

        return description
    except Exception:
        return 'unknown'

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql://root:@localhost/securestamp')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size 
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL')
    ONION_URL = os.getenv('ONION_URL')
    GPG_USER = os.getenv('GPG_USER', 'not-valid-key')
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USE_SSL = os.getenv('MAIL_USE_SSL', 'False') == 'True'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')
    APP_VERSION = get_app_version()
