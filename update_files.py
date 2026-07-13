#!/usr/bin/env python3
import os
import re
import subprocess
import hashlib
import mimetypes
from datetime import datetime, timedelta, timezone

from flask import render_template
from flask_mail import Message

from app import create_app, db, mail
from models import File, User
from i18n import normalize_language
from tabulate import tabulate


EMAIL_TRANSLATIONS = {
    'en': {
        'subject': "SecureStamp.it: Timestamp completed {filename}",
        'status_timestamp_completed': "Timestamp completed",
        'title': "Timestamp Completed",
        'hero_title': "Timestamp completed",
        'hero_subtitle_primary': "The timestamp for {filename} has been confirmed.",
        'hero_subtitle_secondary': "The file, detached signature, and completed timestamp proof are attached to this email.",
        'hello_user': "Hello {username},",
        'hello_generic': "Hello,",
        'body_primary': "SecureStamp.it has completed the timestamping workflow for your uploaded file. The record details are below.",
        'body_secondary': "SecureStamp.it has completed the timestamping workflow for {filename}. This message includes the original file, the detached signature, and the completed OpenTimestamps proof as attachments.",
        'protect_note': "To protect access to your evidence package, the links in this email work only after you log in to the SecureStamp.it platform with your account.",
        'file_name': "File name",
        'file_uuid': "File UUID",
        'status': "Status",
        'uploaded_at': "Uploaded at (UTC)",
        'confirmed_at': "Confirmed at (UTC)",
        'time_to_confirmation': "Time to confirmation",
        'file_size': "File size",
        'sha256_hash': "SHA256 hash",
        'not_available': "Not available",
        'actions_title': "Available actions",
        'actions_body': "After signing in, you can download the original file, retrieve the completed timestamp proof, and inspect the timestamp record details from your SecureStamp.it workspace.",
        'download_file': "Download file",
        'download_proof': "Download completed proof",
        'see_details': "See timestamp details",
        'login_hint_prefix': "If you are not logged in yet, open ",
        'login_hint_link': "the SecureStamp.it login page",
        'login_hint_suffix': " first, then return to the links above.",
        'login_hint_no_link': "If the action links do not open directly, log in to SecureStamp.it first and then access this file from your dashboard.",
        'primary_footer': "This notification was generated because email notifications are enabled on your account.",
        'secondary_footer': "This is an attachment-only confirmation email for the additional recipient configured at upload time.",
    },
    'it': {
        'subject': "SecureStamp.it: Timestamp completato {filename}",
        'status_timestamp_completed': "Timestamp completato",
        'title': "Timestamp completato",
        'hero_title': "Timestamp completato",
        'hero_subtitle_primary': "Il timestamp per {filename} e stato confermato.",
        'hero_subtitle_secondary': "Il file, la firma separata e la prova timestamp completata sono allegati a questa email.",
        'hello_user': "Ciao {username},",
        'hello_generic': "Ciao,",
        'body_primary': "SecureStamp.it ha completato il flusso di timestamp per il file che hai caricato. I dettagli del record sono riportati sotto.",
        'body_secondary': "SecureStamp.it ha completato il flusso di timestamp per {filename}. Questo messaggio include in allegato il file originale, la firma separata e la prova OpenTimestamps completata.",
        'protect_note': "Per proteggere l'accesso al tuo pacchetto di prove, i link in questa email funzionano solo dopo aver effettuato l'accesso alla piattaforma SecureStamp.it con il tuo account.",
        'file_name': "Nome file",
        'file_uuid': "UUID file",
        'status': "Stato",
        'uploaded_at': "Caricato il (UTC)",
        'confirmed_at': "Confermato il (UTC)",
        'time_to_confirmation': "Tempo al completamento",
        'file_size': "Dimensione file",
        'sha256_hash': "Hash SHA256",
        'not_available': "Non disponibile",
        'actions_title': "Azioni disponibili",
        'actions_body': "Dopo l'accesso puoi scaricare il file originale, recuperare la prova timestamp completata e consultare i dettagli del record dal tuo spazio SecureStamp.it.",
        'download_file': "Scarica file",
        'download_proof': "Scarica prova completata",
        'see_details': "Vedi dettagli timestamp",
        'login_hint_prefix': "Se non hai ancora effettuato l'accesso, apri ",
        'login_hint_link': "la pagina di login di SecureStamp.it",
        'login_hint_suffix': " e poi torna ai link qui sopra.",
        'login_hint_no_link': "Se i link di azione non si aprono direttamente, accedi prima a SecureStamp.it e poi raggiungi questo file dalla dashboard.",
        'primary_footer': "Questa notifica e stata generata perche le notifiche email sono abilitate sul tuo account.",
        'secondary_footer': "Questa e una email di conferma con soli allegati per il destinatario aggiuntivo configurato al momento del caricamento.",
    },
}


STATUS_TRANSLATIONS = {
    'en': {
        'Timestamp completed': "Timestamp completed",
        'Timestamp requested': "Timestamp requested",
        'Error': "Error",
    },
    'it': {
        'Timestamp completed': "Timestamp completato",
        'Timestamp requested': "Timestamp richiesto",
        'Error': "Errore",
    },
}


for code, updates in {
    'es': {
        'subject': "SecureStamp.it: Marca de tiempo completada {filename}",
        'title': "Marca de tiempo completada",
        'hero_title': "Marca de tiempo completada",
        'hero_subtitle_primary': "La marca de tiempo de {filename} ha sido confirmada.",
        'hero_subtitle_secondary': "El archivo, la firma separada y la prueba de marca de tiempo completada estan adjuntos a este correo.",
        'hello_user': "Hola {username},",
        'hello_generic': "Hola,",
        'body_primary': "SecureStamp.it ha completado el flujo de marcado temporal de tu archivo cargado. Los detalles del registro estan abajo.",
        'body_secondary': "SecureStamp.it ha completado el flujo de marcado temporal de {filename}. Este mensaje incluye el archivo original, la firma separada y la prueba OpenTimestamps completada como adjuntos.",
        'protect_note': "Para proteger el acceso a tu paquete de evidencias, los enlaces de este correo funcionan solo despues de iniciar sesion en la plataforma SecureStamp.it con tu cuenta.",
        'file_name': "Nombre del archivo",
        'file_uuid': "UUID del archivo",
        'uploaded_at': "Subido el (UTC)",
        'confirmed_at': "Confirmado el (UTC)",
        'time_to_confirmation': "Tiempo hasta la confirmacion",
        'file_size': "Tamano del archivo",
        'actions_title': "Acciones disponibles",
        'actions_body': "Despues de iniciar sesion puedes descargar el archivo original, recuperar la prueba completada y revisar los detalles del registro en SecureStamp.it.",
        'download_file': "Descargar archivo",
        'download_proof': "Descargar prueba completada",
        'see_details': "Ver detalles",
        'login_hint_link': "la pagina de inicio de sesion de SecureStamp.it",
        'primary_footer': "Esta notificacion se genero porque las notificaciones por correo estan habilitadas en tu cuenta.",
        'secondary_footer': "Este es un correo de confirmacion solo con adjuntos para el destinatario adicional configurado durante la carga.",
    },
    'pt': {
        'subject': "SecureStamp.it: Timestamp concluido {filename}",
        'title': "Timestamp concluido",
        'hero_title': "Timestamp concluido",
        'hero_subtitle_primary': "O timestamp de {filename} foi confirmado.",
        'hero_subtitle_secondary': "O arquivo, a assinatura destacada e a prova de timestamp concluida estao anexados a este email.",
        'hello_user': "Ola {username},",
        'hello_generic': "Ola,",
        'body_primary': "O SecureStamp.it concluiu o fluxo de timestamp para o arquivo enviado. Os detalhes do registro estao abaixo.",
        'body_secondary': "O SecureStamp.it concluiu o fluxo de timestamp para {filename}. Esta mensagem inclui o arquivo original, a assinatura destacada e a prova OpenTimestamps concluida em anexo.",
        'protect_note': "Para proteger o acesso ao seu pacote de evidencias, os links deste email funcionam somente depois de entrar na plataforma SecureStamp.it com sua conta.",
        'file_name': "Nome do arquivo",
        'file_uuid': "UUID do arquivo",
        'uploaded_at': "Enviado em (UTC)",
        'confirmed_at': "Confirmado em (UTC)",
        'time_to_confirmation': "Tempo ate a confirmacao",
        'file_size': "Tamanho do arquivo",
        'actions_title': "Acoes disponiveis",
        'actions_body': "Depois de entrar, voce pode baixar o arquivo original, obter a prova concluida e consultar os detalhes do registro no SecureStamp.it.",
        'download_file': "Baixar arquivo",
        'download_proof': "Baixar prova concluida",
        'see_details': "Ver detalhes",
        'login_hint_link': "a pagina de login do SecureStamp.it",
        'primary_footer': "Esta notificacao foi gerada porque as notificacoes por email estao ativadas na sua conta.",
        'secondary_footer': "Este e um email de confirmacao somente com anexos para o destinatario adicional configurado no envio.",
    },
    'fr': {
        'subject': "SecureStamp.it : Horodatage termine {filename}",
        'title': "Horodatage termine",
        'hero_title': "Horodatage termine",
        'hero_subtitle_primary': "L'horodatage de {filename} a ete confirme.",
        'hero_subtitle_secondary': "Le fichier, la signature detachee et la preuve d'horodatage terminee sont joints a cet email.",
        'hello_user': "Bonjour {username},",
        'hello_generic': "Bonjour,",
        'body_primary': "SecureStamp.it a termine le flux d'horodatage pour votre fichier televerse. Les details de l'enregistrement sont ci-dessous.",
        'body_secondary': "SecureStamp.it a termine le flux d'horodatage pour {filename}. Ce message inclut le fichier original, la signature detachee et la preuve OpenTimestamps terminee en pieces jointes.",
        'protect_note': "Pour proteger l'acces a votre dossier de preuves, les liens de cet email fonctionnent seulement apres connexion a la plateforme SecureStamp.it avec votre compte.",
        'file_name': "Nom du fichier",
        'file_uuid': "UUID du fichier",
        'uploaded_at': "Televerse le (UTC)",
        'confirmed_at': "Confirme le (UTC)",
        'time_to_confirmation': "Temps jusqu'a confirmation",
        'file_size': "Taille du fichier",
        'actions_title': "Actions disponibles",
        'actions_body': "Apres connexion, vous pouvez telecharger le fichier original, recuperer la preuve terminee et consulter les details sur SecureStamp.it.",
        'download_file': "Telecharger le fichier",
        'download_proof': "Telecharger la preuve",
        'see_details': "Voir les details",
        'login_hint_link': "la page de connexion SecureStamp.it",
        'primary_footer': "Cette notification a ete generee car les notifications email sont activees sur votre compte.",
        'secondary_footer': "Ceci est un email de confirmation avec pieces jointes uniquement pour le destinataire additionnel configure lors du televersement.",
    },
    'de': {
        'subject': "SecureStamp.it: Zeitstempel abgeschlossen {filename}",
        'title': "Zeitstempel abgeschlossen",
        'hero_title': "Zeitstempel abgeschlossen",
        'hero_subtitle_primary': "Der Zeitstempel fur {filename} wurde bestaetigt.",
        'hero_subtitle_secondary': "Die Datei, die abgetrennte Signatur und der abgeschlossene Zeitstempel-Nachweis sind an diese E-Mail angehaengt.",
        'hello_user': "Hallo {username},",
        'hello_generic': "Hallo,",
        'body_primary': "SecureStamp.it hat den Zeitstempel-Ablauf fur Ihre hochgeladene Datei abgeschlossen. Die Datensatzdetails finden Sie unten.",
        'body_secondary': "SecureStamp.it hat den Zeitstempel-Ablauf fur {filename} abgeschlossen. Diese Nachricht enthalt die Originaldatei, die abgetrennte Signatur und den abgeschlossenen OpenTimestamps-Nachweis als Anhang.",
        'protect_note': "Zum Schutz Ihres Nachweispakets funktionieren die Links in dieser E-Mail erst, nachdem Sie sich mit Ihrem Konto bei SecureStamp.it angemeldet haben.",
        'file_name': "Dateiname",
        'file_uuid': "Datei-UUID",
        'uploaded_at': "Hochgeladen am (UTC)",
        'confirmed_at': "Bestaetigt am (UTC)",
        'time_to_confirmation': "Zeit bis zur Bestaetigung",
        'file_size': "Dateigrosse",
        'actions_title': "Verfugbare Aktionen",
        'actions_body': "Nach der Anmeldung konnen Sie die Originaldatei herunterladen, den abgeschlossenen Nachweis abrufen und die Details in SecureStamp.it ansehen.",
        'download_file': "Datei herunterladen",
        'download_proof': "Nachweis herunterladen",
        'see_details': "Details ansehen",
        'login_hint_link': "die SecureStamp.it-Anmeldeseite",
        'primary_footer': "Diese Benachrichtigung wurde erstellt, weil E-Mail-Benachrichtigungen fur Ihr Konto aktiviert sind.",
        'secondary_footer': "Dies ist eine reine Anhangs-Bestatigung fur den zusatzlichen Empfanger aus dem Upload.",
    },
    'ru': {
        'subject': "SecureStamp.it: Метка времени завершена {filename}",
        'title': "Метка времени завершена",
        'hero_title': "Метка времени завершена",
        'hero_subtitle_primary': "Метка времени для {filename} подтверждена.",
        'hero_subtitle_secondary': "Файл, отделенная подпись и завершенное доказательство отметки времени приложены к этому письму.",
        'hello_user': "Здравствуйте, {username},",
        'hello_generic': "Здравствуйте,",
        'body_primary': "SecureStamp.it завершил процесс отметки времени для вашего загруженного файла. Ниже приведены детали записи.",
        'body_secondary': "SecureStamp.it завершил процесс отметки времени для {filename}. Это письмо содержит исходный файл, отделенную подпись и завершенное доказательство OpenTimestamps во вложениях.",
        'protect_note': "Чтобы защитить доступ к вашему пакету доказательств, ссылки в этом письме работают только после входа в SecureStamp.it под вашей учетной записью.",
        'file_name': "Имя файла",
        'file_uuid': "UUID файла",
        'uploaded_at': "Загружен (UTC)",
        'confirmed_at': "Подтвержден (UTC)",
        'time_to_confirmation': "Время до подтверждения",
        'file_size': "Размер файла",
        'actions_title': "Доступные действия",
        'actions_body': "После входа вы можете скачать исходный файл, получить завершенное доказательство и посмотреть детали записи в SecureStamp.it.",
        'download_file': "Скачать файл",
        'download_proof': "Скачать доказательство",
        'see_details': "Посмотреть детали",
        'login_hint_link': "страницу входа SecureStamp.it",
        'primary_footer': "Это уведомление отправлено, потому что для вашей учетной записи включены email-уведомления.",
        'secondary_footer': "Это письмо только с вложениями для дополнительного получателя, указанного при загрузке.",
    },
    'zh': {
        'subject': "SecureStamp.it：时间戳已完成 {filename}",
        'title': "时间戳已完成",
        'hero_title': "时间戳已完成",
        'hero_subtitle_primary': "{filename} 的时间戳已确认。",
        'hero_subtitle_secondary': "该文件、分离签名和已完成的时间戳证明已作为附件包含在此邮件中。",
        'hello_user': "{username}，您好：",
        'hello_generic': "您好：",
        'body_primary': "SecureStamp.it 已完成您上传文件的时间戳流程。记录详情如下。",
        'body_secondary': "SecureStamp.it 已完成 {filename} 的时间戳流程。此邮件附带原始文件、分离签名和已完成的 OpenTimestamps 证明。",
        'protect_note': "为保护您的证据包访问权限，本邮件中的链接仅在您使用账户登录 SecureStamp.it 平台后可用。",
        'file_name': "文件名",
        'file_uuid': "文件 UUID",
        'uploaded_at': "上传时间 (UTC)",
        'confirmed_at': "确认时间 (UTC)",
        'time_to_confirmation': "完成耗时",
        'file_size': "文件大小",
        'actions_title': "可用操作",
        'actions_body': "登录后，您可以下载原始文件、获取已完成的时间戳证明，并在 SecureStamp.it 中查看记录详情。",
        'download_file': "下载文件",
        'download_proof': "下载已完成证明",
        'see_details': "查看详情",
        'login_hint_link': "SecureStamp.it 登录页面",
        'primary_footer': "此通知之所以发送，是因为您的账户已启用邮件通知。",
        'secondary_footer': "这是发送给上传时配置的附加收件人的仅附件确认邮件。",
    },
    'hu': {
        'subject': "SecureStamp.it: Idobelyegzes kesz {filename}",
        'title': "Idobelyegzes kesz",
        'hero_title': "Idobelyegzes kesz",
        'hero_subtitle_primary': "A(z) {filename} idobelyege megerositve.",
        'hero_subtitle_secondary': "A fajl, a kulonallo alairas es a kesz idobelyeg-bizonyitek csatolva van ehhez az emailhez.",
        'hello_user': "Udv {username},",
        'hello_generic': "Udv,",
        'body_primary': "A SecureStamp.it befejezte a feltoltott fajl idobelyegzesi folyamatait. A rogzitett adatok lent talalhatok.",
        'body_secondary': "A SecureStamp.it befejezte a(z) {filename} idobelyegzesi folyamatait. Ez az uzenet csatolva tartalmazza az eredeti fajlt, a kulonallo alairast es a kesz OpenTimestamps bizonyitekot.",
        'protect_note': "A bizonyiteki csomag vedelme erdekeben az emailben levo linkek csak akkor mukodnek, ha bejelentkezik a SecureStamp.it feluleten a fiokjaval.",
        'file_name': "Fajlnev",
        'file_uuid': "Fajl UUID",
        'uploaded_at': "Feltoltve (UTC)",
        'confirmed_at': "Megerositve (UTC)",
        'time_to_confirmation': "Megerositesehez eltelt ido",
        'file_size': "Fajlmeret",
        'actions_title': "Elerheto muveletek",
        'actions_body': "Bejelentkezes utan letoltheti az eredeti fajlt, a kesz bizonyitekot es megnezheti a reszleteket a SecureStamp.it feluleten.",
        'download_file': "Fajl letoltese",
        'download_proof': "Bizonyitek letoltese",
        'see_details': "Reszletek megtekintese",
        'login_hint_link': "a SecureStamp.it bejelentkezesi oldalat",
        'primary_footer': "Ez az ertesites azert keszult, mert az emailertesitesek engedelyezve vannak a fiokjaban.",
        'secondary_footer': "Ez egy csak csatolmanyos megerosito email a feltolteskor megadott tovabbi cimzettnek.",
    },
}.items():
    EMAIL_TRANSLATIONS[code] = {**EMAIL_TRANSLATIONS['en'], **updates}


for code, updates in {
    'es': {
        'Timestamp completed': "Marca de tiempo completada",
        'Timestamp requested': "Marca de tiempo solicitada",
        'Error': "Error",
    },
    'pt': {
        'Timestamp completed': "Timestamp concluido",
        'Timestamp requested': "Timestamp solicitado",
        'Error': "Erro",
    },
    'fr': {
        'Timestamp completed': "Horodatage termine",
        'Timestamp requested': "Horodatage demande",
        'Error': "Erreur",
    },
    'de': {
        'Timestamp completed': "Zeitstempel abgeschlossen",
        'Timestamp requested': "Zeitstempel angefordert",
        'Error': "Fehler",
    },
    'ru': {
        'Timestamp completed': "Метка времени завершена",
        'Timestamp requested': "Запрошена метка времени",
        'Error': "Ошибка",
    },
    'zh': {
        'Timestamp completed': "时间戳已完成",
        'Timestamp requested': "时间戳已请求",
        'Error': "错误",
    },
    'hu': {
        'Timestamp completed': "Idobelyegzes kesz",
        'Timestamp requested': "Idobelyegzes kerve",
        'Error': "Hiba",
    },
}.items():
    STATUS_TRANSLATIONS[code] = updates


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


def get_email_language(language_code):
    normalized = normalize_language(language_code, default='en')
    return normalized if normalized in EMAIL_TRANSLATIONS else 'en'


def email_text(language_code, key, **kwargs):
    language = get_email_language(language_code)
    template = EMAIL_TRANSLATIONS.get(language, EMAIL_TRANSLATIONS['en']).get(key)
    if template is None:
        template = EMAIL_TRANSLATIONS['en'][key]
    return template.format(**kwargs) if kwargs else template


def translate_email_status(status, language_code):
    language = get_email_language(language_code)
    return STATUS_TRANSLATIONS.get(language, STATUS_TRANSLATIONS['en']).get(
        status,
        STATUS_TRANSLATIONS['en'].get(status, status),
    )


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


OTS_TIMEZONE_OFFSETS = {
    'UTC': 0,
    'GMT': 0,
    'CET': 1,
    'CEST': 2,
}


def get_proof_confirmation_time(file_path):
    proof_path = f'{file_path}.ots'
    if not os.path.exists(file_path) or not os.path.exists(proof_path):
        return None

    try:
        result = subprocess.run(
            ['ots-cli.js', 'verify', '--ignore-bitcoin-node', '-f', file_path, proof_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    match = re.search(r'Success!\s+Bitcoin attests data existed as of\s+(.+)', result.stdout)
    if not match:
        return None

    raw_value = match.group(1).strip()
    raw_parts = raw_value.rsplit(' ', 1)
    if len(raw_parts) != 2:
        return None

    timestamp_part, timezone_name = raw_parts
    timezone_offset = OTS_TIMEZONE_OFFSETS.get(timezone_name.upper())
    if timezone_offset is None:
        return None

    try:
        naive_timestamp = datetime.strptime(timestamp_part, '%a %b %d %H:%M:%S %Y')
    except ValueError:
        return None

    aware_timestamp = naive_timestamp.replace(tzinfo=timezone(timedelta(hours=timezone_offset)))
    return aware_timestamp.astimezone(timezone.utc).replace(tzinfo=None)


def build_timestamp_completion_email(file, user):
    confirmed_at = file.confirmed_at or datetime.utcnow()
    base_url = get_public_base_url()
    language = get_email_language(user.email_notification_language)
    return render_template(
        'emails/timestamp_completed.html',
        email_lang=language,
        email_t=lambda key, **kwargs: email_text(language, key, **kwargs),
        user=user,
        file=file,
        translated_status=translate_email_status(file.status, language),
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
    confirmed_at = file.confirmed_at or datetime.utcnow()
    language = get_email_language(file.notification_email_language)
    return render_template(
        'emails/timestamp_completed_attachment.html',
        email_lang=language,
        email_t=lambda key, **kwargs: email_text(language, key, **kwargs),
        user=user,
        file=file,
        translated_status=translate_email_status(file.status, language),
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


def send_pending_notifications(app, file, user, mail_enabled):
    primary_recipient = get_primary_notification_recipient(user)
    secondary_recipient = get_secondary_notification_recipient(file, user)

    if not mail_enabled:
        recipients = [recipient for recipient in [primary_recipient, secondary_recipient] if recipient]
        if recipients:
            print(f"Email notification skipped for {', '.join(recipients)}: SMTP is not configured")
        else:
            print(f"Email notification skipped for file {file.storage_key}: no recipients configured")
        return

    if primary_recipient and not file.primary_notification_sent_at:
        try:
            subject = email_text(
                user.email_notification_language,
                'subject',
                filename=file.original_filename,
            )
            html_body = build_timestamp_completion_email(file, user)
            send_email([primary_recipient], subject, html_body)
            file.primary_notification_sent_at = datetime.utcnow()
            db.session.commit()
            print(f"Primary notification email sent to {primary_recipient}")
        except Exception as exc:
            db.session.rollback()
            print(f"Primary notification email failed for {primary_recipient}: {exc}")

    if secondary_recipient and not file.secondary_notification_sent_at:
        try:
            subject = email_text(
                file.notification_email_language,
                'subject',
                filename=file.original_filename,
            )
            html_body = build_attachment_confirmation_email(file, user)
            attachments = build_existing_attachments(file)
            send_email(
                [secondary_recipient],
                subject,
                html_body,
                attachments=attachments,
            )
            file.secondary_notification_sent_at = datetime.utcnow()
            db.session.commit()
            print(f"Secondary notification email sent to {secondary_recipient}")
        except Exception as exc:
            db.session.rollback()
            print(f"Secondary notification email failed for {secondary_recipient}: {exc}")

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
                        file.confirmed_at = get_proof_confirmation_time(file.file_path) or datetime.utcnow()
                        db.session.commit()
                else:
                    print(result.stdout.decode('utf-8'))

            if file.status == 'Timestamp completed':
                send_pending_notifications(app, file, user, mail_enabled)

        repaired_confirmed_at = 0
        for file, _user in files:
            if file.status != 'Timestamp completed' or file.confirmed_at is not None:
                continue

            confirmed_at = get_proof_confirmation_time(file.file_path)
            if confirmed_at is None:
                continue

            file.confirmed_at = confirmed_at
            repaired_confirmed_at += 1
            print(f"Backfilled confirmed_at from proof for file {file.file_path}")

        if repaired_confirmed_at:
            db.session.commit()
            print(f"Backfilled confirmed_at for {repaired_confirmed_at} completed file(s)")

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
