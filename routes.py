import os
import secrets
from functools import wraps
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, abort, jsonify, g, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import User, File, Symbol, ApiToken
from app import db
import subprocess
import uuid
import hashlib
import os
from datetime import datetime

auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)

TOKEN_PERMISSION_PRESETS = {
    'full_access': {
        'label': 'Full API access',
        'permissions': {
            'can_list_files': True,
            'can_upload_files': True,
            'can_download_files': True,
            'can_download_timestamps': True,
            'can_download_signatures': True,
            'can_manage_symbols': True,
        },
    },
    'upload_and_timestamp_only': {
        'label': 'Upload and timestamp only',
        'permissions': {
            'can_list_files': False,
            'can_upload_files': True,
            'can_download_files': False,
            'can_download_timestamps': False,
            'can_download_signatures': False,
            'can_manage_symbols': False,
        },
    },
}


def hash_api_token(raw_token):
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def extract_bearer_token():
    authorization = request.headers.get('Authorization', '')
    if authorization.startswith('Bearer '):
        return authorization.split(' ', 1)[1].strip()
    return None


def build_file_payload(file):
    return {
        'file_uuid': file.storage_key,
        'filename': file.filename,
        'original_filename': file.original_filename,
        'uploaded_at': file.uploaded_at.isoformat(),
        'status': file.status,
        'file_downloads': file.file_downloads,
        'timestamp_downloads': file.timestamp_downloads,
        'signature_downloads': file.signature_downloads,
    }


def build_public_service_stats():
    return {
        'users': User.query.count(),
        'files': File.query.count(),
        'completed_timestamps': File.query.filter_by(status='Timestamp completed').count(),
        'pending_timestamps': File.query.filter_by(status='Timestamp requested').count(),
        'downloads': db.session.query(
            db.func.coalesce(
                db.func.sum(File.file_downloads + File.timestamp_downloads + File.signature_downloads),
                0,
            )
        ).scalar(),
    }


def get_file_by_reference(file_ref):
    extension = os.path.splitext(file_ref)[1]
    if extension:
        return File.query.filter_by(filename=file_ref).first()

    return File.query.filter(File.filename.like(f"{file_ref}.%")).first()


def resolve_api_user():
    if current_user.is_authenticated:
        g.request_user = current_user
        g.api_token = None
        return current_user, None

    raw_token = extract_bearer_token()
    if not raw_token:
        return None, ('missing_token', 'Authentication required.')

    api_token = ApiToken.query.filter_by(token_hash=hash_api_token(raw_token)).first()
    if not api_token:
        return None, ('invalid_token', 'Invalid API token.')
    if api_token.locked:
        return None, ('locked_token', 'API token is locked.')
    if api_token.user.locked:
        return None, ('locked_user', 'Token owner account is locked.')
    if api_token.max_hits is not None and api_token.hits >= api_token.max_hits:
        return None, ('max_hits_reached', 'API token hit limit reached.')

    now = datetime.utcnow()
    api_token.hits += 1
    if api_token.first_used_at is None:
        api_token.first_used_at = now
    api_token.last_used_at = now
    db.session.commit()

    g.request_user = api_token.user
    g.api_token = api_token
    return api_token.user, None


def api_auth_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user, error = resolve_api_user()
        if not user:
            return jsonify({'error': error[1], 'code': error[0]}), 401
        return view_func(*args, **kwargs)
    return wrapped


def token_permission_required(permission_attr, error_message='This token cannot access this endpoint.'):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            api_token = getattr(g, 'api_token', None)
            if api_token is not None and not getattr(api_token, permission_attr, False):
                return jsonify({'error': error_message, 'code': 'insufficient_scope'}), 403
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def get_request_user():
    return getattr(g, 'request_user', current_user)


def process_uploaded_files(uploaded_file_objects, user):
    uploaded_files = []

    for file in uploaded_file_objects:
        if file.filename == '':
            continue

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            extension = os.path.splitext(filename)[1].lower()
            unique_filename = f"{uuid.uuid4()}{extension}"
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)

            subprocess.run(
                ['gpg', '--local-user', current_app.config['GPG_USER'], '--output', file_path + '.sig', '--detach-sign', file_path],
                stdout=subprocess.PIPE
            )
            subprocess.run(['ots-cli.js', 'stamp', file_path], stdout=subprocess.PIPE)

            new_file = File(
                filename=unique_filename,
                original_filename=filename,
                user_id=user.id,
                file_path=file_path,
                status='Timestamp requested'
            )
            db.session.add(new_file)
            uploaded_files.append({
                'file_uuid': new_file.storage_key,
                'name': filename,
                'status': 'success',
            })

    db.session.commit()
    return uploaded_files

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

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Email already exists', 'error')
            return redirect(url_for('auth.register'))

        user = User(username=username, email=email, email_notifications=True)
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
    return render_template('login.html', service_stats=build_public_service_stats())

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
    return render_template('dashboard.html', files=files, config=current_app.config)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'zip', 'gz', 'bz2'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'files' not in request.files:
            return {'error': 'No file part'}, 400

        files = request.files.getlist('files')
        uploaded_files = process_uploaded_files(files, current_user)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {'files': uploaded_files}
        
        flash('Files uploaded successfully', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('upload.html')

@main_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account_settings():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''
        email_notifications = request.form.get('email_notifications') == 'on'

        email_changed = email != current_user.email
        password_changed = bool(new_password or confirm_password)

        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('main.account_settings'))

        if email_changed:
            existing_email = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing_email:
                flash('That email address is already in use.', 'error')
                return redirect(url_for('main.account_settings'))

        if password_changed:
            if new_password != confirm_password:
                flash('New password and confirmation do not match.', 'error')
                return redirect(url_for('main.account_settings'))
            if len(new_password) < 8:
                flash('New password must be at least 8 characters long.', 'error')
                return redirect(url_for('main.account_settings'))

        if email_changed or password_changed:
            if not current_password:
                flash('Current password is required to change email or password.', 'error')
                return redirect(url_for('main.account_settings'))
            if not current_user.check_password(current_password):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('main.account_settings'))

        current_user.email = email
        current_user.email_notifications = email_notifications

        if password_changed:
            current_user.set_password(new_password)

        db.session.commit()
        flash('Account settings updated successfully.', 'success')
        return redirect(url_for('main.account_settings'))

    return render_template('account.html')


@main_bp.route('/tokens', methods=['GET', 'POST'])
@login_required
def manage_tokens():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        max_hits_raw = (request.form.get('max_hits') or '').strip()
        permission_preset = request.form.get('permission_preset') or 'full_access'

        if not name:
            flash('Token name is required.', 'error')
            return redirect(url_for('main.manage_tokens'))

        if permission_preset not in TOKEN_PERMISSION_PRESETS:
            flash('Invalid token permission preset.', 'error')
            return redirect(url_for('main.manage_tokens'))

        max_hits = None
        if max_hits_raw:
            try:
                max_hits = int(max_hits_raw)
            except ValueError:
                flash('Maximum hits must be a number.', 'error')
                return redirect(url_for('main.manage_tokens'))
            if max_hits < 1:
                flash('Maximum hits must be at least 1.', 'error')
                return redirect(url_for('main.manage_tokens'))

        raw_token = secrets.token_urlsafe(32)
        new_token = ApiToken(
            name=name,
            token_hash=hash_api_token(raw_token),
            token_prefix=raw_token[:12],
            user_id=current_user.id,
            max_hits=max_hits,
            **TOKEN_PERMISSION_PRESETS[permission_preset]['permissions'],
        )
        db.session.add(new_token)
        db.session.commit()

        session['new_api_token_value'] = raw_token
        flash('Authorization token created successfully.', 'success')
        return redirect(url_for('main.manage_tokens'))

    tokens = ApiToken.query.filter_by(user_id=current_user.id).order_by(ApiToken.created_at.desc()).all()
    new_token_value = session.pop('new_api_token_value', None)
    return render_template(
        'tokens.html',
        tokens=tokens,
        new_token_value=new_token_value,
        token_permission_presets=TOKEN_PERMISSION_PRESETS,
    )


@main_bp.route('/tokens/<int:token_id>/toggle-lock', methods=['POST'])
@login_required
def toggle_token_lock(token_id):
    token = ApiToken.query.get_or_404(token_id)
    if token.user_id != current_user.id:
        abort(403)

    token.locked = not token.locked
    db.session.commit()
    flash(f'Token { "locked" if token.locked else "unlocked" } successfully.', 'success')
    return redirect(url_for('main.manage_tokens'))


@main_bp.route('/tokens/<int:token_id>/max-hits', methods=['POST'])
@login_required
def update_token_max_hits(token_id):
    token = ApiToken.query.get_or_404(token_id)
    if token.user_id != current_user.id:
        abort(403)

    max_hits_raw = (request.form.get('max_hits') or '').strip()
    if not max_hits_raw:
        token.max_hits = None
    else:
        try:
            max_hits = int(max_hits_raw)
        except ValueError:
            flash('Maximum hits must be a number.', 'error')
            return redirect(url_for('main.manage_tokens'))

        if max_hits < 1:
            flash('Maximum hits must be at least 1.', 'error')
            return redirect(url_for('main.manage_tokens'))

        token.max_hits = max_hits

    db.session.commit()
    flash('Token hit limit updated successfully.', 'success')
    return redirect(url_for('main.manage_tokens'))


@main_bp.route('/tokens/<int:token_id>/reset-stats', methods=['POST'])
@login_required
def reset_token_stats(token_id):
    token = ApiToken.query.get_or_404(token_id)
    if token.user_id != current_user.id:
        abort(403)

    token.hits = 0
    token.first_used_at = None
    token.last_used_at = None
    db.session.commit()
    flash('Token statistics reset successfully.', 'success')
    return redirect(url_for('main.manage_tokens'))


@main_bp.route('/tokens/<int:token_id>/delete', methods=['POST'])
@login_required
def delete_token(token_id):
    token = ApiToken.query.get_or_404(token_id)
    if token.user_id != current_user.id:
        abort(403)

    db.session.delete(token)
    db.session.commit()
    flash('Token deleted successfully.', 'success')
    return redirect(url_for('main.manage_tokens'))

@main_bp.route('/files')
@login_required
def files():
    user_files = File.query.filter_by(user_id=current_user.id).all()
    return render_template('files.html', files=user_files)

@main_bp.route('/files/<file_ref>')
@login_required
def file_detail(file_ref):
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
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


@main_bp.route('/api/files', methods=['GET'])
@api_auth_required
@token_permission_required('can_list_files', 'This token cannot list files.')
def api_files():
    user = get_request_user()
    files = File.query.filter_by(user_id=user.id).order_by(File.uploaded_at.desc()).all()
    return jsonify({'files': [build_file_payload(file) for file in files]})


@main_bp.route('/api/files/upload', methods=['POST'])
@api_auth_required
@token_permission_required('can_upload_files', 'This token cannot upload files or create timestamps.')
def api_upload_files():
    if 'files' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    user = get_request_user()
    files = request.files.getlist('files')
    uploaded_files = process_uploaded_files(files, user)
    return jsonify({'files': uploaded_files})


@main_bp.route('/api/files/<file_ref>/download', methods=['GET'])
@api_auth_required
@token_permission_required('can_download_files', 'This token cannot download original files.')
def api_download_file(file_ref):
    user = get_request_user()
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403

    try:
        file.file_downloads += 1
        db.session.commit()
        return send_file(file.file_path, as_attachment=True, download_name=file.original_filename)
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404


@main_bp.route('/api/files/<file_ref>/timestamp', methods=['GET'])
@api_auth_required
@token_permission_required('can_download_timestamps', 'This token cannot download timestamp proofs.')
def api_download_timestamp(file_ref):
    user = get_request_user()
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403

    try:
        file.timestamp_downloads += 1
        db.session.commit()
        return send_file(file.file_path + '.ots', as_attachment=True, download_name=file.original_filename + '.ots')
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404


@main_bp.route('/api/files/<file_ref>/signature', methods=['GET'])
@api_auth_required
@token_permission_required('can_download_signatures', 'This token cannot download signatures.')
def api_download_signature(file_ref):
    user = get_request_user()
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403

    try:
        file.signature_downloads += 1
        db.session.commit()
        return send_file(file.file_path + '.sig', as_attachment=True, download_name=file.original_filename + '.sig')
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404

@main_bp.route('/download/<file_ref>')
@login_required
def download_file(file_ref):
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
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

@main_bp.route('/download/timestamp/<file_ref>')
@login_required
def download_timestamp(file_ref):
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
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

@main_bp.route('/download/signature/<file_ref>')
@login_required
def download_signature(file_ref):
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
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

@main_bp.route('/api/docs')
def api_docs():
    """Swagger UI page documenting all API endpoints"""
    return render_template('swagger.html')

@main_bp.route('/symbols-dashboard')
@login_required
def symbols_dashboard():
    """Web page for managing symbols"""
    symbols = Symbol.query.filter_by(user_id=current_user.id).order_by(Symbol.created_at.desc()).all()
    return render_template('symbols.html', symbols=symbols)

@main_bp.route('/api/symbols', methods=['POST'])
@api_auth_required
@token_permission_required('can_manage_symbols', 'This token cannot create symbols.')
def register_symbol():
    try:
        user = get_request_user()
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Validate required fields
        required_fields = ['name', 'description']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        # Create new symbol
        new_symbol = Symbol(
            name=data['name'],
            description=data.get('description', ''),
            user_id=user.id,
            created_at=datetime.utcnow()
        )

        db.session.add(new_symbol)
        db.session.commit()

        # Return data in format matching the table structure
        return jsonify({
            'message': 'Symbol registered successfully',
            'symbol': {
                'id': new_symbol.id,
                'name': new_symbol.name,
                'description': new_symbol.description,
                'created_at': new_symbol.created_at.strftime('%Y-%m-%d %H:%M'),
                'user_id': new_symbol.user_id
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@main_bp.route('/api/symbols/<int:symbol_id>', methods=['DELETE'])
@api_auth_required
@token_permission_required('can_manage_symbols', 'This token cannot delete symbols.')
def delete_symbol(symbol_id):
    user = get_request_user()
    symbol = Symbol.query.get_or_404(symbol_id)
    if symbol.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403

    db.session.delete(symbol)
    db.session.commit()
    return jsonify({'message': 'Symbol deleted successfully'})
