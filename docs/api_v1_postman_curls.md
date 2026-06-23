# Nanocare Wellness v1 API - Postman cURL Cookbook

Use only these endpoints for new integrations.

Base URL:

```text
http://localhost:8001/api/v1/wellness
```

In Postman, choose **Import -> Raw text**, paste any cURL below, and replace the placeholder IDs/file paths.

Do not use deprecated routes under `/api/generate`, `/api/doctor/*`, or `/api/user/*` for new web/mobile work.

## Which APIs To Use

Use the current v1 endpoints this way. Draft APIs are doctor-only; patient/customer apps should only read approved reports.

### Doctor Side

| Screen / Action | Method | Endpoint | Use For |
|-----------------|--------|----------|---------|
| Upload | `POST` | `/reports/drafts` | Upload device files and create a temporary editable draft. |
| Draft view | `GET` | `/reports/drafts/{draft_id}` | Reopen/review the draft JSON. |
| Draft dashboard | `GET` | `/reports/drafts/{draft_id}` | Use the returned draft `report` sections: metrics, dimensions, body systems, DMIT, offerings, and biorhythm. |
| Edit draft | `PATCH` | `/reports/drafts/{draft_id}` | Save doctor edits before approval. |
| Approve draft | `POST` | `/reports/drafts/{draft_id}/approve` | Finalize the draft into an approved report. |
| Final report | `GET` | `/reports/{report_id}?detail=full` | Read the final approved report after approval. |
| Patient draft/workflow list | `GET` | `/patients/{patient_id}/drafts?limit=10` | Doctor-side list of draft workflow rows for one patient. |
| Patient approved reports | `GET` | `/patients/{patient_id}/reports?limit=20` | Doctor can also use this to see a patient's approved report history. |

### Patient / Customer Side

| Screen / Action | Method | Endpoint | Use For |
|-----------------|--------|----------|---------|
| Patient dashboard | `GET` | `/patients/{patient_id}/dashboard?limit=10` | Latest approved report, chart history, cards, and dashboard sections. |
| Patient history | `GET` | `/patients/{patient_id}/reports?limit=20` | Approved report list/history only. |
| Final report | `GET` | `/reports/{report_id}?detail=full` | Same approved final report JSON. |
| Report summary | `GET` | `/reports/{report_id}/summary` | Compact report payload for cards/previews. |
| PDF download | `GET` | `/reports/{report_id}/pdf` | Download/open final PDF. Send `X-API-Key`; prefer `links.pdf_download` from report payloads. |

Do not call `/reports/drafts/*` from patient/customer apps.

## Headers Reference

This API uses **three separate headers** — each serves a different purpose:

| Header | What It Does | Required? | When To Send |
|--------|-------------|-----------|-------------|
| `X-API-Key` | **Authentication** — proves you're authorized | Every request (when `NANOCARE_API_KEY` is set) | Always |
| `X-Doctor-Id` | **Identity** — which doctor is acting | Recommended on doctor endpoints | Create, Edit, Approve |
| `Idempotency-Key` | **Duplicate prevention** — safe retries | Optional | Create Draft only |

```
X-API-Key         →  "Am I allowed to call this API?"       (Security)
X-Doctor-Id       →  "Which doctor is doing this?"          (Business logic)
Idempotency-Key   →  "Don't process this request twice"     (Retry safety)
```

> **Dev mode**: When `NANOCARE_API_KEY` is NOT set in `.env`, the `X-API-Key` header is not required.

## Sample Values

```text
Base URL: http://localhost:8001/api/v1/wellness
Doctor ID: doc_123
Patient ID: PAT-99120
Draft ID: draft_e994e65c0630e105
Report ID: report_e994e65c0630e105
```

## 1. Health Check

Use this first to confirm the API base URL is correct.

```bash
curl --location "http://localhost:8001/api/v1/wellness/health"
```

Expected response shape:

```json
{
  "service": "Nanocare Wellness Report Engine",
  "api_version": "v1"
}
```

## 2. Create Draft

Doctor/integration endpoint. Creates a draft only. It does not publish to the customer and does not generate the final PDF.

Required files: `ecg`, `hrv`, `nadi`, `biowell`, `biores`, `inbody`.

Optional file: `dmit`.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/drafts" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123" \
  --header "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  --form "ecg=@/absolute/path/ecg_report.pdf" \
  --form "hrv=@/absolute/path/hrv_report.pdf" \
  --form "nadi=@/absolute/path/nadi_report.pdf" \
  --form "biowell=@/absolute/path/biowell_report.pdf" \
  --form "biores=@/absolute/path/bioresonance_report.pdf" \
  --form "inbody=@/absolute/path/inbody_scan.jpg" \
  --form "dmit=@/absolute/path/dmit_report.pdf" \
  --form "patient_id=PAT-99120" \
  --form "name=Patient001" \
  --form "dob=2004-05-06" \
  --form "date=2026-06-19" \
  --form "doctor_id=doc_123"
```

Important response fields:

```json
{
  "draft_id": "draft_...",
  "patient_id": "PAT-99120",
  "status": "draft",
  "created_by_doctor_id": "doc_123",
  "cached": false,
  "report": {
    "patient": {},
    "metrics": {},
    "dimensions": {},
    "body_systems": {},
    "functional_summary": {},
    "dmit_summary": {},
    "wellness_offerings": {},
    "biorhythm_calendar": {}
  }
}
```

Notes:

- Reusing the same `Idempotency-Key` returns the existing draft.
- Sending the same files and patient inputs can also return an existing cached draft.
- `dmit_summary.personality` uses patient-safe wording such as `Calm / Reasonable`, not raw DMIT labels.

## 3. Get Draft

Doctor review endpoint. Use this after draft creation or when reopening a review screen.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/drafts/draft_e994e65c0630e105" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

Response:

```json
{
  "draft_id": "draft_...",
  "report_id": "",
  "patient_id": "PAT-99120",
  "status": "draft",
  "created_by_doctor_id": "doc_123",
  "report": {}
}
```

## 4. Edit Draft

Deep-merges changed fields into the draft JSON. Send only fields that changed.

```bash
curl --location --request PATCH "http://localhost:8001/api/v1/wellness/reports/drafts/draft_e994e65c0630e105" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123" \
  --header "Content-Type: application/json" \
  --data '{
    "report": {
      "patient": {
        "name": "Patient001",
        "date": "2026-06-19"
      },
      "dimensions": {
        "physical": {
          "score": 78,
          "description": "Updated physical summary."
        }
      },
      "systems": {
        "nervous": {
          "score": 82,
          "status": "Normal",
          "displayStatus": "Normal"
        }
      },
      "system_summaries": {
        "nervous": "Updated functional summary for nervous system."
      },
      "wellness": {
        "diet": "Updated diet guidance.",
        "sleep": "Updated sleep guidance."
      }
    }
  }'
```

Notes:

- Editing `patient.dob` or `patient.date` recalculates the biorhythm calendar.
- Approved drafts cannot be edited.

## 5. Approve Draft

Doctor endpoint. Generates PDF, saves approved report, saves history, and makes it visible to customer endpoints.

```bash
curl --location --request POST "http://localhost:8001/api/v1/wellness/reports/drafts/draft_e994e65c0630e105/approve" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

Important response fields:

```json
{
  "report_id": "report_...",
  "draft_id": "draft_...",
  "status": "approved",
  "links": {
    "report_json": "/api/v1/wellness/reports/report_...",
    "report_summary": "/api/v1/wellness/reports/report_.../summary",
    "pdf_download": "/api/v1/wellness/reports/report_.../pdf"
  },
  "download_requires": "X-API-Key header",
  "report": {},
  "summary": {},
  "history": {}
}
```

Use `links.pdf_download` for the PDF request. It is an authenticated API path, so send `X-API-Key`.

Calling approve again on the same draft is idempotent. It returns the existing approved report instead of generating a duplicate.

## 6. List Patient Drafts

Doctor endpoint. Lists drafts and approved workflow rows for one patient.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/drafts?limit=10" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

## 7. Get Active Draft

Doctor endpoint. Returns the latest draft with status `draft`.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/active-draft" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

Returns `404` when no active draft exists.

## 8. Customer Dashboard

Customer/mobile endpoint. Returns approved reports only. Drafts are never exposed here.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/dashboard?limit=10" \
  --header "X-API-Key: your-secret-key"
```

Important response fields:

```json
{
  "patient_id": "PAT-99120",
  "patient": {},
  "latest_report": {
    "report_id": "report_...",
    "summary": {},
    "metrics": {},
    "body_systems": {},
    "functional_summary": {},
    "dmit": {},
    "wellness_offerings": {},
    "biorhythm_calendar": {
      "month_name": "June 2026",
      "days": [],
      "watch_days": []
    }
  },
  "history": {},
  "reports": []
}
```

## 9. List Approved Reports

Customer/mobile endpoint. Use this for report history cards.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/reports?limit=20" \
  --header "X-API-Key: your-secret-key"
```

## 10. Get Approved Report

Customer/mobile endpoint. Returns the full approved report JSON.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/report_e994e65c0630e105?detail=full" \
  --header "X-API-Key: your-secret-key"
```

Use this when the user opens a complete report detail screen.

## 11. Get Report Summary

Customer/mobile endpoint. Compact payload for cards and list/detail previews.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/report_e994e65c0630e105/summary" \
  --header "X-API-Key: your-secret-key"
```

## 12. Download PDF

Customer/mobile endpoint. Streams the approved PDF.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/report_e994e65c0630e105/pdf" \
  --header "X-API-Key: your-secret-key" \
  --output wellness_report.pdf
```

## Recommended Postman Test Flow

1. `GET /health`
2. `POST /reports/drafts`
3. Copy `draft_id`
4. `GET /reports/drafts/{draft_id}`
5. `PATCH /reports/drafts/{draft_id}`
6. `POST /reports/drafts/{draft_id}/approve`
7. Copy `report_id`
8. `GET /patients/{patient_id}/dashboard`
9. `GET /reports/{report_id}/summary`
10. `GET /reports/{report_id}`
11. `GET /reports/{report_id}/pdf`

## Common Errors

| Status | Meaning | Usual Fix |
|--------|---------|-----------|
| `401` | Invalid or missing API key | Add `X-API-Key` header or check `.env` |
| `400` | Missing required field | Include `patient_id` and required files |
| `404` | Draft/report not found | Check `draft_id`, `report_id`, or approval status |
| `409` | Workflow conflict | Do not edit approved drafts |
| `500` | PDF/DB/internal failure | Check server logs |
