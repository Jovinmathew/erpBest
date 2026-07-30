# ERPNext custom field provisioning

Manual checklist for Frappe's Customize Form — done once, by hand, before `/implement` can build against Material Request or RFQ endpoints. See ADR 0001 for why this is manual rather than a Frappe custom app, and ADR 0002 for why actor fields are plain strings.

**On the Module field:** the three *new* doctypes below each need a Module picked at creation time; the custom fields added to native doctypes don't (Customize Form files those under `Custom` automatically). Since ADR 0001 means no custom Frappe app — and with developer mode off Frappe forces `custom = 1` — the choice is cosmetic: it drives workspace/module-list grouping only, writes nothing to disk, and doesn't affect the REST path (`/api/resource/BFF Rejection` either way). Modules are assigned per doctype below.

## New child doctype: "BFF Rejection"

Reused as a Table field on both Material Request and Request for Quotation.

**Module: `Buying`.** No "matching" answer exists — this straddles two parents in different native modules (Material Request is under Stock, Request for Quotation under Buying). Buying wins because a rejection here is a procurement-approval artifact, not a stock one.

- [ ] `reason` — Small Text
- [ ] `by` — Data
- [ ] `at` — Datetime
- [ ] `snapshot` — Long Text (JSON) — a serialized copy of the parent's live-editable fields (MR: `items`/`required_by`/`raised_for`) at the moment of this rejection. Chosen over relying on Frappe's native document version/change-log: self-contained on the rejection entry itself, no dependency on ERPNext-side change-tracking config.

## Material Request (native doctype) — custom fields

- [ ] `bff_status` — Select: `PENDING_VALIDATION`, `VALIDATED`, `REJECTED`
- [ ] `raised_by` — Data
- [ ] `raised_at` — Datetime
- [ ] `revised_at` — Datetime
- [ ] `validated_by` — Data
- [ ] `validated_at` — Datetime
- [ ] `raised_for` — Data
- [ ] `rejections` — Table → BFF Rejection

Items and `required_by` use Material Request's native fields as-is — no customization needed.

## Request for Quotation (native doctype) — custom fields

- [ ] `bff_status` — Select: `SENT`, `SELECTION_PROPOSED`, `DECIDED`
- [ ] `sent_at` — Datetime
- [ ] `proposed_supplier` — Link: Supplier
- [ ] `proposed_version_index` — Int
- [ ] `proposed_by` — Data
- [ ] `proposed_at` — Datetime
- [ ] `proposed_rationale` — Small Text
- [ ] `final_supplier` — Link: Supplier
- [ ] `final_version_index` — Int
- [ ] `final_by` — Data
- [ ] `final_at` — Datetime
- [ ] `final_remark` — Small Text
- [ ] `rejections` — Table → BFF Rejection

## Request for Quotation Supplier (native child table) — custom fields

All nullable except `quote_status`. One row is appended per new quote Version; the row Frappe creates natively when a supplier is added to the RFQ becomes the first (empty) row.

- [ ] `quote_status` — Select: `PENDING`, `DECLINED`, `QUOTED` — explicit per-supplier state, not inferred from field presence. Starts `PENDING` on send; → `DECLINED` on decline; → `QUOTED` the moment a Version is submitted, including flipping back from `DECLINED` if a supplier quotes after declining (decline stays visible as history, it just stops being the current state — quoting after declining is allowed, not blocked).
- [ ] `version_index` — Int
- [ ] `price` — Currency
- [ ] `currency` — Data
- [ ] `terms` — Small Text
- [ ] `valid_until` — Date
- [ ] `received_at` — Datetime
- [ ] `recorded_by` — Data
- [ ] `declined_at` — Datetime
- [ ] `decline_reason` — Small Text

**Known wrinkle:** native RFQ Supplier's own "quote status" indicator assumes one row per supplier; appending multiple version-rows per supplier bends that assumption. Sanity-check it once this is built and testable — if the native indicator misbehaves, it's safe to ignore, since `received_at`/`declined_at`/our own `quote_status` here are the real source of truth, not Frappe's own indicator.

## Purchase Order (native doctype) — custom fields

Created manually by Office once an RFQ is `DECIDED` — never auto-created off a Decide (see `docs/api-shapes.md`). Supplier/items/price are derived from the RFQ's `final_supplier`/`final_version_index` at creation time, not retyped.

- [ ] `rfq` — Link: Request for Quotation
- [ ] `created_by` — Data

Native `status` (Draft / To Receive and Bill / Completed, etc.) is used as-is — no `bff_status` mirror, since a PO has no BFF-specific validation/decision gate layered on top the way MR/RFQ do.

## Purchase Receipt (native doctype) — custom fields

Supports multiple partial receipts against one Purchase Order (native `per_received` tracking handles this with no extra work). `accepted_qty`/`rejected_qty` are native fields; ERPNext natively routes accepted stock to the default warehouse and rejected stock to a Rejected Warehouse.

- [ ] `received_by` — Data

## New doctype: "Process Sheet"

**Module: `Manufacturing`.** See ADR 0003 for why this is a new doctype rather than native Work Order/Job Card. Created with header fields only — `operations` starts empty; rows get added later as work actually happens (see Process Sheet Operation below). `attachment` is set via Frappe's native `upload_file` endpoint first (getting back a file URL), then referenced here — this endpoint itself stays plain JSON, no multipart handling.

- [ ] `client` — Data
- [ ] `drawing_no` — Data
- [ ] `part_name` — Data
- [ ] `material` — Data
- [ ] `qty` — Data (not Int — source documents use compound values like "1+1")
- [ ] `date` — Date
- [ ] `programmer` — Data
- [ ] `attachment` — Attach
- [ ] `operations` — Table → Process Sheet Operation

## New child doctype: "Process Sheet Operation"

**Module: `Manufacturing`** (same as its parent). Reused as a Table field on Process Sheet. Deliberately has no field describing *what* the operation technically entails (no "operation description" text) — that lives only in the Process Sheet's `attachment`, so nobody (Programmer or Operator) has to retype the drawing's own spec into the system. Rows exist only for operations someone has actually started, created incrementally by whoever executes them — not pre-populated as a full plan at Process Sheet creation time. A rework attempt appends a new row with the same `op_no` rather than overwriting the failed one. `rework`/`rejection` are independent, manually-set facts — never auto-derived from a Quality Inspection's outcome.

- [ ] `op_no` — Int
- [ ] `machine` — Data
- [ ] `operator` — Data
- [ ] `target_qty` — Int
- [ ] `achieved_qty` — Int
- [ ] `date_loaded` — Date
- [ ] `date_unloaded` — Date
- [ ] `rework` — Check
- [ ] `rejection` — Check
- [ ] `remarks` — Small Text

## Quality Inspection (native doctype) — custom fields

Reused as-is for Stage Inspection (see ADR 0003) — only one addition needed. Native `status` (Accepted/Rejected) is explicitly set by the Inspector once they've completed the inspection, not auto-derived from the individual reading rows' own pass/fail values.

- [ ] `op_no` — Int (which Process Sheet Operation this inspection covers; the parent link uses Quality Inspection's native `reference_type`/`reference_name`)

**Known wrinkle (unverified):** whether native `reference_type` accepts a custom doctype ("Process Sheet") at all depends on the ERPNext version in use — check this before building against it; if it doesn't, this is the one point in ADR 0003 that would need revisiting.
