"""Generates the tiny sample attachments used by the Postman collection.

The upload endpoint verifies the declared SHA-256 and the file magic bytes, so the
collection ships files whose hashes are known in advance instead of asking a new
developer to invent them.

Run: python postman/samples/make_samples.py
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

PDF_BYTES = (
    b"%PDF-1.4\n"
    b"% Rice Age Portal - Postman sample report (not a real analysis report)\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\n"
    b"%%EOF\n"
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def main() -> None:
    for name, payload in (("report.pdf", PDF_BYTES), ("platen-bottom.png", PNG_BYTES)):
        path = HERE / name
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        print(f"{name}\tsize={len(payload)}\tsha256={digest}")


if __name__ == "__main__":
    main()
