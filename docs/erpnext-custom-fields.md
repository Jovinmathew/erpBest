# ERPNext custom field provisioning

Manual checklist for Frappe's Customize Form — done once, by hand, before `/implement` can build against Material Request or RFQ endpoints. See ADR 0001 for why this is manual rather than a Frappe custom app, and ADR 0002 for why actor fields are plain strings.

**Status:** fully provisioned against `erpnext.jovsden.space` (Frappe/ERPNext 16.23.0) on 2026-07-30 and verified field-by-field over the REST API. The boxes below are deliberately left unticked so this stays reusable for provisioning a fresh instance.

**Fieldnames below are the real ones — read them literally.** Two conventions are in play and the difference is not cosmetic:

- **Custom fields added to *native* doctypes carry a `custom_` prefix** (`custom_bff_status`, `custom_sent_at`, …). Frappe v15+ applies it automatically to anything added via Customize Form, so a future ERPNext upgrade can't collide with a name we picked. Fields created over the **REST API are not auto-prefixed** — pass `custom_…` explicitly when provisioning that way, or you'll get a bare column that silently diverges from the rest.
- **Fields on our own new doctypes have no prefix** (`reason`, `op_no`, `client`, …). We own those doctypes outright, so there's nothing to collide with and Frappe adds nothing.

The public API in `docs/api-shapes.md` exposes neither form — it maps to its own vocabulary, per CONTEXT.md's rule that the public surface stays free of ERPNext internals.

**On the Module field:** the three *new* doctypes below each need a Module picked at creation time; the custom fields added to native doctypes don't (Customize Form files those under `Custom` automatically). Since ADR 0001 means no custom Frappe app — and with developer mode off Frappe forces `custom = 1` — the choice is cosmetic: it drives workspace/module-list grouping only, writes nothing to disk, and doesn't affect the REST path (`/api/resource/BFF Rejection` either way). Modules are assigned per doctype below.

## New child doctype: "BFF Rejection"

Reused as a Table field on both Material Request and Request for Quotation.

**Module: `Buying`.** No "matching" answer exists — this straddles two parents in different native modules (Material Request is under Stock, Request for Quotation under Buying). Buying wins because a rejection here is a procurement-approval artifact, not a stock one.

- [ ] `reason` — Small Text
- [ ] `by` — Data
- [ ] `at` — Datetime
- [ ] `snapshot` — JSON — a serialized copy of the parent's live-editable fields (MR: native `items`/`schedule_date` plus `custom_raised_for`) at the moment of this rejection. Chosen over relying on Frappe's native document version/change-log: self-contained on the rejection entry itself, no dependency on ERPNext-side change-tracking config. JSON rather than Long Text — Frappe validates the content and still stores it as text.

## Material Request (native doctype) — custom fields

- [ ] `custom_bff_status` — Select: `PENDING_VALIDATION`, `VALIDATED`, `REJECTED`
- [ ] `custom_raised_by` — Data
- [ ] `custom_raised_at` — Datetime
- [ ] `custom_revised_at` — Datetime
- [ ] `custom_validated_by` — Data
- [ ] `custom_validated_at` — Datetime
- [ ] `custom_raised_for` — Data
- [ ] `custom_rejections` — Table → BFF Rejection

Items and the required-by date use Material Request's native fields as-is — no customization needed. Note the native fieldnames are `items` and `schedule_date` (labelled "Required By"); there is no `required_by` field, despite that being the domain term in CONTEXT.md and the public API.

## Request for Quotation (native doctype) — custom fields

- [ ] `custom_bff_status` — Select: `SENT`, `SELECTION_PROPOSED`, `DECIDED`
- [ ] `custom_sent_at` — Datetime
- [ ] `custom_proposed_supplier` — Link: Supplier
- [ ] `custom_proposed_version_index` — Int
- [ ] `custom_proposed_by` — Data
- [ ] `custom_proposed_at` — Datetime
- [ ] `custom_proposed_rationale` — Small Text
- [ ] `custom_final_supplier` — Link: Supplier
- [ ] `custom_final_version_index` — Int
- [ ] `custom_final_by` — Data
- [ ] `custom_final_at` — Datetime
- [ ] `custom_final_remark` — Small Text
- [ ] `custom_rejections` — Table → BFF Rejection

An RFQ is never "raised" or "validated" — those are Material Request gate concepts. If `custom_raised_by`/`custom_validated_*` ever appear here, they were copied across by mistake.

## Request for Quotation Supplier (native child table) — custom fields

All nullable except `custom_bff_quote_status`. One row is appended per new quote Version; the row Frappe creates natively when a supplier is added to the RFQ becomes the first (empty) row.

- [ ] `custom_bff_quote_status` — Select: `PENDING`, `DECLINED`, `QUOTED` — explicit per-supplier state, not inferred from field presence. Starts `PENDING` on send; → `DECLINED` on decline; → `QUOTED` the moment a Version is submitted, including flipping back from `DECLINED` if a supplier quotes after declining (decline stays visible as history, it just stops being the current state — quoting after declining is allowed, not blocked).
- [ ] `custom_version_index` — Int
- [ ] `custom_price` — Currency
- [ ] `custom_currency` — Data
- [ ] `custom_terms` — Small Text
- [ ] `custom_valid_until` — Date
- [ ] `custom_received_at` — Datetime
- [ ] `custom_recorded_by` — Data
- [ ] `custom_declined_at` — Datetime
- [ ] `custom_decline_reason` — Small Text

**Why a separate status field:** RFQ Supplier already has a *native* `quote_status` — a Select with exactly two options, `Pending` and `Received` (confirmed live on 16.23.0). It can't be reused: it has no way to express `DECLINED`, which is a first-class state here carrying `custom_declined_at`/`custom_decline_reason` and the flip-back-to-`QUOTED` rule. Overriding its Options would also collide with ERPNext's own code, which writes `Received` into that field on the supplier-portal path. Note the two fields sit one prefix apart in the field list — `quote_status` is theirs, `custom_bff_quote_status` is ours.

**Known wrinkle:** native RFQ Supplier's own "quote status" indicator assumes one row per supplier; appending multiple version-rows per supplier bends that assumption. Sanity-check it once this is built and testable — if the native indicator misbehaves, it's safe to ignore, since `custom_received_at`/`custom_declined_at`/`custom_bff_quote_status` are the real source of truth, not Frappe's own indicator.

## Purchase Order (native doctype) — custom fields

Created manually by Office once an RFQ is `DECIDED` — never auto-created off a Decide (see `docs/api-shapes.md`). Supplier/items/price are derived from the RFQ's `custom_final_supplier`/`custom_final_version_index` at creation time, not retyped.

- [ ] `custom_rfq` — Link: Request for Quotation
- [ ] `custom_created_by` — Data

Native `status` (Draft / To Receive and Bill / Completed, etc.) is used as-is — no `custom_bff_status` mirror, since a PO has no BFF-specific validation/decision gate layered on top the way MR/RFQ do.

## Purchase Receipt (native doctype) — custom fields

Supports multiple partial receipts against one Purchase Order (native `per_received` tracking handles this with no extra work). `accepted_qty`/`rejected_qty` are native fields; ERPNext natively routes accepted stock to the default warehouse and rejected stock to a Rejected Warehouse.

- [ ] `custom_received_by` — Data

## New doctype: "Process Sheet"

**Module: `Manufacturing`.** Autoname `PS-.YYYY.-.#####`, giving the `PS-2026-00005` form `docs/api-shapes.md` uses. See ADR 0003 for why this is a new doctype rather than native Work Order/Job Card. Created with header fields only — `operations` starts empty; rows get added later as work actually happens (see Process Sheet Operation below). `attachment` is set via Frappe's native `upload_file` endpoint first (getting back a file URL), then referenced here — this endpoint itself stays plain JSON, no multipart handling.

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

- [ ] `custom_op_no` — Int (which Process Sheet Operation this inspection covers)

**Resolved wrinkle — native `reference_type` cannot point at a Process Sheet.** ADR 0003 left this open; checked live on 16.23.0, `reference_type` is a **Select**, not a Link, with a closed list: `Purchase Receipt`, `Purchase Invoice`, `Subcontracting Receipt`, `Delivery Note`, `Sales Invoice`, `Stock Entry`, `Job Card`. `reference_name` is a Dynamic Link driven by it. "Process Sheet" is not in the list and can only be added by overriding the Select's Options via a Property Setter — which would then feed a value ERPNext's own Quality Inspection code doesn't expect on paths that branch on `reference_type`.

So the parent link needs deciding before Stage Inspection is built; it is the one point ADR 0003 flagged as needing revisiting, and it does. This doc records the finding only — see the ADR for the decision.
