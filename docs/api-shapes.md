# API shapes (reference)

Request/response shapes worked out so far via the API-roleplay walkthrough (see the 11-scenario task list — this covers scenarios 1–3 only, and scenario 3 itself is still in progress). **This is a partial snapshot, not the full API surface.** Nothing here is implemented yet (`main.py` currently only has read-only `/items` and `/bin`); this is design-stage reference for when `/implement` picks it up.

Not yet covered at all: Procurement Selection propose/decide (scenario 4), PO → Receipt → Stock (scenario 5, and CONTEXT.md currently has no vocabulary for this leg of the pipeline at all), and every Production/QC scenario (6–11: Process Sheet creation, Operation execution, Stage Inspection pass/fail, Outsource/Final inspection, repeat orders).

## Material Request

### Raise — confirmed

```
POST /material-requests
{
  "raised_by": "supervisor_priya",
  "raised_for": "SYNTEGON PO#4521",
  "required_by": "2026-08-15",
  "items": [
    { "item_code": "CU-CO2-BE-PIPE", "qty": 2, "uom": "Nos" }
  ]
}

→ 201 Created
{
  "name": "MAT-MR-2026-00042",
  "bff_status": "PENDING_VALIDATION",
  "raised_by": "supervisor_priya",
  "raised_at": "2026-07-29T10:03:00",
  "raised_for": "SYNTEGON PO#4521",
  "required_by": "2026-08-15",
  "items": [ ... ],
  "rejections": []
}
```

### Validate — confirmed

```
POST /material-requests/{name}/validate
{ "validated_by": "gm_rahul" }

→ 200 OK
{
  ...
  "bff_status": "VALIDATED",
  "validated_by": "gm_rahul",
  "validated_at": "2026-07-29T11:00:00"
}
```

### Reject — confirmed, with snapshot

`snapshot` chosen over relying on Frappe's native document version/change-log: simpler, self-contained on the rejection entry itself, no dependency on ERPNext-side change-tracking config (kept to a minimum for now).

```
POST /material-requests/{name}/reject
{ "by": "gm_rahul", "reason": "Qty exceeds current stock buffer — confirm against client PO first" }

→ 200 OK
{
  "bff_status": "REJECTED",
  "rejections": [
    {
      "reason": "Qty exceeds current stock buffer — confirm against client PO first",
      "by": "gm_rahul",
      "at": "2026-07-29T11:05:00",
      "snapshot": {
        "items": [ { "item_code": "CU-CO2-BE-PIPE", "qty": 2, "uom": "Nos" } ],
        "required_by": "2026-08-15",
        "raised_for": "SYNTEGON PO#4521"
      }
    }
  ]
}
```

Rejections are append-only — a second rejection adds a second entry, never overwrites the first.

### Revise — confirmed

```
POST /material-requests/{name}/revise
{
  "items": [ { "item_code": "CU-CO2-BE-PIPE", "qty": 1, "uom": "Nos" } ],
  "required_by": "2026-08-20"
}

→ 200 OK
{
  ...
  "bff_status": "PENDING_VALIDATION",
  "revised_at": "2026-07-29T11:20:00",
  "items": [ updated ],
  "rejections": [ ...unchanged, never cleared... ]
}
```

Rules confirmed:
- Any Requester may revise a `REJECTED` MR — not restricted to the original `raised_by`.
- Calling `revise` when `bff_status` is anything other than `REJECTED` (e.g. still `PENDING_VALIDATION`) → error.

## RFQ / Quote

### Send — PROVISIONAL, mid-revision

Originally sketched as the BFF composing/sending its own supplier email off a plain `POST /rfqs { suppliers: [...] }` call. That's now superseded: checked live against the actual ERPNext instance (v16.29.0) and confirmed ERPNext's native Request for Quotation doctype already has built-in supplier-email sending — fields `email_template`, `subject`, `message_for_supplier`, `send_attached_files`, `send_document_print`, `letter_head`, `preview` back a native "Send Supplier Emails" action that renders the RFQ as a letterhead-styled PDF and emails it directly. Two Letter Head records already exist in the instance (`Company Letterhead`, `Company Letterhead - Grey`).

Working direction: the BFF should trigger ERPNext's native send action rather than compose email itself. **Not yet finalized**: the concrete BFF-facing request/response shape for that trigger. Also blocked operationally — the live instance currently has 0 Email Account records (no outgoing SMTP wired up) and 0 Supplier records (nothing to send to yet).

### Decline — sketched, not yet confirmed

```
POST /rfqs/{name}/suppliers/{supplier}/decline
{ "reason": "Can't meet the CuCo2Be spec at this volume" }

→ 200 OK
{ "supplier": "SUP-002", "versions": [], "declined_at": "2026-07-29T13:10:00", "decline_reason": "..." }
```

Open questions raised, not yet answered:
- Can a supplier still submit a quote *after* declining, or does decline permanently lock them out of the RFQ?
- Should "no reply yet" (e.g. a supplier who never responds) be represented purely as the absence of `declined_at` and an empty `versions` array, with no separate explicit per-supplier status field?

### Quote version submit — sketched, not yet confirmed

```
POST /rfqs/{name}/suppliers/{supplier}/quotes
{ "price": 12500.00, "currency": "INR", "terms": "30 days", "valid_until": "2026-08-30", "recorded_by": "office_anita" }

→ 200 OK
{
  "supplier": "SUP-001",
  "versions": [
    { "version_index": 1, "price": 12500.00, "currency": "INR", "terms": "30 days",
      "valid_until": "2026-08-30", "received_at": "2026-07-29T14:00:00", "recorded_by": "office_anita" }
  ]
}
```

A later call with a new price appends `version_index: 2` rather than overwriting — Version 1 stays as historical record, per the glossary's "latest always wins, older Versions never re-selectable" rule. Same open-question caveats as Decline above apply (this was sketched before the conversation pivoted to the native-send question, and wasn't explicitly re-confirmed after).
