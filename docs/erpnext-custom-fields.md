# ERPNext custom field provisioning

Manual checklist for Frappe's Customize Form — done once, by hand, before `/implement` can build against Material Request or RFQ endpoints. See ADR 0001 for why this is manual rather than a Frappe custom app, and ADR 0002 for why actor fields are plain strings.

## New child doctype: "BFF Rejection"

Reused as a Table field on both Material Request and Request for Quotation.

- [ ] `reason` — Small Text
- [ ] `by` — Data
- [ ] `at` — Datetime

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

All nullable. One row is appended per new quote Version; the row Frappe creates natively when a supplier is added to the RFQ becomes the first (empty) row.

- [ ] `version_index` — Int
- [ ] `price` — Currency
- [ ] `currency` — Data
- [ ] `terms` — Small Text
- [ ] `valid_until` — Date
- [ ] `received_at` — Datetime
- [ ] `recorded_by` — Data
- [ ] `declined_at` — Datetime
- [ ] `decline_reason` — Small Text

**Known wrinkle:** native RFQ Supplier's own "quote status" indicator assumes one row per supplier; appending multiple version-rows per supplier bends that assumption. Sanity-check it once this is built and testable — if the native indicator misbehaves, it's safe to ignore, since `received_at`/`declined_at` here are the real source of truth, not Frappe's own indicator.

## New doctype: "Process Sheet"

See ADR 0003 for why this is a new doctype rather than native Work Order/Job Card.

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

Reused as a Table field on Process Sheet.

- [ ] `op_no` — Int
- [ ] `operation` — Small Text
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

Reused as-is for Stage Inspection (see ADR 0003) — only one addition needed.

- [ ] `op_no` — Int (which Process Sheet Operation this inspection covers; the parent link uses Quality Inspection's native `reference_type`/`reference_name`)

**Known wrinkle (unverified):** whether native `reference_type` accepts a custom doctype ("Process Sheet") at all depends on the ERPNext version in use — check this before building against it; if it doesn't, this is the one point in ADR 0003 that would need revisiting.
