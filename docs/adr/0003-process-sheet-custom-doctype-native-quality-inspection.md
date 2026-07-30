---
status: accepted
---

# Process Sheet as new custom doctype, native Quality Inspection reused for stage inspection, record-keeping only

The production/QC domain — the job-shop routing sheet and per-operation dimensional inspection used by the organization's own shop-floor staff — is added as a second domain on the BFF, scoped to **record-keeping only**: capturing what happened at each operation, not scheduling or driving shop-floor work. No local database; ERPNext remains the sole system of record, extending ADR 0001's pattern to a new domain.

A new custom doctype **Process Sheet** (parent) and child doctype **Process Sheet Operation** are added rather than reusing ERPNext's native Work Order/Job Card. Job Card is a child of Work Order, which itself requires a BOM — machinery for BOM-driven repetitive/discrete manufacturing that this domain has no use for, since scope is record-keeping for job-shop, one-off client parts, not production planning. Forcing a Work Order/BOM into existence purely to unlock Job Card would mean maintaining fake upstream records for data those records don't actually drive — the same shape of problem ADR 0001 already rejected when it declined native Supplier Quotation for being item-line-heavy for a flat-price model.

Native **Quality Inspection** is reused as-is for the stage inspection sub-domain: its parameter + tolerance + numbered-readings shape is a genuine structural match for the organization's Stagewise Inspection Report, unlike Job Card. Quality Inspection connects back to its Process Sheet via its native `reference_type`/`reference_name` dynamic link, plus a new plain `op_no` field — not a link into the Process Sheet Operation child row, since the source document itself treats Op. No as a plain value rather than a foreign key, and Frappe child table rows aren't normally addressable as link targets.

Process Sheet's own descriptive fields (Client, Drawing No, Part Name, Material, Qty) are plain Data fields, not Links to Item or Material Request — same reasoning as MR's `raised_for`: the relationship between this domain and procurement hasn't been observed in practice yet, so it isn't modeled. The original scanned/PDF process sheet is retrievable via a native Frappe `Attach` field, keeping ERPNext the sole store rather than reopening ADR 0001's "no second system of record" decision for file storage.

Process Sheet is a single combined record per job — routing definition and execution actuals (operator, target/achieved qty, load/unload time) live together on the same Process Sheet Operation rows. Three new roles participate — **Programmer** (authors the routing), **Operator** (executes an operation), **Inspector** (records readings) — with roles/permissions deliberately left loose, to be discovered as the domain gets built out further. Actor identity for all three follows ADR 0002 unchanged: plain string fields, static token table, API-first — this phase is being driven directly via API calls before any frontend exists.

**Considered and rejected:**
- **Reusing Job Card/Work Order/BOM for Process Sheet.** Requires standing up BOM + Work Order machinery this record-keeping-only scope has no use for; would mean faking upstream planning records purely to unlock a child doctype.
- **Template/run split** (a separate reusable Process Sheet template vs. per-run actuals, closer to BOM/Work Order's own template/instance split). Repeat orders and templates do exist in practice, but there isn't yet enough data to know how templates actually vary (same tolerances every time? different client, same drawing?) — splitting now risks modeling a relationship that doesn't match reality. Deferred, not rejected outright.
- **Linking Process Sheet fields (Client, Drawing No, Part Name) to Material Request or Item.** The relationship between procurement and production hasn't been observed in practice yet; free-text avoids guessing at a link shape ahead of that.
- **External storage (e.g. S3) for the scanned process sheet copy.** Would reopen ADR 0001's "no second system of record" decision for no clear benefit over a native attachment.

**Consequences:**
- The template/run split is expected debt — once enough repeat-order Process Sheets exist to show the actual variation pattern, this ADR should be revisited to decide whether/how to split template from run.
- Whether Frappe's Quality Inspection `reference_type` accepts a custom doctype (Process Sheet) is an assumption, not yet verified against the ERPNext version in use — verify before building against it.
- Roles (Programmer/Operator/Inspector) have no defined permission boundaries yet; this is deliberate, not an oversight — expect to revisit once usage patterns are clearer.
- See `docs/erpnext-custom-fields.md` for the new doctype/field provisioning checklist.

**Refinements from the later API-shape review** (see `docs/api-shapes.md` for the concrete request/response shapes):
- Process Sheet Operation carries no field describing what an operation technically entails — that duplicated the attached drawing for no payoff, since the Programmer already produces it as a document. Rows only ever record who/what/when (machine, operator, qty, timing), never a spec.
- Process Sheet is created with header fields only (`operations` starts empty) — the full 12-row plan is never pre-populated from the Programmer's document; rows get added incrementally by whoever actually executes each operation.
- `rework`/`rejection` on an Operation are independently, manually recorded facts — confirmed never auto-set by a failed Stage Inspection's outcome.
- Repeat orders against the same drawing confirmed to create a fully new, independent Process Sheet each time (no link back) — reinforces the template/run split above as still-deferred, not resolved.
- The upstream question of how a job enters the system at all was resolved separately as ERPNext's native **Sales Order** (see CONTEXT.md's Sales Order section) — deliberately not yet linked to Process Sheet.
