# Nanocare Wellness Integration API — v1 Guide

> **Base URL**: `http://localhost:8001/api/v1/wellness`
>
> **OpenAPI Docs**: `http://localhost:8001/docs` (Swagger UI)

---

## Authentication

| Header | Required | Purpose |
|--------|----------|---------|
| `X-Doctor-Id` | Yes (draft/approve) | External doctor identifier |
| `Idempotency-Key` | Optional | Unique UUID per request — safe retries |

> **Note**: The API does not validate `X-Doctor-Id` against any user table.
> The external system is responsible for doctor authentication.
> Future versions will transition to `Authorization: Bearer <token>`.

---

## Workflow Overview

```
1. Doctor uploads device files     → POST /reports/drafts
2. Doctor reviews draft            → GET  /reports/drafts/{draft_id}
3. Doctor edits draft (optional)   → PATCH /reports/drafts/{draft_id}
4. Doctor approves draft           → POST /reports/drafts/{draft_id}/approve
5. Customer views dashboard        → GET  /patients/{patient_id}/dashboard
6. Customer downloads PDF          → GET  /reports/{report_id}/pdf
```

---

## Endpoints

### 1. Create Draft

Upload 6 device files to generate a wellness report draft.

```bash
curl -X POST http://localhost:8001/api/v1/wellness/reports/drafts \
  -H "X-Doctor-Id: doc_123" \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -F ecg=@ecg_report.pdf \
  -F hrv=@hrv_report.pdf \
  -F nadi=@nadi_report.pdf \
  -F biowell=@biowell_report.pdf \
  -F biores=@bioresonance_report.pdf \
  -F inbody=@inbody_scan.jpg \
  -F patient_id=PAT001 \
  -F "name=John Doe" \
  -F dob=1990-05-15 \
  -F date=2026-06-22
```

**Response** (`200 OK`):
```json
{
  "draft_id": "draft_a1b2c3d4...",
  "patient_id": "PAT001",
  "status": "draft",
  "created_by_doctor_id": "doc_123",
  "report": { "patient": {...}, "metrics": {...}, "dimensions": {...}, ... },
  "cached": false,
  "extraction_summary": { "ecg": "ok", "hrv": "ok", ... }
}
```

**Idempotency**: Sending the same files + patient inputs returns the existing draft (`"cached": true`). No re-extraction occurs.

---

### 2. Get Draft (Doctor Review)

```bash
curl http://localhost:8001/api/v1/wellness/reports/drafts/draft_a1b2c3d4 \
  -H "X-Doctor-Id: doc_123"
```

**Response** (`200 OK`):
```json
{
  "draft_id": "draft_a1b2c3d4",
  "report_id": "",
  "patient_id": "PAT001",
  "status": "draft",
  "created_by_doctor_id": "doc_123",
  "report": { ... }
}
```

---

### 3. Edit Draft

Deep-merge updates into the draft. Only changed fields are required.
No re-extraction, no re-synthesis, no PDF generation.

```bash
curl -X PATCH http://localhost:8001/api/v1/wellness/reports/drafts/draft_a1b2c3d4 \
  -H "X-Doctor-Id: doc_123" \
  -H "Content-Type: application/json" \
  -d '{
    "report": {
      "patient": { "name": "John D." },
      "wellness": { "diet": "Updated dietary recommendation" }
    }
  }'
```

**Response** (`200 OK`):
```json
{
  "draft_id": "draft_a1b2c3d4",
  "status": "draft",
  "report": { "patient": { "name": "John D.", ... }, ... }
}
```

> **Note**: If you change `patient.dob` or `patient.date`, the biorhythm
> calendar is automatically recalculated.

---

### 4. Approve Draft

Generates the final PDF, persists to history, and returns the full approved report.

```bash
curl -X POST http://localhost:8001/api/v1/wellness/reports/drafts/draft_a1b2c3d4/approve \
  -H "X-Doctor-Id: doc_456"
```

**Response** (`200 OK`):
```json
{
  "report_id": "report_a1b2c3d4...",
  "draft_id": "draft_a1b2c3d4",
  "status": "approved",
  "created_by_doctor_id": "doc_123",
  "approved_by_doctor_id": "doc_456",
  "generated_report": "http://localhost:8001/api/v1/wellness/reports/report_.../pdf",
  "report": { ... },
  "summary": { "report_id": "...", "summary": {...}, "metrics": {...}, ... },
  "history": { "visit_saved": true, ... }
}
```

**Idempotent**: Calling approve on an already-approved draft returns the existing approval (same `report_id`, no new PDF).

---

### 5. Get Active Draft (Doctor)

Find the latest unfinished draft for a patient.

```bash
curl http://localhost:8001/api/v1/wellness/patients/PAT001/active-draft \
  -H "X-Doctor-Id: doc_123"
```

Returns `404` if no active draft exists.

---

### 6. List Patient Drafts (Doctor)

```bash
curl http://localhost:8001/api/v1/wellness/patients/PAT001/drafts?limit=10 \
  -H "X-Doctor-Id: doc_123"
```

---

### 7. Patient Dashboard (Customer/User)

Latest approved report + historical chart data. No drafts are ever exposed.

```bash
curl http://localhost:8001/api/v1/wellness/patients/PAT001/dashboard
```

**Response** (`200 OK`):
```json
{
  "patient_id": "PAT001",
  "patient": { "id": "PAT001", "name": "John D.", "dob": "1990-05-15" },
  "latest_report": { "report_id": "...", "summary": {...}, ... },
  "history": { "dates": [...], "stats": {...}, "dimensions": {...}, ... },
  "reports": [ ... ]
}
```

---

### 8. List Approved Reports (Customer/User)

```bash
curl http://localhost:8001/api/v1/wellness/patients/PAT001/reports?limit=20
```

---

### 9. Get Approved Report

```bash
curl http://localhost:8001/api/v1/wellness/reports/report_a1b2c3d4
```

---

### 10. Get Report Summary

Compact payload for mobile/web cards.

```bash
curl http://localhost:8001/api/v1/wellness/reports/report_a1b2c3d4/summary
```

---

### 11. Download PDF

```bash
curl http://localhost:8001/api/v1/wellness/reports/report_a1b2c3d4/pdf \
  -o wellness_report.pdf
```

---

## Error Responses

All errors return JSON:

```json
{
  "detail": "Draft draft_xyz not found"
}
```

| Status | Meaning |
|--------|---------|
| `400` | Missing required field (e.g. `patient_id`) |
| `404` | Draft/report not found |
| `409` | Conflict (e.g. editing an approved draft) |
| `500` | PDF generation or internal error |

---

## Legacy Routes (Deprecated)

The following routes still work but are deprecated in OpenAPI:

| Legacy Route | v1 Replacement |
|-------------|----------------|
| `POST /api/generate` | `POST /api/v1/wellness/reports/drafts` + `.../approve` |
| `POST /api/doctor/reports/draft` | `POST /api/v1/wellness/reports/drafts` |
| `GET /api/doctor/reports/{id}` | `GET /api/v1/wellness/reports/drafts/{id}` |
| `PATCH /api/doctor/reports/{id}` | `PATCH /api/v1/wellness/reports/drafts/{id}` |
| `POST /api/doctor/reports/{id}/approve` | `POST /api/v1/wellness/reports/drafts/{id}/approve` |
| `GET /api/user/patient/{id}/dashboard` | `GET /api/v1/wellness/patients/{id}/dashboard` |
| `GET /api/user/patient/{id}/reports` | `GET /api/v1/wellness/patients/{id}/reports` |
| `GET /api/user/report/{id}/summary` | `GET /api/v1/wellness/reports/{id}/summary` |
| `GET /api/user/report/{id}/pdf` | `GET /api/v1/wellness/reports/{id}/pdf` |
