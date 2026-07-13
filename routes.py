import os
import secrets
from functools import wraps
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, abort, jsonify, g, session, Response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import User, File, Symbol, ApiToken
from app import db
import subprocess
import uuid
import hashlib
import os
import math
from email.utils import parseaddr
from datetime import datetime, timedelta
from i18n import LANGUAGES, normalize_language, set_language, translate

auth_bp = Blueprint('auth', __name__)
main_bp = Blueprint('main', __name__)

PUBLIC_INDEXABLE_ENDPOINTS = {
    'auth.login',
    'auth.register',
    'main.api_docs',
    'main.robots_txt',
    'main.sitemap_xml',
}

TOKEN_PERMISSION_PRESETS = {
    'full_access': {
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


def tr(key, **kwargs):
    return translate(key, **kwargs)


def get_valid_language_or_default(raw_language, default='en'):
    return normalize_language((raw_language or '').strip(), default=default)


def normalize_base_url(raw_url):
    if not raw_url:
        return None

    raw_url = raw_url.strip()
    if not raw_url:
        return None
    if not raw_url.startswith(('http://', 'https://')):
        raw_url = f'https://{raw_url}'
    return raw_url.rstrip('/')


def get_public_base_url():
    configured = normalize_base_url(current_app.config.get('PUBLIC_BASE_URL'))
    if configured:
        return configured
    return request.url_root.rstrip('/')


def build_canonical_url(path=None):
    base_url = get_public_base_url()
    path = path or request.path
    if not path.startswith('/'):
        path = f'/{path}'
    return f'{base_url}{path}'


def build_file_payload(file):
    return {
        'file_uuid': file.storage_key,
        'filename': file.filename,
        'original_filename': file.original_filename,
        'notification_email': file.notification_email,
        'notification_email_language': file.notification_email_language,
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


def build_public_urls():
    return [
        {
            'loc': build_canonical_url(url_for('auth.login')),
            'changefreq': 'weekly',
            'priority': '1.0',
        },
        {
            'loc': build_canonical_url(url_for('auth.register')),
            'changefreq': 'monthly',
            'priority': '0.8',
        },
        {
            'loc': build_canonical_url(url_for('main.api_docs')),
            'changefreq': 'weekly',
            'priority': '0.7',
        },
    ]


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
        return None, ('missing_token', tr('api.auth_required'))

    api_token = ApiToken.query.filter_by(token_hash=hash_api_token(raw_token)).first()
    if not api_token:
        return None, ('invalid_token', tr('api.invalid_token'))
    if api_token.locked:
        return None, ('locked_token', tr('api.locked_token'))
    if api_token.user.locked:
        return None, ('locked_user', tr('api.locked_user'))
    if api_token.max_hits is not None and api_token.hits >= api_token.max_hits:
        return None, ('max_hits_reached', tr('api.max_hits_reached'))

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


def token_permission_required(permission_attr, error_key='api.token_cannot_access_endpoint'):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            api_token = getattr(g, 'api_token', None)
            if api_token is not None and not getattr(api_token, permission_attr, False):
                return jsonify({'error': tr(error_key), 'code': 'insufficient_scope'}), 403
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def get_request_user():
    return getattr(g, 'request_user', current_user)


def normalize_optional_email(raw_email):
    raw_email = (raw_email or '').strip()
    if not raw_email:
        return None

    parsed_email = parseaddr(raw_email)[1]
    if not parsed_email or parsed_email != raw_email or '@' not in parsed_email:
        return None
    return parsed_email


def process_uploaded_files(uploaded_file_objects, user, notification_email=None, notification_email_language=None):
    uploaded_files = []
    notification_email = normalize_optional_email(notification_email)
    notification_email_language = (
        get_valid_language_or_default(notification_email_language, default='en')
        if notification_email
        else None
    )

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
                notification_email=notification_email,
                notification_email_language=notification_email_language,
                user_id=user.id,
                file_path=file_path,
                status='Timestamp requested'
            )
            db.session.add(new_file)
            uploaded_files.append({
                'file_uuid': new_file.storage_key,
                'name': filename,
                'notification_email': notification_email,
                'notification_email_language': notification_email_language,
                'status': 'success',
            })

    db.session.commit()
    return uploaded_files


@main_bp.route('/set-language', methods=['POST'])
def set_language_route():
    set_language(request.form.get('language', 'en'))
    next_url = request.form.get('next') or request.referrer or url_for('auth.login')
    if not next_url.startswith('/'):
        next_url = url_for('auth.login')
    return redirect(next_url)


@main_bp.after_app_request
def apply_search_headers(response):
    endpoint = request.endpoint or ''
    if endpoint in PUBLIC_INDEXABLE_ENDPOINTS:
        response.headers['X-Robots-Tag'] = 'index, follow'
    else:
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


@main_bp.route('/robots.txt')
def robots_txt():
    lines = [
        'User-agent: *',
        'Allow: /login',
        'Allow: /register',
        'Allow: /api/docs',
        'Disallow: /',
        'Disallow: /dashboard',
        'Disallow: /upload',
        'Disallow: /account',
        'Disallow: /tokens',
        'Disallow: /files',
        'Disallow: /download',
        'Disallow: /api/',
        'Disallow: /symbols-dashboard',
        f'Sitemap: {build_canonical_url("/sitemap.xml")}',
    ]
    return Response('\n'.join(lines) + '\n', mimetype='text/plain')


@main_bp.route('/sitemap.xml')
def sitemap_xml():
    urls = build_public_urls()
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for entry in urls:
        xml_lines.extend([
            '  <url>',
            f"    <loc>{entry['loc']}</loc>",
            f"    <changefreq>{entry['changefreq']}</changefreq>",
            f"    <priority>{entry['priority']}</priority>",
            '  </url>',
        ])
    xml_lines.append('</urlset>')
    return Response('\n'.join(xml_lines) + '\n', mimetype='application/xml')

# Authentication routes
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user:
            flash(tr('flash.username_exists'), 'error')
            return redirect(url_for('auth.register'))

        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash(tr('flash.email_exists'), 'error')
            return redirect(url_for('auth.register'))

        user = User(username=username, email=email, email_notifications=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return redirect(url_for('auth.login'))

    return render_template(
        'register.html',
        meta_title='SecureStamp Registration | Secure File Timestamping Access',
        meta_description='Request access to SecureStamp to manage signed files, Bitcoin timestamp proofs, and controlled verification workflows.',
        meta_robots='index, follow',
        canonical_url=build_canonical_url(url_for('auth.register')),
    )

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if user.locked:
                flash(tr('flash.account_locked'), 'error')
                return redirect(url_for('auth.login'))
            
            login_user(user)
            return redirect(url_for('main.dashboard'))
        
        flash(tr('flash.invalid_credentials'), 'error')
    return render_template(
        'login.html',
        service_stats=build_public_service_stats(),
        meta_title='SecureStamp | Secure File Timestamping and Evidence Management',
        meta_description='SecureStamp helps teams timestamp files, manage signed evidence packages, and verify document integrity with Bitcoin-based proofs.',
        meta_robots='index, follow',
        canonical_url=build_canonical_url(url_for('auth.login')),
    )

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
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = 100
    filename_query = (request.args.get('filename') or '').strip()
    status_filter = (request.args.get('status') or '').strip()
    date_from_raw = (request.args.get('date_from') or '').strip()
    date_to_raw = (request.args.get('date_to') or '').strip()

    filters = {
        'filename': filename_query,
        'status': status_filter,
        'date_from': date_from_raw,
        'date_to': date_to_raw,
    }

    status_options = [
        row[0]
        for row in db.session.query(File.status)
        .filter_by(user_id=current_user.id)
        .distinct()
        .order_by(File.status.asc())
        .all()
        if row[0]
    ]

    query = File.query.filter_by(user_id=current_user.id)
    total_files_count = query.count()

    if filename_query:
        query = query.filter(File.original_filename.ilike(f"%{filename_query}%"))

    if status_filter:
        query = query.filter(File.status == status_filter)

    invalid_filters = []

    if date_from_raw:
        try:
            date_from = datetime.strptime(date_from_raw, '%Y-%m-%d')
            query = query.filter(File.uploaded_at >= date_from)
        except ValueError:
            invalid_filters.append(tr('dashboard.filter_start_date'))

    if date_to_raw:
        try:
            date_to = datetime.strptime(date_to_raw, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(File.uploaded_at < date_to)
        except ValueError:
            invalid_filters.append(tr('dashboard.filter_end_date'))

    if invalid_filters:
        flash(tr('dashboard.invalid_filter_message', filters=', '.join(invalid_filters)), 'error')

    total_filtered_count = query.count()
    total_pages = max(1, math.ceil(total_filtered_count / per_page)) if total_filtered_count else 1
    page = min(page, total_pages)

    files = (
        query.order_by(File.uploaded_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    aggregate_row = query.with_entities(
        db.func.coalesce(db.func.sum(File.file_downloads), 0),
        db.func.coalesce(db.func.sum(File.timestamp_downloads), 0),
        db.func.coalesce(db.func.sum(File.signature_downloads), 0),
    ).first()

    pagination_params = {key: value for key, value in filters.items() if value}

    def build_dashboard_page_url(target_page):
        params = dict(pagination_params)
        params['page'] = target_page
        return url_for('main.dashboard', **params)

    pagination_window_start = max(1, page - 2)
    pagination_window_end = min(total_pages, page + 2)
    page_numbers = list(range(pagination_window_start, pagination_window_end + 1))

    return render_template(
        'dashboard.html',
        files=files,
        config=current_app.config,
        filters=filters,
        status_options=status_options,
        total_files_count=total_files_count,
        total_filtered_count=total_filtered_count,
        has_active_filters=any(filters.values()),
        current_page=page,
        per_page=per_page,
        total_pages=total_pages,
        page_numbers=page_numbers,
        prev_page_url=build_dashboard_page_url(page - 1) if page > 1 else None,
        next_page_url=build_dashboard_page_url(page + 1) if page < total_pages else None,
        page_urls={page_number: build_dashboard_page_url(page_number) for page_number in page_numbers},
        filtered_file_downloads=aggregate_row[0],
        filtered_timestamp_downloads=aggregate_row[1],
        filtered_signature_downloads=aggregate_row[2],
    )

def allowed_file(filename):
    return bool((filename or '').strip())

@main_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'files' not in request.files:
            return {'error': tr('api.no_file_part')}, 400

        files = request.files.getlist('files')
        notification_email = normalize_optional_email(request.form.get('notification_email'))
        if request.form.get('notification_email') and not notification_email:
            return {'error': tr('api.invalid_notification_email')}, 400
        raw_notification_email_language = request.form.get('notification_email_language')
        if raw_notification_email_language and raw_notification_email_language not in LANGUAGES:
            return {'error': tr('flash.invalid_language')}, 400
        notification_email_language = get_valid_language_or_default(
            raw_notification_email_language,
            default='en',
        )

        uploaded_files = process_uploaded_files(
            files,
            current_user,
            notification_email,
            notification_email_language,
        )
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {'files': uploaded_files}
        
        flash(tr('flash.files_uploaded'), 'success')
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
        email_notification_language = request.form.get('email_notification_language') or 'en'

        if email_notification_language not in LANGUAGES:
            flash(tr('flash.invalid_language'), 'error')
            return redirect(url_for('main.account_settings'))

        email_changed = email != current_user.email
        password_changed = bool(new_password or confirm_password)

        if not email:
            flash(tr('flash.email_required'), 'error')
            return redirect(url_for('main.account_settings'))

        if email_changed:
            existing_email = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing_email:
                flash(tr('flash.email_in_use'), 'error')
                return redirect(url_for('main.account_settings'))

        if password_changed:
            if new_password != confirm_password:
                flash(tr('flash.password_mismatch'), 'error')
                return redirect(url_for('main.account_settings'))
            if len(new_password) < 8:
                flash(tr('flash.password_too_short'), 'error')
                return redirect(url_for('main.account_settings'))

        if email_changed or password_changed:
            if not current_password:
                flash(tr('flash.current_password_required'), 'error')
                return redirect(url_for('main.account_settings'))
            if not current_user.check_password(current_password):
                flash(tr('flash.current_password_incorrect'), 'error')
                return redirect(url_for('main.account_settings'))

        current_user.email = email
        current_user.email_notifications = email_notifications
        current_user.email_notification_language = email_notification_language

        if password_changed:
            current_user.set_password(new_password)

        db.session.commit()
        flash(tr('flash.account_updated'), 'success')
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
            flash(tr('flash.token_name_required'), 'error')
            return redirect(url_for('main.manage_tokens'))

        if permission_preset not in TOKEN_PERMISSION_PRESETS:
            flash(tr('flash.invalid_token_preset'), 'error')
            return redirect(url_for('main.manage_tokens'))

        max_hits = None
        if max_hits_raw:
            try:
                max_hits = int(max_hits_raw)
            except ValueError:
                flash(tr('flash.max_hits_number'), 'error')
                return redirect(url_for('main.manage_tokens'))
            if max_hits < 1:
                flash(tr('flash.max_hits_min'), 'error')
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
        flash(tr('flash.token_created'), 'success')
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
    flash(
        tr(
            'flash.token_lock_updated',
            state=tr('flash.token_state_locked') if token.locked else tr('flash.token_state_unlocked'),
        ),
        'success',
    )
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
            flash(tr('flash.max_hits_number'), 'error')
            return redirect(url_for('main.manage_tokens'))

        if max_hits < 1:
            flash(tr('flash.max_hits_min'), 'error')
            return redirect(url_for('main.manage_tokens'))

        token.max_hits = max_hits

    db.session.commit()
    flash(tr('flash.token_hit_limit_updated'), 'success')
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
    flash(tr('flash.token_stats_reset'), 'success')
    return redirect(url_for('main.manage_tokens'))


@main_bp.route('/tokens/<int:token_id>/delete', methods=['POST'])
@login_required
def delete_token(token_id):
    token = ApiToken.query.get_or_404(token_id)
    if token.user_id != current_user.id:
        abort(403)

    db.session.delete(token)
    db.session.commit()
    flash(tr('flash.token_deleted'), 'success')
    return redirect(url_for('main.manage_tokens'))

@main_bp.route('/files')
@login_required
def files():
    user_files = File.query.filter_by(user_id=current_user.id).all()
    return render_template('files.html', files=user_files)

@main_bp.route('/files/<file_ref>', methods=['GET', 'POST'])
@login_required
def file_detail(file_ref):
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != current_user.id:
        flash(tr('flash.unauthorized_access'), 'error')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        if file.status == 'Timestamp completed':
            flash(tr('flash.external_email_locked'), 'error')
            return redirect(url_for('main.file_detail', file_ref=file.storage_key))

        raw_notification_email = request.form.get('notification_email')
        notification_email = normalize_optional_email(raw_notification_email)
        raw_notification_email_language = request.form.get('notification_email_language')
        if raw_notification_email_language and raw_notification_email_language not in LANGUAGES:
            flash(tr('flash.invalid_language'), 'error')
            return redirect(url_for('main.file_detail', file_ref=file.storage_key))
        notification_email_language = get_valid_language_or_default(
            raw_notification_email_language,
            default='en',
        )
        if raw_notification_email and not notification_email:
            flash(tr('flash.invalid_external_email'), 'error')
            return redirect(url_for('main.file_detail', file_ref=file.storage_key))

        file.notification_email = notification_email
        file.notification_email_language = notification_email_language if notification_email else None
        db.session.commit()
        flash(tr('flash.external_email_updated'), 'success')
        return redirect(url_for('main.file_detail', file_ref=file.storage_key))
    
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
@token_permission_required('can_list_files', 'api.token_cannot_list_files')
def api_files():
    user = get_request_user()
    files = File.query.filter_by(user_id=user.id).order_by(File.uploaded_at.desc()).all()
    return jsonify({'files': [build_file_payload(file) for file in files]})


@main_bp.route('/api/files/upload', methods=['POST'])
@api_auth_required
@token_permission_required('can_upload_files', 'api.token_cannot_upload')
def api_upload_files():
    if 'files' not in request.files:
        return jsonify({'error': tr('api.no_file_part')}), 400

    user = get_request_user()
    notification_email = normalize_optional_email(request.form.get('notification_email'))
    if request.form.get('notification_email') and not notification_email:
        return jsonify({'error': tr('api.invalid_notification_email')}), 400
    raw_notification_email_language = request.form.get('notification_email_language')
    if raw_notification_email_language and raw_notification_email_language not in LANGUAGES:
        return jsonify({'error': tr('flash.invalid_language')}), 400
    notification_email_language = get_valid_language_or_default(
        raw_notification_email_language,
        default='en',
    )

    files = request.files.getlist('files')
    uploaded_files = process_uploaded_files(files, user, notification_email, notification_email_language)
    return jsonify({'files': uploaded_files})


@main_bp.route('/api/files/<file_ref>/download', methods=['GET'])
@api_auth_required
@token_permission_required('can_download_files', 'api.token_cannot_download_files')
def api_download_file(file_ref):
    user = get_request_user()
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != user.id:
        return jsonify({'error': tr('api.forbidden')}), 403

    try:
        file.file_downloads += 1
        db.session.commit()
        return send_file(file.file_path, as_attachment=True, download_name=file.original_filename)
    except FileNotFoundError:
        return jsonify({'error': tr('api.file_not_found')}), 404


@main_bp.route('/api/files/<file_ref>/timestamp', methods=['GET'])
@api_auth_required
@token_permission_required('can_download_timestamps', 'api.token_cannot_download_timestamps')
def api_download_timestamp(file_ref):
    user = get_request_user()
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != user.id:
        return jsonify({'error': tr('api.forbidden')}), 403

    try:
        file.timestamp_downloads += 1
        db.session.commit()
        return send_file(file.file_path + '.ots', as_attachment=True, download_name=file.original_filename + '.ots')
    except FileNotFoundError:
        return jsonify({'error': tr('api.file_not_found')}), 404


@main_bp.route('/api/files/<file_ref>/signature', methods=['GET'])
@api_auth_required
@token_permission_required('can_download_signatures', 'api.token_cannot_download_signatures')
def api_download_signature(file_ref):
    user = get_request_user()
    file = get_file_by_reference(file_ref)
    if not file:
        abort(404)
    if file.user_id != user.id:
        return jsonify({'error': tr('api.forbidden')}), 403

    try:
        file.signature_downloads += 1
        db.session.commit()
        return send_file(file.file_path + '.sig', as_attachment=True, download_name=file.original_filename + '.sig')
    except FileNotFoundError:
        return jsonify({'error': tr('api.file_not_found')}), 404

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
        flash(tr('flash.file_not_found'), 'error')
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
        flash(tr('flash.file_not_found'), 'error')
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
        flash(tr('flash.file_not_found'), 'error')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/api/docs')
def api_docs():
    """Swagger UI page documenting all API endpoints"""
    return render_template(
        'swagger.html',
        meta_title='SecureStamp API Documentation',
        meta_description='Explore the SecureStamp API for file uploads, timestamp retrieval, signed artifacts, and token-based automation workflows.',
        meta_robots='index, follow',
        canonical_url=build_canonical_url(url_for('main.api_docs')),
    )

@main_bp.route('/symbols-dashboard')
@login_required
def symbols_dashboard():
    """Web page for managing symbols"""
    symbols = Symbol.query.filter_by(user_id=current_user.id).order_by(Symbol.created_at.desc()).all()
    return render_template('symbols.html', symbols=symbols)

@main_bp.route('/api/symbols', methods=['POST'])
@api_auth_required
@token_permission_required('can_manage_symbols', 'api.token_cannot_manage_symbols_create')
def register_symbol():
    try:
        user = get_request_user()
        data = request.get_json()
        if not data:
            return jsonify({'error': tr('api.no_data_provided')}), 400

        # Validate required fields
        required_fields = ['name', 'description']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': tr('api.missing_required_field', field=field)}), 400

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
            'message': tr('api.symbol_registered'),
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
@token_permission_required('can_manage_symbols', 'api.token_cannot_manage_symbols_delete')
def delete_symbol(symbol_id):
    user = get_request_user()
    symbol = Symbol.query.get_or_404(symbol_id)
    if symbol.user_id != user.id:
        return jsonify({'error': tr('api.forbidden')}), 403

    db.session.delete(symbol)
    db.session.commit()
    return jsonify({'message': tr('api.symbol_deleted')})
