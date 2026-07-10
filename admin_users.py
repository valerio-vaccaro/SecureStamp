#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime

from sqlalchemy import case, func

from app import app, db
from models import ApiToken, File, User


def format_dt(value):
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def format_status(user):
    return "pending" if user.locked else "active"


def build_user_rows(include_pending_only=False):
    file_stats = (
        db.session.query(
            File.user_id.label("user_id"),
            func.count(File.id).label("files"),
            func.coalesce(
                func.sum(
                    File.file_downloads + File.timestamp_downloads + File.signature_downloads
                ),
                0,
            ).label("downloads"),
            func.coalesce(
                func.sum(case((File.status == "Timestamp completed", 1), else_=0)),
                0,
            ).label("completed"),
            func.coalesce(
                func.sum(case((File.status == "Timestamp requested", 1), else_=0)),
                0,
            ).label("requested"),
            func.coalesce(
                func.sum(case((File.status == "Error", 1), else_=0)),
                0,
            ).label("errors"),
            func.max(File.uploaded_at).label("last_upload_at"),
        )
        .group_by(File.user_id)
        .subquery()
    )

    token_stats = (
        db.session.query(
            ApiToken.user_id.label("user_id"),
            func.count(ApiToken.id).label("tokens"),
            func.coalesce(func.sum(ApiToken.hits), 0).label("token_hits"),
            func.max(ApiToken.last_used_at).label("last_token_use_at"),
        )
        .group_by(ApiToken.user_id)
        .subquery()
    )

    query = (
        db.session.query(
            User.id,
            User.username,
            User.email,
            User.created_at,
            User.locked,
            User.email_notifications,
            func.coalesce(file_stats.c.files, 0).label("files"),
            func.coalesce(file_stats.c.downloads, 0).label("downloads"),
            func.coalesce(file_stats.c.completed, 0).label("completed"),
            func.coalesce(file_stats.c.requested, 0).label("requested"),
            func.coalesce(file_stats.c.errors, 0).label("errors"),
            file_stats.c.last_upload_at.label("last_upload_at"),
            func.coalesce(token_stats.c.tokens, 0).label("tokens"),
            func.coalesce(token_stats.c.token_hits, 0).label("token_hits"),
            token_stats.c.last_token_use_at.label("last_token_use_at"),
        )
        .outerjoin(file_stats, file_stats.c.user_id == User.id)
        .outerjoin(token_stats, token_stats.c.user_id == User.id)
        .order_by(User.created_at.asc())
    )

    if include_pending_only:
        query = query.filter(User.locked.is_(True))

    return query.all()


def print_table(rows):
    headers = [
        "id",
        "username",
        "email",
        "status",
        "created_at",
        "files",
        "requested",
        "completed",
        "errors",
        "downloads",
        "tokens",
        "token_hits",
        "last_upload",
        "last_token_use",
        "email_notifications",
    ]

    normalized = []
    for row in rows:
        normalized.append(
            [
                str(row.id),
                row.username,
                row.email,
                "pending" if row.locked else "active",
                format_dt(row.created_at),
                str(row.files),
                str(row.requested),
                str(row.completed),
                str(row.errors),
                str(row.downloads),
                str(row.tokens),
                str(row.token_hits),
                format_dt(row.last_upload_at),
                format_dt(row.last_token_use_at),
                "on" if row.email_notifications else "off",
            ]
        )

    widths = [len(header) for header in headers]
    for record in normalized:
        for index, value in enumerate(record):
            widths[index] = max(widths[index], len(value))

    def render_line(values):
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    print(render_line(headers))
    print("-+-".join("-" * width for width in widths))
    for record in normalized:
        print(render_line(record))


def command_list(args):
    rows = build_user_rows(include_pending_only=args.pending_only)
    if not rows:
        print("No users found.")
        return 0

    print_table(rows)
    return 0


def find_user(identifier):
    if identifier.isdigit():
        user = User.query.filter_by(id=int(identifier)).first()
        if user:
            return user

    user = User.query.filter_by(username=identifier).first()
    if user:
        return user

    return User.query.filter_by(email=identifier).first()


def command_approve(args):
    user = find_user(args.user)
    if not user:
        print(f"User not found: {args.user}", file=sys.stderr)
        return 1

    if not user.locked:
        print(
            f"User '{user.username}' is already active "
            f"(id={user.id}, email={user.email})."
        )
        return 0

    user.locked = False
    db.session.commit()
    print(
        f"Approved user '{user.username}' "
        f"(id={user.id}, email={user.email})."
    )
    return 0


def command_set_password(args):
    user = find_user(args.user)
    if not user:
        print(f"User not found: {args.user}", file=sys.stderr)
        return 1

    if len(args.password) < 8:
        print("Password must be at least 8 characters long.", file=sys.stderr)
        return 1

    user.set_password(args.password)
    db.session.commit()
    print(
        f"Password updated for user '{user.username}' "
        f"(id={user.id}, email={user.email})."
    )
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Administrative user management for SecureStamp."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list",
        help="List registered users with status and usage summary.",
    )
    list_parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Show only pending registrations.",
    )
    list_parser.set_defaults(func=command_list)

    approve_parser = subparsers.add_parser(
        "approve",
        help="Approve a pending registration by id, username, or email.",
    )
    approve_parser.add_argument(
        "user",
        help="User id, username, or email.",
    )
    approve_parser.set_defaults(func=command_approve)

    password_parser = subparsers.add_parser(
        "set-password",
        help="Change a user's password by id, username, or email.",
    )
    password_parser.add_argument(
        "user",
        help="User id, username, or email.",
    )
    password_parser.add_argument(
        "password",
        help="New password value.",
    )
    password_parser.set_defaults(func=command_set_password)

    return parser


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        sys.argv.append("list")
    args = parser.parse_args()
    with app.app_context():
        return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
