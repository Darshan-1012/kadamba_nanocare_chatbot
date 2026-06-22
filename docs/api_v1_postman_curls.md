# Nanocare Wellness v1 API - Postman cURL Cookbook

Use only these endpoints for new integrations.

Base URL:

```text
http://localhost:8001/api/v1/wellness
```

In Postman, choose **Import -> Raw text**, paste any cURL below, and replace the placeholder IDs/file paths.

Do not use deprecated routes under `/api/generate`, `/api/doctor/*`, or `/api/user/*` for new web/mobile work.

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
  --header "X-Doctor-Id: doc_123"
```

Important response fields:

```json
{
  "report_id": "report_...",
  "draft_id": "draft_...",
  "status": "approved",
  "generated_report": "http://localhost:8001/api/v1/wellness/reports/report_.../pdf",
  "report": {},
  "summary": {},
  "history": {}
}
```

Calling approve again on the same draft is idempotent. It returns the existing approved report instead of generating a duplicate.

## 6. List Patient Drafts

Doctor endpoint. Lists drafts and approved workflow rows for one patient.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/drafts?limit=10" \
  --header "X-Doctor-Id: doc_123"
```

## 7. Get Active Draft

Doctor endpoint. Returns the latest draft with status `draft`.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/active-draft" \
  --header "X-Doctor-Id: doc_123"
```

Returns `404` when no active draft exists.

## 8. Customer Dashboard

Customer/mobile endpoint. Returns approved reports only. Drafts are never exposed here.

```bash
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/dashboard?limit=10"
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
curl --location "http://localhost:8001/api/v1/wellness/patients/PAT-99120/reports?limit=20"
```

## 10. Get Approved Report

Customer/mobile endpoint. Returns the full approved report JSON.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/report_e994e65c0630e105?detail=full"
```

Use this when the user opens a complete report detail screen.

## 11. Get Report Summary

Customer/mobile endpoint. Compact payload for cards and list/detail previews.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/report_e994e65c0630e105/summary"
```

## 12. Download PDF

Customer/mobile endpoint. Streams the approved PDF.

```bash
curl --location "http://localhost:8001/api/v1/wellness/reports/report_e994e65c0630e105/pdf" \
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
| `400` | Missing required field | Include `patient_id` and required files |
| `404` | Draft/report not found | Check `draft_id`, `report_id`, or approval status |
| `409` | Workflow conflict | Do not edit approved drafts |
| `500` | PDF/DB/internal failure | Check server logs |
