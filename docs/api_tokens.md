# API Tokens

SecureStamp authorization tokens authenticate API calls as the user who created the token.

Create a token from the `Tokens` page in the web UI. Copy it when shown: the raw token is only displayed once.

## Base URL

Examples below use:

```bash
BASE_URL="https://securestamp.it"
TOKEN="paste-your-token-here"
```

All requests must send:

```bash
Authorization: Bearer $TOKEN
```

## List Files

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/files"
```

The response returns `file_uuid` for each file. Use that UUID in all file download endpoints below.

## Upload Files

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "notification_email=optional@example.com" \
  -F "files=@/path/to/document.pdf" \
  -F "files=@/path/to/image.png" \
  "$BASE_URL/api/files/upload"
```

`notification_email` is optional. If provided, SecureStamp.it also sends the timestamp completion email to that address for every uploaded file in the request.

## Download Original File

```bash
curl -L \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/files/FILE_UUID/download" \
  -o downloaded-file.bin
```

## Download Timestamp Proof

```bash
curl -L \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/files/FILE_UUID/timestamp" \
  -o proof.ots
```

## Download Signature

```bash
curl -L \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/files/FILE_UUID/signature" \
  -o signature.sig
```

## Create Symbol

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"MY-SYMBOL","description":"Created via token"}' \
  "$BASE_URL/api/symbols"
```

## Delete Symbol

```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/api/symbols/SYMBOL_ID"
```

## Notes

- Token hits are counted automatically on every token-authenticated API request.
- Locked tokens are rejected.
- If a token has `max_hits`, requests stop working once the limit is reached.
- Token downloads increment the same file download statistics as the web app.
