#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests


def normalize_base_url(url: str) -> str:
    url = (url or "securestamp.it").strip()
    if not urlparse(url).scheme:
        url = f"https://{url}"
    return url.rstrip("/")


class SecureStampTokenClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = normalize_base_url(base_url)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _json(self, response: requests.Response):
        try:
            return response.json()
        except ValueError:
            return {"status_code": response.status_code, "text": response.text}

    def list_files(self):
        response = self.session.get(self._url("/api/files"))
        return response.status_code, self._json(response)

    def upload_files(self, paths):
        files = []
        opened = []
        try:
            for path in paths:
                handle = open(path, "rb")
                opened.append(handle)
                files.append(("files", (Path(path).name, handle)))
            response = self.session.post(self._url("/api/files/upload"), files=files)
            return response.status_code, self._json(response)
        finally:
            for handle in opened:
                handle.close()

    def download_file(self, file_id: int, output_path: str | None = None):
        response = self.session.get(self._url(f"/api/files/{file_id}/download"), stream=True)
        return self._save_binary_response(response, output_path)

    def download_timestamp(self, file_id: int, output_path: str | None = None):
        response = self.session.get(self._url(f"/api/files/{file_id}/timestamp"), stream=True)
        return self._save_binary_response(response, output_path)

    def download_signature(self, file_id: int, output_path: str | None = None):
        response = self.session.get(self._url(f"/api/files/{file_id}/signature"), stream=True)
        return self._save_binary_response(response, output_path)

    def create_symbol(self, name: str, description: str):
        response = self.session.post(
            self._url("/api/symbols"),
            json={"name": name, "description": description},
        )
        return response.status_code, self._json(response)

    def delete_symbol(self, symbol_id: int):
        response = self.session.delete(self._url(f"/api/symbols/{symbol_id}"))
        return response.status_code, self._json(response)

    def _save_binary_response(self, response: requests.Response, output_path: str | None):
        if not response.ok:
            return response.status_code, self._json(response)

        if not output_path:
            output_path = self._filename_from_response(response) or "download.bin"

        output = Path(output_path)
        with output.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)

        return response.status_code, {"saved_to": str(output)}

    @staticmethod
    def _filename_from_response(response: requests.Response):
        content_disposition = response.headers.get("Content-Disposition", "")
        marker = "filename="
        if marker not in content_disposition:
            return None
        return content_disposition.split(marker, 1)[1].strip().strip('"')


def print_result(status_code, payload):
    print(f"HTTP {status_code}")
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser():
    parser = argparse.ArgumentParser(description="SecureStamp token-authenticated API client")
    parser.add_argument("--url", default="securestamp.it", help="Base URL, default: securestamp.it")
    parser.add_argument("--token", required=True, help="Authorization token")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-files", help="List files")

    upload = subparsers.add_parser("upload-files", help="Upload one or more files")
    upload.add_argument("files", nargs="+", help="File paths to upload")

    download_file = subparsers.add_parser("download-file", help="Download original file")
    download_file.add_argument("file_id", type=int)
    download_file.add_argument("--output", help="Output path")

    download_timestamp = subparsers.add_parser("download-timestamp", help="Download timestamp proof")
    download_timestamp.add_argument("file_id", type=int)
    download_timestamp.add_argument("--output", help="Output path")

    download_signature = subparsers.add_parser("download-signature", help="Download signature")
    download_signature.add_argument("file_id", type=int)
    download_signature.add_argument("--output", help="Output path")

    create_symbol = subparsers.add_parser("create-symbol", help="Create a symbol")
    create_symbol.add_argument("--name", required=True)
    create_symbol.add_argument("--description", default="")

    delete_symbol = subparsers.add_parser("delete-symbol", help="Delete a symbol")
    delete_symbol.add_argument("symbol_id", type=int)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    client = SecureStampTokenClient(args.url, args.token)

    if args.command == "list-files":
        print_result(*client.list_files())
    elif args.command == "upload-files":
        print_result(*client.upload_files(args.files))
    elif args.command == "download-file":
        print_result(*client.download_file(args.file_id, args.output))
    elif args.command == "download-timestamp":
        print_result(*client.download_timestamp(args.file_id, args.output))
    elif args.command == "download-signature":
        print_result(*client.download_signature(args.file_id, args.output))
    elif args.command == "create-symbol":
        print_result(*client.create_symbol(args.name, args.description))
    elif args.command == "delete-symbol":
        print_result(*client.delete_symbol(args.symbol_id))


if __name__ == "__main__":
    main()
