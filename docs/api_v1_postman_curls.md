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
| Upload | `POST` | `/doctor/drafts` | Upload device files and create a temporary editable draft. |
| Draft view | `GET` | `/doctor/drafts/{draft_id}` | Reopen/review the draft JSON. |
| Draft dashboard | `GET` | `/doctor/drafts/{draft_id}/dashboard` | Use the returned draft `report` sections: metrics, dimensions, body systems, DMIT, offerings, and biorhythm. |
| Edit draft | `PATCH` | `/doctor/drafts/{draft_id}` | Save doctor edits before approval. |
| Approve draft | `POST` | `/doctor/drafts/{draft_id}/approve` | Finalize the draft into an approved report. |
| Patient list | `GET` | `/doctor/patients?limit=100` | List patients that have draft/report workflow activity. |
| Patient draft/workflow list | `GET` | `/doctor/patients/{patient_id}/drafts?limit=10` | Doctor-side draft workflow rows for one patient. |
| Patient approved reports | `GET` | `/doctor/patients/{patient_id}/reports?limit=20` | Doctor view of approved report list. |
| Final report | `GET` | `/doctor/reports/{report_id}?detail=full` | Read the final approved report after approval. |

### Patient / Customer Side

| Screen / Action | Method | Endpoint | Use For |
|-----------------|--------|----------|---------|
| Patient dashboard | `GET` | `/patients/{patient_id}/dashboard?limit=10` | Latest approved report, chart history, cards, and dashboard sections. |
| Patient report list | `GET` | `/patients/{patient_id}/reports?limit=20` | Approved report cards/list only. |
| Patient history | `GET` | `/patients/{patient_id}/history?limit=20` | Chart/trend history only: dates, stats, dimensions, systems. |
| Final report | `GET` | `/patients/{patient_id}/reports/{report_id}?detail=full` | Same approved final report JSON, scoped to patient. |
| Report summary | `GET` | `/patients/{patient_id}/reports/{report_id}/summary` | Compact report payload for cards/previews. |
| PDF download | `GET` | `/patients/{patient_id}/reports/{report_id}/pdf` | Download/open final PDF. Send `X-API-Key`; prefer `links.patient_pdf_download`. |

Do not call `/doctor/*` or draft endpoints from patient/customer apps.

Older mixed v1 paths such as `/reports/drafts/*` and `/reports/{report_id}` still work as transitional aliases, but new integrations should use the role-based paths above.

Link naming rule: approval responses can include both `doctor_*` and `patient_*` links. Patient dashboard/history/detail responses should use only `patient_*` links.

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
Idempotency-Key   →  "Don't process this exact request twice" (Retry safety)
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
curl --location "http://localhost:8001/api/v1/wellness/doctor/drafts" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123" \
  --header "Idempotency-Key: {{$guid}}" \
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

- Reusing the same `Idempotency-Key` with the same files and patient inputs returns the existing draft.
- Reusing the same `Idempotency-Key` after changing files, name, DOB, patient ID, or report date returns `409 idempotency_key_conflict`.
- In Postman, use `{{$guid}}` for normal draft creation tests so each changed request gets a new key.
- Sending the same files and patient inputs can also return an existing cached draft.
- `dmit_summary.personality` uses patient-safe wording such as `Calm / Reasonable`, not raw DMIT labels.

## 3. Get Draft

Doctor review endpoint. Use this after draft creation or when reopening a review screen.

```bash
curl --location "http://localhost:8001/api/v1/wellness/doctor/drafts/draft_e994e65c0630e105" \
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
curl --location --request PATCH "http://localhost:8001/api/v1/wellness/doctor/drafts/draft_e994e65c0630e105" \
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
curl --location --request POST "http://localhost:8001/api/v1/wellness/doctor/drafts/draft_e994e65c0630e105/approve" \
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
    "doctor_report": "/api/v1/wellness/doctor/reports/report_...",
    "doctor_report_summary": "/api/v1/wellness/doctor/reports/report_.../summary",
    "doctor_pdf_download": "/api/v1/wellness/doctor/reports/report_.../pdf",
    "patient_report": "/api/v1/wellness/patients/PAT-99120/reports/report_...",
    "patient_report_summary": "/api/v1/wellness/patients/PAT-99120/reports/report_.../summary",
    "patient_pdf_download": "/api/v1/wellness/patients/PAT-99120/reports/report_.../pdf"
  },
  "download_requires": "X-API-Key header",
  "report": {},
  "summary": {},
  "history": {}
}
```

Use `links.doctor_pdf_download` on doctor screens and `links.patient_pdf_download` on patient screens. Both require `X-API-Key`.

Calling approve again on the same draft is idempotent. It returns the existing approved report instead of generating a duplicate.

## 6. Doctor Patient List

Doctor endpoint. Lists patients with workflow activity.

```bash
curl --location "http://localhost:8001/api/v1/wellness/doctor/patients?limit=100" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

## 7. List Patient Drafts

Doctor endpoint. Lists drafts and approved workflow rows for one patient.

```bash
curl --location "http://localhost:8001/api/v1/wellness/doctor/patients/PAT-99120/drafts?limit=10" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

## 8. Get Active Draft

Doctor endpoint. Returns the latest draft with status `draft`.

```bash
curl --location "http://localhost:8001/api/v1/wellness/doctor/patients/PAT-99120/active-draft" \
  --header "X-API-Key: your-secret-key" \
  --header "X-Doctor-Id: doc_123"
```

Returns `404` when no active draft exists.

## 9. Patient Dashboard

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

## 10. Patient Report List

Customer/mobile endpoint. Use this for approved report cards/list.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/reports?limit=20" \
  --header "X-API-Key: your-secret-key"
```

Response shape:

```json
{
  "patient_id": "PAT-99120",
  "reports": [],
  "total": 0
}
```

## 11. Patient History

Customer/mobile endpoint. Use this for chart/trend history only.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/history?limit=20" \
  --header "X-API-Key: your-secret-key"
```

Response shape:

```json
{
  "patient_id": "PAT-99120",
  "history": {
    "dates": [],
    "stats": {},
    "dimensions": {},
    "systems": {},
    "visit_count": 0
  }
}
```

## 12. Patient Final Report

Customer/mobile endpoint. Returns the full approved report JSON.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/reports/report_e994e65c0630e105?detail=full" \
  --header "X-API-Key: your-secret-key"
```

Use this when the user opens a complete report detail screen.

## 13. Patient Report Summary

Customer/mobile endpoint. Compact payload for cards and list/detail previews.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/reports/report_e994e65c0630e105/summary" \
  --header "X-API-Key: your-secret-key"
```

## 14. Patient PDF Download

Customer/mobile endpoint. Streams the approved PDF.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/reports/report_e994e65c0630e105/pdf" \
  --header "X-API-Key: your-secret-key" \
  --output wellness_report.pdf
```

## Recommended Postman Test Flow

1. `GET /health`
2. `POST /doctor/drafts`
3. Copy `draft_id`
4. `GET /doctor/drafts/{draft_id}`
5. `PATCH /doctor/drafts/{draft_id}`
6. `POST /doctor/drafts/{draft_id}/approve`
7. Copy `report_id`
8. `GET /patients/{patient_id}/dashboard`
9. `GET /patients/{patient_id}/reports`
10. `GET /patients/{patient_id}/history`
11. `GET /patients/{patient_id}/reports/{report_id}/summary`
12. `GET /patients/{patient_id}/reports/{report_id}`
13. `GET /patients/{patient_id}/reports/{report_id}/pdf`

## Common Errors

| Status | Meaning | Usual Fix |
|--------|---------|-----------|
| `401` | Invalid or missing API key | Add `X-API-Key` header or check `.env` |
| `400` | Missing required field | Include `patient_id` and required files |
| `404` | Draft/report not found | Check `draft_id`, `report_id`, or approval status |
| `409` | Workflow/idempotency conflict | Do not edit approved drafts; use a new `Idempotency-Key` when draft inputs change |
| `500` | PDF/DB/internal failure | Check server logs |
