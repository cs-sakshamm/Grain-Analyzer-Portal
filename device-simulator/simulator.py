#!/usr/bin/env python3
"""Rice Age device simulator.

Behaves like a provisioned IoT analyser: obtains a device token, submits a
versioned scan payload, uploads the configured attachments, finalizes and polls
status. Standard library only.

Credentials are read from the environment; the client secret is never printed.
All sample data is synthetic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SAMPLE_PAYLOAD = HERE / "sample_payload.json"

PDF_SAMPLE = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
PNG_SAMPLE = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 20

SCENARIOS = (
    "valid",
    "missing-top",
    "invalid-payload",
    "duplicate",
    "conflict",
    "bad-credentials",
)


def log(message: str) -> None:
    print(message, flush=True)


def request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    json_body: Any | None = None,
    data: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, Any]:
    headers: dict[str, str] = {"Accept": "application/json"}
    body: bytes | None = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif data is not None:
        body = data
        headers["Content-Type"] = content_type or "application/octet-stream"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            parsed = json.loads(raw) if raw else None
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = raw.decode("utf-8", "replace")
        return exc.code, parsed
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach the API at {url}: {exc.reason}") from exc


def build_payload(client_scan_id: str, *, valid: bool = True) -> dict[str, Any]:
    payload = json.loads(SAMPLE_PAYLOAD.read_text(encoding="utf-8"))
    payload["client_scan_id"] = client_scan_id
    payload["analyzed_at"] = datetime.now(UTC).isoformat()
    if not valid:
        payload["analysis"].pop("measurements", None)
    return payload


def obtain_token(base_url: str, client_id: str, client_secret: str) -> str | None:
    status, body = request(
        "POST",
        f"{base_url}/api/v1/device-auth/token",
        json_body={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if status == 200 and isinstance(body, dict):
        log(f"Authenticated as device {body.get('device_id')} (expires in {body.get('expires_in')}s)")
        return str(body["access_token"])
    log(f"Authentication failed: HTTP {status} {_error_summary(body)}")
    return None


def _error_summary(body: Any) -> str:
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return f"[{body['error'].get('code')}] {body['error'].get('message')}"
    return str(body)[:300]


def submit_scan(base_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    status, body = request(
        "POST", f"{base_url}/api/v1/device/scans", token=token, json_body=payload
    )
    if status in (200, 201) and isinstance(body, dict):
        log(
            f"Scan {body['scan_id']} accepted "
            f"(HTTP {status}, state={body['processing_status']}, replayed={body.get('replayed')})"
        )
        return body
    log(f"Scan submission rejected: HTTP {status} {_error_summary(body)}")
    return None


def upload_attachment(
    base_url: str,
    token: str,
    scan_id: str,
    *,
    role: str,
    content: bytes,
    content_type: str,
    filename: str,
) -> bool:
    status, body = request(
        "POST",
        f"{base_url}/api/v1/device/scans/{scan_id}/attachments/prepare",
        token=token,
        json_body={
            "role": role,
            "content_type": content_type,
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "filename": filename,
        },
    )
    if status != 200 or not isinstance(body, dict):
        log(f"Prepare {role} failed: HTTP {status} {_error_summary(body)}")
        return False
    url = str(body["url"])
    if not url.startswith("http"):
        url = urllib.parse.urljoin(base_url + "/", url.lstrip("/"))
    upload_status, upload_body = request(
        "PUT", url, token=token, data=content, content_type=content_type
    )
    if upload_status in (200, 201):
        log(f"Uploaded {role} ({len(content)} bytes, sha256 verified)")
        return True
    log(f"Upload {role} failed: HTTP {upload_status} {_error_summary(upload_body)}")
    return False


def finalize(base_url: str, token: str, scan_id: str) -> dict[str, Any] | None:
    status, body = request(
        "POST", f"{base_url}/api/v1/device/scans/{scan_id}/finalize", token=token, json_body={}
    )
    if status == 200 and isinstance(body, dict):
        log(
            f"Finalized: state={body['processing_status']} "
            f"verdict={body.get('quality_verdict')} "
            f"notifications={body.get('notifications_created')}"
        )
        return body
    log(f"Finalize failed: HTTP {status} {_error_summary(body)}")
    return None


def poll_status(base_url: str, token: str, scan_id: str) -> dict[str, Any] | None:
    for attempt in range(5):
        status, body = request(
            "GET", f"{base_url}/api/v1/device/scans/{scan_id}/status", token=token
        )
        if status == 200 and isinstance(body, dict):
            log(
                f"Status: {body['processing_status']} attachments="
                f"{[(item['role'], item['upload_status']) for item in body['attachments']]}"
            )
            if body["processing_status"] in ("completed", "failed"):
                return body
        else:
            log(f"Status poll failed: HTTP {status} {_error_summary(body)}")
            return None
        time.sleep(min(2**attempt, 8))
    return None


def run_scenario(args: argparse.Namespace, token: str | None) -> int:
    if args.scenario == "bad-credentials":
        token = obtain_token(args.base_url, args.client_id, args.client_secret + "-wrong")
        return 0 if token is None else 1
    if token is None:
        return 1

    client_scan_id = args.client_scan_id or f"SIM-{uuid.uuid4().hex[:12]}"
    payload = build_payload(client_scan_id, valid=args.scenario != "invalid-payload")
    accepted = submit_scan(args.base_url, token, payload)
    if args.scenario == "invalid-payload":
        return 0 if accepted is None else 1
    if accepted is None:
        return 1
    scan_id = str(accepted["scan_id"])

    if args.scenario == "duplicate":
        replay = submit_scan(args.base_url, token, payload)
        return 0 if replay and replay.get("scan_id") == scan_id else 1
    if args.scenario == "conflict":
        changed = build_payload(client_scan_id, valid=True)
        changed["analysis"]["grain_count"] = 999
        status, body = request(
            "POST", f"{args.base_url}/api/v1/device/scans", token=token, json_body=changed
        )
        log(f"Conflicting replay returned HTTP {status} {_error_summary(body)}")
        return 0 if status == 409 else 1

    uploads = [
        ("report_pdf", PDF_SAMPLE, "application/pdf", f"{client_scan_id}.pdf"),
        ("bottom_image", PNG_SAMPLE, "image/png", f"{client_scan_id}-bottom.png"),
    ]
    if args.scenario != "missing-top":
        uploads.append(
            ("top_image", PNG_SAMPLE, "image/png", f"{client_scan_id}-top.png")
        )
    for role, content, content_type, filename in uploads:
        if not upload_attachment(
            args.base_url,
            token,
            scan_id,
            role=role,
            content=content,
            content_type=content_type,
            filename=filename,
        ):
            return 1

    if finalize(args.base_url, token, scan_id) is None:
        return 1
    return 0 if poll_status(args.base_url, token, scan_id) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate a Rice Age IoT analyser.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("RICE_AGE_API_URL", "http://localhost:8000"),
    )
    parser.add_argument("--client-id", default=os.getenv("RICE_AGE_DEVICE_CLIENT_ID", ""))
    parser.add_argument(
        "--client-secret", default=os.getenv("RICE_AGE_DEVICE_CLIENT_SECRET", "")
    )
    parser.add_argument("--scenario", choices=SCENARIOS, default="valid")
    parser.add_argument("--client-scan-id", default=None)
    args = parser.parse_args(argv)

    if not args.client_id or not args.client_secret:
        parser.error(
            "set RICE_AGE_DEVICE_CLIENT_ID and RICE_AGE_DEVICE_CLIENT_SECRET, "
            "or pass --client-id/--client-secret"
        )
    if args.scenario == "missing-top":
        log("Note: top_image is optional; this scenario verifies finalize succeeds without it.")

    token = (
        obtain_token(args.base_url, args.client_id, args.client_secret)
        if args.scenario != "bad-credentials"
        else None
    )
    return run_scenario(args, token)


if __name__ == "__main__":
    sys.exit(main())
