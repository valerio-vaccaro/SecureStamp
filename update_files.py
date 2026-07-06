#!/usr/bin/env python3
import os
import subprocess
import hashlib
import mimetypes
from datetime import datetime

from flask import render_template
from flask_mail import Message

from app import create_app, db, mail
from models import File, User
from tabulate import tabulate


def format_size(size):
    """Convert size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def get_file_size_string(file):
    try:
        return format_size(os.path.getsize(file.file_path))
    except OSError:
        return "N/A"


def calculate_file_hash(file_path):
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(8192), b''):
                sha256.update(chunk)
    except OSError:
        return None
    return sha256.hexdigest()


def normalize_base_url(raw_url):
    if not raw_url:
        return None
    raw_url = raw_url.strip()
    if not raw_url:
        return None
    if not raw_url.startswith(('http://', 'https://')):
        raw_url = f"https://{raw_url}"
    return raw_url.rstrip('/')


def get_public_base_url():
    app = create_app()
    with app.app_context():
        return normalize_base_url(app.config.get('PUBLIC_BASE_URL'))


def build_platform_link(base_url, path):
    if not base_url:
        return None
    return f"{base_url}{path}"


def format_elapsed_time(start_time, end_time):
    total_seconds = max(0, int((end_time - start_time).total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def build_timestamp_completion_email(file, user):
    confirmed_at = datetime.utcnow()
    base_url = get_public_base_url()
    return render_template(
        'emails/timestamp_completed.html',
        user=user,
        file=file,
        file_hash=calculate_file_hash(file.file_path),
        file_size=get_file_size_string(file),
        confirmed_at=confirmed_at,
        completion_time=format_elapsed_time(file.uploaded_at, confirmed_at),
        file_download_url=build_platform_link(base_url, f"/download/{file.storage_key}"),
        timestamp_download_url=build_platform_link(base_url, f"/download/timestamp/{file.storage_key}"),
        file_detail_url=build_platform_link(base_url, f"/files/{file.storage_key}"),
        platform_login_url=build_platform_link(base_url, "/login"),
    )


def build_attachment_confirmation_email(file, user):
    confirmed_at = datetime.utcnow()
    return render_template(
        'emails/timestamp_completed_attachment.html',
        user=user,
        file=file,
        file_hash=calculate_file_hash(file.file_path),
        file_size=get_file_size_string(file),
        confirmed_at=confirmed_at,
        completion_time=format_elapsed_time(file.uploaded_at, confirmed_at),
    )


def get_primary_notification_recipient(user):
    if user.email_notifications and user.email:
        return user.email.strip()
    return None


def get_secondary_notification_recipient(file, user):
    if not file.notification_email:
        return None

    secondary = file.notification_email.strip()
    return secondary or None


def build_existing_attachments(file):
    candidates = [
        (file.file_path, file.original_filename),
        (f"{file.file_path}.sig", f"{file.original_filename}.sig"),
        (f"{file.file_path}.ots", f"{file.original_filename}.ots"),
    ]
    return [(file_path, attachment_name) for file_path, attachment_name in candidates if os.path.exists(file_path)]


def smtp_configured(app):
    required_keys = ['MAIL_SERVER', 'MAIL_PORT', 'MAIL_DEFAULT_SENDER']
    return all(app.config.get(key) for key in required_keys)

def list_files():
    # Create app context
    app = create_app()
    with app.app_context():
        # Get all files with their owners
        files = db.session.query(File, User).join(User).all()
        
        if not files:
            print("No files found in database")
            return

        # Prepare data for tabulate
        table_data = []
        for file, user in files:
            size_str = get_file_size_string(file)

            # Check if signature and timestamp files exist
            sig_exists = "✓" if os.path.exists(f"{file.file_path}.sig") else "✗"
            ots_exists = "✓" if os.path.exists(f"{file.file_path}.ots") else "✗"

            table_data.append([
                file.storage_key,
                file.original_filename,
                user.username,
                file.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                size_str,
                file.status,
                sig_exists,
                ots_exists
            ])

        # Print table
        headers = ["UUID", "Filename", "Owner", "Upload Date", "Size", "Status", "Signature", "Timestamp"]
        print("\nFile Database Contents:")
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

        # Print summary
        total_files = len(files)
        total_users = len(set(user.id for _, user in files))
        print(f"\nSummary:")
        print(f"Total files: {total_files}")
        print(f"Unique users: {total_users}")

def update_files():
    # Create app context
    app = create_app()
    with app.app_context():
        mail_enabled = smtp_configured(app)
        if not mail_enabled:
            print("SMTP notifications disabled: set MAIL_SERVER, MAIL_PORT, and MAIL_DEFAULT_SENDER in .env")

        # Get all files with their owners
        files = db.session.query(File, User).join(User).all()
        
        if not files:
            print("No files found in database")
            return

        from config import Config
        for file, user in files:
            if file.status == 'Timestamp requested':
                print(f"Checking status of file {file.file_path}")
                result = subprocess.run(
                    ['ots-cli.js', 'upgrade', file.file_path + '.ots'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                if result.returncode == 0:
                    res = result.stdout.decode('utf-8')
                    print(res)
                    if res.find("Success! Timestamp complete") != -1:
                        print(f"Timestamp completed for file {file.file_path}!!!")
                        file.status = 'Timestamp completed'
                        db.session.commit()

                        primary_recipient = get_primary_notification_recipient(user)
                        secondary_recipient = get_secondary_notification_recipient(file, user)

                        if mail_enabled:
                            subject = f"SecureStamp.it: Timestamp Completed {file.original_filename}"

                            if primary_recipient:
                                html_body = build_timestamp_completion_email(file, user)
                                send_email([primary_recipient], subject, html_body)
                                print(f"Primary notification email sent to {primary_recipient}")

                            if secondary_recipient:
                                html_body = build_attachment_confirmation_email(file, user)
                                attachments = build_existing_attachments(file)
                                send_email(
                                    [secondary_recipient],
                                    subject,
                                    html_body,
                                    attachments=attachments,
                                )
                                print(f"Secondary notification email sent to {secondary_recipient}")
                        elif primary_recipient or secondary_recipient:
                            recipients = [recipient for recipient in [primary_recipient, secondary_recipient] if recipient]
                            print(f"Email notification skipped for {', '.join(recipients)}: SMTP is not configured")
                        else:
                            print(f"Email notification skipped for file {file.storage_key}: no recipients configured")
                else:
                    print(result.stdout.decode('utf-8'))

def send_email(recipients, subject, html_body, attachments=None):
    app = create_app()
    with app.app_context():
        msg = Message(
            subject=subject,
            recipients=recipients,
            html=html_body
        )
        for file_path, attachment_name in attachments or []:
            with open(file_path, 'rb') as handle:
                mime_type = mimetypes.guess_type(attachment_name)[0] or 'application/octet-stream'
                msg.attach(attachment_name, mime_type, handle.read())
        mail.send(msg)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='List files in the SecureStamp database')
    parser.add_argument('-u', '--user', help='Filter by username')
    parser.add_argument('-s', '--status', help='Filter by status')
    args = parser.parse_args()

    list_files()

    update_files()
