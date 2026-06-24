# Nanocare Wellness v1 Frontend Integration Guide

This guide is for web and mobile teams. Use only the v1 API base:

```text
http://localhost:8001/api/v1/wellness
```

Avoid deprecated routes:

```text
/api/generate
/api/doctor/*
/api/user/*
```

When `NANOCARE_API_KEY` is set, every protected request must include:

```http
X-API-Key: your-secret-key
```

## Roles

Doctor/integration screens:

- Create a draft.
- Review and edit draft JSON.
- Approve the draft.
- Open the final PDF/customer view after approval.

Customer/patient screens:

- Read approved reports only.
- Show dashboard, history, report cards, biorhythm calendar, DMIT, body systems, wellness offerings, and PDF.
- Never call draft endpoints from a customer app.

## Route Map

Health check:

| Screen/Use Case | Method | Endpoint |
|-----------------|--------|----------|
| Health check | `GET` | `/health` |

Doctor side:

| Screen/Use Case | Method | Endpoint | Render/Store |
|-----------------|--------|----------|--------------|
| Upload | `POST` | `/doctor/drafts` | Store `draft_id`; render returned draft `report`. |
| Draft view/dashboard | `GET` | `/doctor/drafts/{draft_id}/dashboard` | Render editable draft dashboard from `report`. |
| Edit draft | `PATCH` | `/doctor/drafts/{draft_id}` | Save changed draft fields. |
| Approve draft | `POST` | `/doctor/drafts/{draft_id}/approve` | Store `report_id`; draft becomes final report. |
| Patient list | `GET` | `/doctor/patients?limit=100` | Show patients with workflow activity. |
| Patient draft/workflow list | `GET` | `/doctor/patients/{patient_id}/drafts?limit=10` | Doctor-only draft workflow list. |
| Patient approved reports | `GET` | `/doctor/patients/{patient_id}/reports?limit=20` | Doctor can view approved report list. |
| Final report | `GET` | `/doctor/reports/{report_id}?detail=full` | Render approved read-only report. |

Patient/customer side:

| Screen/Use Case | Method | Endpoint | Render/Store |
|-----------------|--------|----------|--------------|
| Patient dashboard | `GET` | `/patients/{patient_id}/dashboard?limit=10` | Latest approved report, history, charts, cards. |
| Patient report list | `GET` | `/patients/{patient_id}/reports?limit=20` | Approved report cards/list only. |
| Patient history | `GET` | `/patients/{patient_id}/history?limit=20` | Chart/trend history only: dates, stats, dimensions, systems. |
| Final report | `GET` | `/patients/{patient_id}/reports/{report_id}?detail=full` | Same approved read-only report, scoped to patient. |
| Report summary | `GET` | `/patients/{patient_id}/reports/{report_id}/summary` | Compact payload for cards/previews. |
| PDF | `GET` | `/patients/{patient_id}/reports/{report_id}/pdf` | Fetch with `X-API-Key`; prefer `links.patient_pdf_download`. |

Patient/customer apps must not call `/doctor/*` or draft endpoints.

Older mixed v1 paths such as `/reports/drafts/*` and `/reports/{report_id}` still work as transitional aliases, but new integrations should use the role-based paths above.

Link naming rule: approval responses can include both `doctor_*` and `patient_*` links. Patient dashboard/history/detail responses should use only `patient_*` links.

## Doctor Web Flow

1. Collect patient details and files.
2. `POST /doctor/drafts` with multipart form data.
3. Store `draft_id`.
4. Render editable sections from `response.report`.
5. Save edits with `PATCH /doctor/drafts/{draft_id}`.
6. Approve with `POST /doctor/drafts/{draft_id}/approve`.
7. Store `report_id` and show PDF/customer links.

### Doctor Create Draft

Browser example:

```js
async function createDraft(baseUrl, apiKey, doctorId, formState, files) {
  const form = new FormData();
  form.append("ecg", files.ecg);
  form.append("hrv", files.hrv);
  form.append("nadi", files.nadi);
  form.append("biowell", files.biowell);
  form.append("biores", files.biores);
  form.append("inbody", files.inbody);
  if (files.dmit) form.append("dmit", files.dmit);
  form.append("patient_id", formState.patientId);
  form.append("name", formState.name);
  form.append("dob", formState.dob);
  form.append("date", formState.reportDate);
  form.append("doctor_id", doctorId);

  const res = await fetch(`${baseUrl}/doctor/drafts`, {
    method: "POST",
    headers: {
      "X-API-Key": apiKey,
      "X-Doctor-Id": doctorId,
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Do not set `Content-Type` manually for multipart uploads in the browser. Let `fetch` set the boundary.

### Doctor Save Draft Edits

Send only changed fields. The API deep-merges them into the draft.

```js
async function saveDraft(baseUrl, apiKey, doctorId, draftId, patch) {
  const res = await fetch(`${baseUrl}/doctor/drafts/${encodeURIComponent(draftId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
      "X-Doctor-Id": doctorId,
    },
    body: JSON.stringify({ report: patch }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Example patch:

```json
{
  "patient": { "name": "Patient001", "date": "2026-06-19" },
  "dimensions": {
    "physical": { "score": 78, "description": "Doctor reviewed summary." }
  },
  "systems": {
    "nervous": { "score": 82, "status": "Normal", "displayStatus": "Normal" }
  },
  "system_summaries": {
    "nervous": "Doctor reviewed functional summary."
  },
  "wellness": {
    "diet": "Doctor reviewed diet guidance."
  }
}
```

If `patient.dob` or `patient.date` changes, the API recalculates the biorhythm calendar.

### Doctor Approve

```js
async function approveDraft(baseUrl, apiKey, doctorId, draftId) {
  const res = await fetch(`${baseUrl}/doctor/drafts/${encodeURIComponent(draftId)}/approve`, {
    method: "POST",
    headers: {
      "X-API-Key": apiKey,
      "X-Doctor-Id": doctorId,
    },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Approval makes the report customer-visible.

## Customer Web/Mobile Flow

1. Load dashboard with `GET /patients/{patient_id}/dashboard?limit=10`.
2. Use `latest_report` for the first screen.
3. Use `reports` from dashboard or `GET /patients/{patient_id}/reports?limit=20` for approved report cards.
4. Use `history` from dashboard or `GET /patients/{patient_id}/history?limit=20` for trend charts.
5. When a user opens a specific report, call `GET /patients/{patient_id}/reports/{report_id}?detail=full`.
6. Use `links.patient_pdf_download` for PDF viewing, and send `X-API-Key`.

### Customer Dashboard

```js
async function loadDashboard(baseUrl, apiKey, patientId) {
  const res = await fetch(`${baseUrl}/patients/${encodeURIComponent(patientId)}/dashboard?limit=10`, {
    headers: { "X-API-Key": apiKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

Use this shape:

```json
{
  "patient": {},
  "latest_report": {
    "report_id": "report_...",
    "summary": {},
    "metrics": {},
    "body_systems": {},
    "functional_summary": {},
    "dmit": {},
    "wellness_offerings": {},
    "biorhythm_calendar": {}
  },
  "history": {},
  "reports": []
}
```

### Customer Report Detail

```js
async function loadReport(baseUrl, apiKey, patientId, reportId) {
  const res = await fetch(`${baseUrl}/patients/${encodeURIComponent(patientId)}/reports/${encodeURIComponent(reportId)}?detail=full`, {
    headers: { "X-API-Key": apiKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

For PDF buttons, fetch the file with the same header:

```js
async function loadPdfBlob(baseUrl, apiKey, pdfPath) {
  const url = new URL(pdfPath, baseUrl).toString();
  const res = await fetch(url, {
    headers: { "X-API-Key": apiKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}
```

## What To Render

Summary tab:

- `summary.physical`
- `summary.psychological`
- `summary.emotional`
- `summary.spiritual`
- `metrics`
- `dimensions.*.description`
- `dimensions.*.summary_points`

Body Systems tab:

- Prefer `body_systems`.
- Show `score`, `displayStatus` or `status`.
- Show `functional_summary`.

DMIT tab:

- Use `dmit` from dashboard/summary payloads, or `report.dmit_summary` from full reports.
- Show brain dominance, TFRC, learning style, planning, multiple intelligences, brain lobes, and SWOT.
- Personality labels are already patient-safe: examples include `Calm / Reasonable`, `Straightforward / Bold`, `Expressive / Social`, `Analytical / Observant`.
- Do not display raw labels such as `Dove`, `Eagle`, `Owl`, or `Peacock`.

Wellness Offerings tab:

- Prefer `wellness_offerings`.
- Suggested groups:
  - `nutrition`
  - `movement`
  - `recovery`
  - `support`
  - `lifestyle`
  - `priority_systems`

Biorhythm tab:

- Prefer `biorhythm_calendar`.
- Use `month_name`, `today`, `days`, and `watch_days`.
- Each item in `days` includes physical, emotional, intellectual percentages and a daily interpretation.
- For mobile, render a compact list by day first; calendar grid can be a secondary view.

PDF:

- Prefer `links.patient_pdf_download` from patient report/summary payloads.
- Prefer `links.doctor_pdf_download` from doctor report/summary payloads.
- Send `X-API-Key` when fetching the PDF.

## Mobile Notes

Recommended mobile loading strategy:

1. Dashboard screen: call `/patients/{patient_id}/dashboard?limit=10`.
2. Report list screen: call `/patients/{patient_id}/reports?limit=20`.
3. Trend/history screen: call `/patients/{patient_id}/history?limit=20`.
4. Report detail screen: call `/patients/{patient_id}/reports/{report_id}?detail=full`.
5. PDF button: fetch `links.patient_pdf_download` with `X-API-Key`, then open the returned file/blob in the platform PDF viewer.
6. Cache `report_id`, `patient_id`, and the latest dashboard response locally.
7. Refresh dashboard after the doctor approves a draft.

React Native multipart upload notes:

- Use `FormData`.
- Include file objects with `uri`, `name`, and `type`.
- Do not manually set multipart boundaries.
- If your networking layer requires `Content-Type`, use `multipart/form-data`, but prefer letting it infer the boundary.

Example file item:

```js
form.append("ecg", {
  uri: fileUri,
  name: "ecg_report.pdf",
  type: "application/pdf",
});
```

## Error Handling

All errors are JSON where possible:

```json
{ "detail": "Draft draft_xyz not found" }
```

Frontend behavior:

- `400`: show missing input/file message.
- `404`: show not found or no approved reports yet.
- `409`: tell the doctor the draft is no longer editable.
- `500`: show retry/support message and log the request ID if your gateway adds one.

## Integration Rules

- Customer apps must never call draft endpoints.
- Doctor apps should not call deprecated `/api/doctor/*` endpoints.
- Store `draft_id` for draft review sessions.
- Store `report_id` after approval.
- Treat report JSON as read-only on customer screens.
- Use `PATCH` only from doctor review screens.
- Use `Idempotency-Key` for draft creation retries; reuse it only for the same request payload.
- Generate a new `Idempotency-Key` when files, name, DOB, patient ID, or report date changes.
