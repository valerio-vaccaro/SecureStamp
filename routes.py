import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import User, File
from app import db
import subprocess
import uuid
import hashlib
from datetime import datetime

auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)

# Authentication routes
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists')
            return redirect(url_for('auth.register'))

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for('auth.login'))

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.locked:
                flash('Your account is locked. Please contact the administrator.', 'error')
                return redirect(url_for('auth.login'))
            
            login_user(user)
            return redirect(url_for('main.dashboard'))
        
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

# Main routes
@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    files = File.query.filter_by(user_id=current_user.id).order_by(File.uploaded_at.desc()).all()
    return render_template('dashboard.html', files=files)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'zip', 'gz', 'bz2'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'files' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)

        files = request.files.getlist('files')

        for file in files:
            if file.filename == '':
                flash('No selected file', 'error')
                continue

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)

                # create signature
                result = subprocess.run(['gpg', '--local-user', current_app.config['GPG_USER'], '--output', file_path+'.sig', '--detach-sign', file_path], stdout=subprocess.PIPE)
                print(result.stdout)

                # create timestamp
                result = subprocess.run(['ots-cli.js', 'stamp', file_path], stdout=subprocess.PIPE)
                print(result.stdout)

                new_file = File(
                    filename=unique_filename,
                    original_filename=filename,
                    user_id=current_user.id,
                    file_path=file_path,
                    status='Timestamp requested'  # Set initial status
                )
                db.session.add(new_file)
        
        db.session.commit()
        flash('Files uploaded successfully', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('upload.html')

@main_bp.route('/files')
@login_required
def files():
    user_files = File.query.filter_by(user_id=current_user.id).all()
    return render_template('files.html', files=user_files)

@main_bp.route('/files/<int:file_id>')
@login_required
def file_detail(file_id):
    file = File.query.get_or_404(file_id)
    if file.user_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Calculate file hash
    try:
        with open(file.file_path, 'rb') as f:
            file_content = f.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
    except Exception:
        file_hash = None
    
    return render_template('file_detail.html', file=file, file_hash=file_hash)

@main_bp.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    file = File.query.get_or_404(file_id)
    if file.user_id != current_user.id:
        abort(403)
    
    try:
        # Increment download counter
        file.file_downloads += 1
        db.session.commit()
        
        return send_file(
            file.file_path,
            as_attachment=True,
            download_name=file.original_filename
        )
    except FileNotFoundError:
        flash('File not found', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/download/timestamp/<int:file_id>')
@login_required
def download_timestamp(file_id):
    file = File.query.get_or_404(file_id)
    if file.user_id != current_user.id:
        abort(403)

    try:
        # Increment timestamp download counter
        file.timestamp_downloads += 1
        db.session.commit()
        
        return send_file(
            file.file_path+'.ots',
            as_attachment=True,
            download_name=file.original_filename+'.ots'
        )
    except FileNotFoundError:
        flash('File not found', 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/download/signature/<int:file_id>')
@login_required
def download_signature(file_id):
    file = File.query.get_or_404(file_id)
    if file.user_id != current_user.id:
        abort(403)

    try:
        # Increment signature download counter
        file.signature_downloads += 1
        db.session.commit()
        
        return send_file(
            file.file_path+'.sig',
            as_attachment=True,
            download_name=file.original_filename+'.sig'
        )
    except FileNotFoundError:
        flash('File not found', 'error')
        return redirect(url_for('main.dashboard'))