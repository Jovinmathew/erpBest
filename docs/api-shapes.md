# API shapes (reference)

Request/response shapes worked out via the API-roleplay walkthrough — all 11 original scenarios plus two upstream questions raised mid-walkthrough (13 total, all resolved). Nothing here is implemented yet (`main.py` currently only has read-only `/items` and `/bin`, kept purely for manual API testing, not a scoped feature); this is design-stage reference for when `/implement` picks it up.

## Material Request

### Raise
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

### Validate
```
POST /material-requests/{name}/validate
{ "validated_by": "gm_rahul" }

→ 200 OK
{ ..., "bff_status": "VALIDATED", "validated_by": "gm_rahul", "validated_at": "2026-07-29T11:00:00" }
```

### Reject — with snapshot
`snapshot` captures the MR's live fields at the moment of rejection (chosen over relying on Frappe's native document version/change-log — self-contained, no ERPNext-side change-tracking config needed).
```
POST /material-requests/{name}/reject
{ "by": "gm_rahul", "reason": "Qty exceeds current stock buffer — confirm against client PO first" }

→ 200 OK
{
  "bff_status": "REJECTED",
  "rejections": [
    {
      "reason": "Qty exceeds current stock buffer — confirm against client PO first",
      "by": "gm_rahul", "at": "2026-07-29T11:05:00",
      "snapshot": {
        "items": [ { "item_code": "CU-CO2-BE-PIPE", "qty": 2, "uom": "Nos" } ],
        "required_by": "2026-08-15", "raised_for": "SYNTEGON PO#4521"
      }
    }
  ]
}
```
Rejections are append-only — a second rejection adds a second entry, never overwrites the first.

### Revise
```
POST /material-requests/{name}/revise
{ "items": [ { "item_code": "CU-CO2-BE-PIPE", "qty": 1, "uom": "Nos" } ], "required_by": "2026-08-20" }

→ 200 OK
{ ..., "bff_status": "PENDING_VALIDATION", "revised_at": "2026-07-29T11:20:00", "items": [ updated ], "rejections": [ ...unchanged... ] }
```
Rules: any Requester may revise a `REJECTED` MR (not restricted to the original `raised_by`); calling `revise` when `bff_status` isn't `REJECTED` → error.

## RFQ / Quote

### Send
Triggers ERPNext's native supplier-email action rather than the BFF composing its own (see ADR 0004). The BFF: creates the native RFQ doc, copies any Frappe File attachments from the Material Request onto the RFQ (native send only carries attachments already on the RFQ itself), then submits it, firing the native email.
```
POST /rfqs
{
  "material_request": "MAT-MR-2026-00042",
  "suppliers": ["SUP-001", "SUP-002", "SUP-003"],
  "sent_by": "office_anita",
  "letter_head": "Company Letterhead",
  "subject": "Request for Quotation — SYNTEGON Cross Seal Roller raw material",
  "message_for_supplier": "Please find attached our RFQ. Kindly respond with pricing and terms by 2026-08-10.",
  "use_html": false,
  "message_for_supplier_html": null
}

→ 201 Created
{
  "name": "RFQ-2026-00017",
  "bff_status": "SENT",
  "sent_at": "2026-07-29T12:00:00",
  "sent_by": "office_anita",
  "material_request": "MAT-MR-2026-00042",
  "quotes": [
    { "supplier": "SUP-001", "quote_status": "PENDING", "versions": [] },
    { "supplier": "SUP-002", "quote_status": "PENDING", "versions": [] },
    { "supplier": "SUP-003", "quote_status": "PENDING", "versions": [] }
  ]
}
```
`letter_head`/`subject`/`message_for_supplier` are **required** on every send — no default boilerplate, Office makes a deliberate call on wording each time. `use_html`/`message_for_supplier_html` map to native `use_html`/`mfs_html` for formatted (bold/bullets) messages. If no Email Account is configured in ERPNext, submit raises `OutgoingEmailError` — surface as a clear `424 Failed Dependency`, don't swallow it. Native send also activates ERPNext's Supplier Portal (suppliers can self-submit a native Supplier Quotation) — deliberately ignored, see ADR 0004; resend/reminder is out of scope for now.

### Decline
```
POST /rfqs/{name}/suppliers/{supplier}/decline
{ "reason": "Can't meet the CuCo2Be spec at this volume" }

→ 200 OK
{ "supplier": "SUP-002", "quote_status": "DECLINED", "declined_at": "2026-07-29T13:10:00",
  "decline_reason": "Can't meet the CuCo2Be spec at this volume", "versions": [] }
```
Declining doesn't lock the supplier out — a later quote flips `quote_status` back to `QUOTED`, `declined_at`/`decline_reason` stay as history.

### Quote version submit
```
POST /rfqs/{name}/suppliers/{supplier}/quotes
{ "price": 12500.00, "currency": "INR", "terms": "30 days", "valid_until": "2026-08-30", "recorded_by": "office_anita" }

→ 200 OK
{
  "supplier": "SUP-001", "quote_status": "QUOTED",
  "versions": [ { "version_index": 1, "price": 12500.00, "currency": "INR", "terms": "30 days",
    "valid_until": "2026-08-30", "received_at": "2026-07-29T14:00:00", "recorded_by": "office_anita" } ]
}
```
A later call appends `version_index: 2` rather than overwriting — older Versions stay as historical record, latest always wins. Versions only store the flat price/currency/terms/valid_until summary Office records — no attachment of the supplier's original quote document (considered, deferred as low priority for now, same gap noted for future revisit as the Process Sheet's own attachment field).

### Selection propose → Decide
```
POST /rfqs/{name}/propose
{ "supplier": "SUP-001", "version_index": 2, "proposed_by": "gm_rahul", "rationale": "Lowest price with acceptable terms" }

→ 200 OK
{ "bff_status": "SELECTION_PROPOSED", "proposed_supplier": "SUP-001", "proposed_version_index": 2,
  "proposed_by": "gm_rahul", "proposed_at": "...", "proposed_rationale": "..." }
```

```
POST /rfqs/{name}/decide
{ "decision": "RATIFY", "final_by": "director_john", "remark": "Agreed, proceed with SUP-001" }
→ 200 OK
{ "bff_status": "DECIDED", "final_supplier": "SUP-001", "final_version_index": 2, "final_by": "director_john", "final_at": "...", "final_remark": "..." }
```
```
POST /rfqs/{name}/decide
{ "decision": "OVERRIDE", "final_supplier": "SUP-002", "final_version_index": 1, "final_by": "director_john", "remark": "Prefer SUP-002 — better track record" }
→ 200 OK
{ "bff_status": "DECIDED", "proposed_supplier": "SUP-001", "proposed_version_index": 2, // kept as history
  "final_supplier": "SUP-002", "final_version_index": 1, "final_by": "director_john", "final_at": "...", "final_remark": "..." }
```
```
POST /rfqs/{name}/decide
{ "decision": "REJECT", "by": "director_john", "reason": "None of these meet our quality bar — get more quotes" }
→ 200 OK
{ "bff_status": "SENT", "proposed_supplier": null, "proposed_version_index": null, "rejections": [ { "reason": "...", "by": "director_john", "at": "..." } ] }
```
Only `REJECT` re-opens the RFQ (back to `SENT`, clearing the proposed fields, rejections list stays append-only) so GM can propose again. `RATIFY`/`OVERRIDE` are terminal — no re-proposing after either.

## Purchase Order → Receipt → Stock

### Purchase Order
Manual only — never auto-created off a Decide. Fields derived from the decided RFQ, not retyped. Blocked unless the RFQ is `DECIDED`.
```
POST /purchase-orders
{ "rfq": "RFQ-2026-00017", "created_by": "office_anita" }

→ 201 Created
{
  "name": "PUR-ORD-2026-00031", "rfq": "RFQ-2026-00017", "supplier": "SUP-002",
  "items": [ { "item_code": "CU-CO2-BE-PIPE", "qty": 1, "rate": 13200.00, "uom": "Nos" } ],
  "status": "To Receive and Bill", "created_by": "office_anita", "created_at": "2026-07-30T09:00:00"
}
```
`status` is ERPNext's own native PO status — no `bff_status` mirror, since a PO has no BFF-specific gate layered on top the way MR/RFQ do.

### Receipt
Native Purchase Receipt, supports multiple partial receipts against one PO (native `per_received` tracking).
```
POST /purchase-receipts
{ "purchase_order": "PUR-ORD-2026-00031", "received_by": "store_person_meena",
  "items": [ { "item_code": "CU-CO2-BE-PIPE", "received_qty": 1, "accepted_qty": 1, "rejected_qty": 0 } ] }

→ 201 Created
{ "name": "MAT-PRE-2026-00019", "purchase_order": "PUR-ORD-2026-00031", "received_by": "store_person_meena",
  "received_at": "2026-08-05T10:15:00", "items": [ ... ], "status": "Completed" }
```
`accepted_qty`/`rejected_qty` are native — ERPNext routes accepted stock to the default warehouse, rejected stock to a Rejected Warehouse, no custom logic.

### Stock
Read-only visibility into ERPNext's native Stock Ledger/Bin, updated automatically on Receipt submit. No issue-to-production or other stock-mutating action in scope for this pilot.

## Process Sheet

### Creation
Header fields only — the Programmer already produces the routing as a document (the attachment); making them re-type all 12 operations into structured fields would be pure duplicate entry for no payoff. `operations` starts empty.
```
POST /process-sheets
{
  "client": "SYNTEGON", "drawing_no": "8-110-505-969", "part_name": "CROSS SEAL ROLLER UPR & LWR",
  "material": "CuCo2Be", "qty": "1+1", "date": "2026-04-06", "programmer": "programmer_ravi",
  "attachment": "/files/PROCESS_SHEET_CSR.pdf"
}

→ 201 Created
{ "name": "PS-2026-00005", ...same fields..., "operations": [] }
```
`attachment` is uploaded via Frappe's native `upload_file` endpoint first (getting back a file URL), then referenced here — this endpoint stays plain JSON, no multipart handling. No `sales_order` link (see CONTEXT.md's Sales Order note) — deliberately kept lean/unlinked for now, even though Sales Order is confirmed as the real upstream entity.

### Operation — load, then unload
No operation *description* field — the technical spec only ever lives in the attached document; the row just records who/what/when. Rows are created incrementally by whoever executes them, not pre-populated as a full plan.
```
POST /process-sheets/{name}/operations
{ "op_no": 3, "machine": "CNC MILLING", "operator": "operator_das", "target_qty": 2, "date_loaded": "2026-04-07" }

→ 200 OK
{ "op_no": 3, "machine": "CNC MILLING", "operator": "operator_das", "target_qty": 2, "achieved_qty": null,
  "date_loaded": "2026-04-07", "date_unloaded": null, "rework": false, "rejection": false, "remarks": null }
```
```
PATCH /process-sheets/{name}/operations/{op_no}
{ "achieved_qty": 2, "date_unloaded": "2026-04-07" }

→ 200 OK
{ ..., "achieved_qty": 2, "date_unloaded": "2026-04-07" }
```
Outsourced operations (e.g. Op 11, "OUTSOURCE" station) reuse this exact same shape — `operator` becomes whoever coordinated sending it out, `date_loaded`/`date_unloaded` become sent-to-vendor/received-back dates. No special vendor/dispatch fields.

### Rework
A rework attempt appends a **new row**, same `op_no`, rather than mutating the failed one — preserves both attempts' history.
```
POST /process-sheets/{name}/operations   // second attempt at op 7
{ "op_no": 7, "machine": "CNC MILLING 4X", "operator": "operator_das", "target_qty": 1, "date_loaded": "2026-04-09" }

PATCH /process-sheets/{name}/operations/7   // this new row
{ "achieved_qty": 1, "date_unloaded": "2026-04-09", "rework": true, "remarks": "Reworked after OD84.64 out of tolerance on first pass" }
```
`rework`/`rejection` are independently, manually recorded facts — never auto-set by a failed Stage Inspection. Whether a rework ever needs to spin off an entirely separate new Process Sheet (vs. staying within the same one, as above) is unresolved — deferred until real data shows the pattern, same treatment as the template/run split below.

### Final Inspection & Dispatch (Op 12)
Just another Operation row + Stage Inspection, same shape as any other op — no separate Process-Sheet-level `dispatched_at`/completion field. A passed Op 12 Stage Inspection is sufficient to consider the job done.

### Repeat orders
A second job against the same drawing is a **fully new, independent Process Sheet** — no structural link back to the earlier one, no drawing-level template entity. This is deferred debt (per ADR 0003) — revisit once enough repeat-order data shows how templates actually vary.
```
POST /process-sheets
{ "client": "SYNTEGON", "drawing_no": "8-110-505-969", "part_name": "CROSS SEAL ROLLER UPR & LWR",
  "material": "CuCo2Be", "qty": "5+5", "date": "2026-09-12", "programmer": "programmer_ravi",
  "attachment": "/files/PROCESS_SHEET_CSR_v2.pdf" }

→ 201 Created
{ "name": "PS-2026-00031", ..., "operations": [] }
```

## Stage Inspection (Quality Inspection)

### Pass
```
POST /quality-inspections
{
  "reference_type": "Process Sheet", "reference_name": "PS-2026-00005", "op_no": 7,
  "inspected_by": "inspector_kavya",
  "readings": [
    { "specification": "1.15°x 3.05 SLT", "tolerance": "+0.05", "reading_1": "1.17 x 3.07", "status": "Accepted" },
    { "specification": "OD Ø84.64", "tolerance": "+0.02", "reading_1": "84.65", "status": "Accepted" },
    { "specification": "OD Ø85.24", "tolerance": "-0.04", "reading_1": "85.21", "status": "Accepted" },
    { "specification": "DIST 34.78", "tolerance": "±0.025", "reading_1": "34.79", "status": "Accepted" },
    { "specification": "PROF. DEEP 0.3", "tolerance": "±0.01", "reading_1": "0.305", "status": "Accepted" }
  ],
  "status": "Accepted"
}

→ 201 Created
{ "name": "QI-2026-00042", "reference_type": "Process Sheet", "reference_name": "PS-2026-00005", "op_no": 7,
  "inspected_by": "inspector_kavya", "inspected_at": "2026-04-08T11:00:00", "status": "Accepted", "readings": [ ... ] }
```
Each reading row keeps `reading_1`..`reading_10` available (the paper document's own 1–10 sample columns), even though most jobs only fill `reading_1`. Top-level `status` is explicitly set by the Inspector once they complete the inspection — never auto-derived from the individual readings' own pass/fail values.

### Fail
Same shape, one or more readings `"status": "Rejected"`, overall `"status": "Rejected"` — see Process Sheet's Rework section above for what happens next (independent, manually recorded `rework`/`rejection` on a new Operation row).

## Upstream: how a job enters the system at all

**Resolved as Sales Order, not a bespoke doctype.** A client (e.g. SYNTEGON) issues us a formal PO first — that's the real first step, not just an inbound email. ERPNext's native Sales Order already models this (confirmed live against the v16.29.0 instance): `customer` (Link), `po_no` (Data), `po_date` (Date), `items`, `delivery_date`. Whoever receives the client's PO creates a Sales Order from it — that's the intake record and the handoff point between whoever received it and whoever acts on it next (e.g. the Programmer building a Process Sheet).

A custom "Client Request" doctype (logging received_by/received_at/attachment/status purely to bridge that handoff) was proposed and **dropped** once Sales Order was confirmed to already cover the need natively.

**Deliberately not yet linked** to either Material Request or Process Sheet — `raised_for` and `client`/`drawing_no` both stay free-text, no `sales_order` Link field on either. Sales Order is confirmed as the right conceptual anchor, but wiring an actual structural link is being kept lean until a real need to query across it is observed, consistent with every other "don't build ahead of what's known" call made throughout this design.
