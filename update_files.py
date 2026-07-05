#!/usr/bin/env python3
import os
import subprocess
from datetime import datetime

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


def build_timestamp_completion_email(file, user):
    timestamp_path = f"{file.file_path}.ots"
    signature_path = f"{file.file_path}.sig"
    stats = [
        f"File name: {file.original_filename}",
        f"File ID: {file.id}",
        f"Status: {file.status}",
        f"Uploaded at (UTC): {file.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Confirmed at (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        f"File size: {get_file_size_string(file)}",
        f"Original file downloads: {file.file_downloads}",
        f"Timestamp proof downloads: {file.timestamp_downloads}",
        f"Signature downloads: {file.signature_downloads}",
        f"Timestamp proof present: {'Yes' if os.path.exists(timestamp_path) else 'No'}",
        f"Signature present: {'Yes' if os.path.exists(signature_path) else 'No'}",
    ]
    body = [
        f"Hello {user.username},",
        "",
        "SecureStamp has confirmed a timestamp for one of your files.",
        "",
        *stats,
        "",
        "This notification was generated because email notifications are enabled on your account.",
    ]
    return "\n".join(body)


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
                file.id,
                file.original_filename,
                user.username,
                file.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                size_str,
                file.status,
                sig_exists,
                ots_exists
            ])

        # Print table
        headers = ["ID", "Filename", "Owner", "Upload Date", "Size", "Status", "Signature", "Timestamp"]
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

                        if user.email_notifications and mail_enabled:
                            subject = "SecureStamp: Timestamp Completed"
                            body = build_timestamp_completion_email(file, user)
                            send_email(user.email, subject, body)
                            print(f"Notification email sent to {user.email}")
                        elif user.email_notifications:
                            print(f"Email notification skipped for {user.email}: SMTP is not configured")
                        else:
                            print(f"Email notification skipped for {user.email}")
                else:
                    print(result.stdout.decode('utf-8'))

def send_email(recipient, subject, body):
    app = create_app()
    with app.app_context():
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body
        )
        mail.send(msg)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='List files in the SecureStamp database')
    parser.add_argument('-u', '--user', help='Filter by username')
    parser.add_argument('-s', '--status', help='Filter by status')
    args = parser.parse_args()

    list_files()

    update_files()
