# Device Simulator

A command-line stand-in for a provisioned Rice Age analyser. It uses only the Python
standard library (3.12+) and speaks the same API contract as a real device: device
token → scan submission → attachment prepare/upload → finalize → status polling.

All sample data and files are synthetic. Do not point this at production, and never use
real personal data or production device credentials.

---

## 1. Prerequisites

- The backend running at an address the simulator can reach (default
  `http://localhost:8000`), with PostgreSQL available.
- A registered, **active** device with an active department assignment and an issued
  credential. The secret is shown only once, at issuance or rotation:

```bash
# as a super admin, with $TOKEN from POST /api/v1/auth/login
curl -s -X POST "$API/api/v1/admin/devices" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"device_uid":"RICE-DEVICE-001","serial_number":"SN-0001","department_id":"<uuid>"}'

curl -s -X POST "$API/api/v1/admin/devices/<device-uuid>/credentials" \
  -H "Authorization: Bearer $TOKEN"
```

Store the returned `client_id` and `client_secret` in your environment. They are not
recoverable later; rotate to get a new pair.

## 2. Configuration

| Variable | Meaning |
| --- | --- |
| `RICE_AGE_API_URL` | API base URL, default `http://localhost:8000` |
| `RICE_AGE_DEVICE_CLIENT_ID` | Device `client_id` |
| `RICE_AGE_DEVICE_CLIENT_SECRET` | Device secret |

```bash
export RICE_AGE_API_URL=http://localhost:8000
export RICE_AGE_DEVICE_CLIENT_ID=dev_...
export RICE_AGE_DEVICE_CLIENT_SECRET=...
```

The simulator prints the client id but never the secret.

## 3. Running a scan

```bash
python device-simulator/simulator.py
```

Optional flags: `--base-url`, `--client-id`, `--client-secret`, `--scenario`,
`--client-scan-id`.

A successful run prints the token identity, the accepted scan id and processing state,
each uploaded attachment, the finalize result (`completed`, verdict, notification
count) and the polled status with attachment states.

## 4. Scenarios

| `--scenario` | What it proves | Expected result |
| --- | --- | --- |
| `valid` (default) | Full happy path with report, bottom and top images | `completed` |
| `missing-top` | `top_image` is optional; finalize still succeeds | `completed` |
| `invalid-payload` | Schema validation rejects a payload without measurements | HTTP `422` |
| `duplicate` | Identical replay returns the same scan | HTTP `200`, same `scan_id` |
| `conflict` | Same `client_scan_id`, different payload | HTTP `409 scan_conflict` |
| `bad-credentials` | Wrong secret cannot obtain a device token | HTTP `401` |

```bash
python device-simulator/simulator.py --scenario conflict
```

Exit code `0` means the scenario behaved as expected; `1` means it did not.

## 5. What the simulator does *not* do

- It does not infer rice age from images, grade quality, or certify anything.
- It does not retry indefinitely: token/HTTP failures are reported and the process
  exits non-zero so a CI job or operator can react.
- It does not bypass attachment verification; the backend recomputes SHA-256 and checks
  magic bytes on upload.
