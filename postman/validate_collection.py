"""Validates the Postman collection against the backend's real OpenAPI document.

Checks performed:
  * both JSON files parse;
  * every request maps to an operation that exists in the app's OpenAPI paths;
  * every OpenAPI operation is covered by at least one request;
  * the raw PDF body in the collection is byte-identical to postman/samples/report.pdf;
  * environment hashes and sizes match the sample attachments.

Run from the repository root:

    cd backend && python ../postman/validate_collection.py     # needs app importable
    # or, with backend/ on PYTHONPATH:
    python postman/validate_collection.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COLLECTION = HERE / "Rice_Age_Portal.postman_collection.json"
ENVIRONMENT = HERE / "Rice_Age_Local.postman_environment.json"


def iter_requests(node):
    if "request" in node:
        yield node
        return
    for child in node.get("item", []):
        yield from iter_requests(child)


def collection_operation(request: dict) -> tuple[str, str]:
    """Returns (METHOD, /api/v1/... path) with Postman variables normalised to {param}."""

    raw = request["url"]["raw"].split("{{base_url}}", 1)[-1].split("?", 1)[0]
    path = re.sub(r"\{\{[a-zA-Z0-9_]+\}\}", "{param}", raw)
    return request["method"].upper(), path


def openapi_operations() -> set[tuple[str, str]]:
    backend = ROOT / "backend"
    sys.path.insert(0, str(backend))
    from app.main import create_app  # noqa: PLC0415

    spec = create_app().openapi()
    operations: set[tuple[str, str]] = set()
    for path, methods in spec["paths"].items():
        normalised = re.sub(r"\{[^}]+\}", "{param}", path)
        for method in methods:
            operations.add((method.upper(), normalised))
    return operations


def main() -> int:
    collection = json.loads(COLLECTION.read_text(encoding="utf-8"))
    environment = json.loads(ENVIRONMENT.read_text(encoding="utf-8"))

    problems: list[str] = []
    requests = list(iter_requests(collection))
    actual = {collection_operation(item["request"]) for item in requests}

    expected = openapi_operations()
    missing_from_collection = expected - actual
    unknown = actual - expected
    if missing_from_collection:
        problems.append(f"operations missing from the collection: {sorted(missing_from_collection)}")
    if unknown:
        problems.append(f"collection requests with no backend operation: {sorted(unknown)}")

    env = {row["key"]: row["value"] for row in environment["values"]}
    for filename, size_key, hash_key in (
        ("report.pdf", "report_size_bytes", "report_sha256"),
        ("platen-bottom.png", "bottom_image_size_bytes", "bottom_image_sha256"),
    ):
        payload = (HERE / "samples" / filename).read_bytes()
        if str(len(payload)) != env.get(size_key):
            problems.append(f"{size_key} does not match {filename}")
        if hashlib.sha256(payload).hexdigest() != env.get(hash_key):
            problems.append(f"{hash_key} does not match {filename}")

    upload = next(
        request for request in requests if request["name"].startswith("Upload report attachment")
    )
    sample_report = (HERE / "samples" / "report.pdf").read_bytes()
    if upload["request"]["body"]["raw"].encode("utf-8") != sample_report:
        problems.append("the collection's raw PDF body differs from samples/report.pdf")

    methods: dict[str, int] = {}
    for method, _path in actual:
        methods[method] = methods.get(method, 0) + 1

    print(f"folders: {len(collection['item'])}")
    print(f"requests: {len(requests)}")
    print(f"operations covered: {len(actual)} of {len(expected)} in OpenAPI")
    print("by method: " + ", ".join(f"{method} {count}" for method, count in sorted(methods.items())))
    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("OK: collection, environment and sample attachments are consistent with the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
