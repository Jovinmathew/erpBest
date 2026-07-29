---
status: accepted
---

# Actor identity via static token table, not Frappe User

Callers are identified by a static token→`{user_id, roles}` table held in BFF settings, not by ERPNext/Frappe User records. Actor fields (`raised_by`, `validated_by`, rejection `by`, `proposed_by`/`final_by`) are stored as plain strings, not Links to User. This was chosen over deriving identity from Frappe Users because nobody besides the person provisioning ERPNext touches its UI during this pilot (API-first, Postman/curl only) — there's no payoff from ERPNext's native "created by" rendering, and linking to User would mean provisioning and keeping two identity stores in sync for a system only one person will ever look at directly.

**Consequences:** if the pilot later needs real auth (token issuance, multi-tenant identity, or a frontend where people log in), actor fields will need a migration path from plain strings to real identities. This is accepted as a deliberate pilot-scope simplification, not an oversight.
