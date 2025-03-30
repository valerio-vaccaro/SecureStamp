#!/usr/bin/env python3
from app import create_app, db
from models import File, User
from tabulate import tabulate
from datetime import datetime
import subprocess

def format_size(size):
    """Convert size in bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"

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
            try:
                file_size = os.path.getsize(file.file_path)
                size_str = format_size(file_size)
            except:
                size_str = "N/A"

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
        # Get all files with their owners
        files = db.session.query(File, User).join(User).all()
        
        if not files:
            print("No files found in database")
            return

        from config import Config

        for file, user in files:
            if file.status == 'Timestamp requested':
                print(f"Checking status of file {file.file_path}")
                result = subprocess.run(['ots-cli.js', 'upgrade', file.file_path+'.ots'], stdout=subprocess.PIPE)
                if result.returncode == 0:
                    res = result.stdout.decode('utf-8')
                    print(res)
                    if res.find("Success! Timestamp complete") != -1:
                        print(f"Timestamp completed for file {file.file_path}!!!")
                        file.status = 'Timestamp completed'
                        db.session.commit()

if __name__ == "__main__":
    import os
    import argparse

    parser = argparse.ArgumentParser(description='List files in the SecureStamp database')
    parser.add_argument('-u', '--user', help='Filter by username')
    parser.add_argument('-s', '--status', help='Filter by status')
    args = parser.parse_args()

    list_files()

    update_files()
