"""Cross-cutting HTTP behaviour: error envelope, correlation IDs, headers, CORS."""

from __future__ import annotations

from fastapi.testclient import TestClient

REQUEST_ID_HEADER = "X-Request-ID"


def test_unknown_route_uses_the_error_envelope_and_echoes_request_id(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/does-not-exist", headers={REQUEST_ID_HEADER: "req-abc-123"})

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == "req-abc-123"
    assert response.headers[REQUEST_ID_HEADER] == "req-abc-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    request_id = client.get("/api/v1/health").headers[REQUEST_ID_HEADER]

    assert len(request_id) == 36
    assert request_id.count("-") == 4


def test_method_not_allowed_uses_the_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_request_id_is_capped_to_64_characters(client: TestClient) -> None:
    oversized = "x" * 200

    response = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: oversized})

    assert response.headers[REQUEST_ID_HEADER] == "x" * 64


def test_cors_allows_configured_origin_and_rejects_others(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    rejected = client.options(
        "/api/v1/health",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in rejected.headers
