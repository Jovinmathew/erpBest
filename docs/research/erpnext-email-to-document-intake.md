# ERPNext email-to-document intake — Email Account "Append To" — research

Scope: primary-source research (Frappe/ERPNext GitHub source + official docs.frappe.io pages) into whether native Frappe/ERPNext already solves "email-to-document intake" (auto-creating a document from an inbound email), to inform how the BFF would wire a custom "Client Request" doctype into it, per [ADR 0001](../adr/0001-erpnext-native-persistence.md)'s "reuse ERPNext's own native behavior" philosophy.

**Versions and commits cited.** Frappe keeps one long-lived branch per major version in both `frappe/frappe` and `frappe/erpnext`: `version-13`, `version-14`, `version-15`, and — as of this research (previous sibling research, written 2026-07-29, predates this) — a `version-16` branch now exists in **both** repos, so it is used here instead of `develop` (no caveat needed, unlike the sibling doc's `develop`-only situation). Branch heads used below (fetched 2026-07-30 via the GitHub API, e.g. `https://api.github.com/repos/frappe/frappe/branches/version-16`):

| Repo | Branch | Commit SHA |
|---|---|---|
| `frappe/frappe` | `version-13` | `5ec534b8b6f25df94da00f247bdb1583baa05995` |
| `frappe/frappe` | `version-14` | `be2f6245febabc75f48196c250938d733aa9054f` |
| `frappe/frappe` | `version-15` | `95444a13d13bfaefda943a8597e1de3cf1f2b218` |
| `frappe/frappe` | `version-16` | `06613fc60b44d5736007ae3107cdab029b2ae045` |
| `frappe/erpnext` | `version-13` | `37e00a66da7f38107ee31141c43154a4615ff568` |
| `frappe/erpnext` | `version-14` | `bd7e5b3e0589db07e45e49cbe1b250b62ad868d3` |
| `frappe/erpnext` | `version-15` | `7098602dccf012a88683da862828899e245e5525` |
| `frappe/erpnext` | `version-16` | `8378b6e203841c056925420cc44e6d631c915cf1` |

All "current"/primary-target permalinks below use the `frappe/frappe@06613fc6` and `frappe/erpnext@8378b6e2` (`version-16`) SHAs, matching this project's ERPNext v16.29.0 target. Version-history permalinks (v13/v14/v15) are used only in the [Version differences](#version-differences) section.

---

## Summary — does native ERPNext already solve this?

**Yes, close to entirely — Frappe's "Email Account → Append To" is exactly the intake mechanism described, it is pure configuration (no code) to wire in a new custom doctype, and it already handles attachments, reply-threading, and unknown senders; the only real gaps are around dedup fidelity for doctypes with no natural subject line and a documented (not enforced-by-default) attachment size limit.**

- Frappe has a native, generic `Email Account.append_to` field: pick any DocType flagged `email_append_to`, and every inbound email addressed to that account auto-creates a new document of that doctype (or attaches to an existing one) as a side effect of the standard `EmailAccount.receive()` → `InboundMail.process()` pipeline — this is framework-level (`frappe/frappe`), not ERPNext-specific, though ERPNext ships three of its own doctypes (Issue, Lead, Opportunity) pre-flagged as valid targets. See [Q1](#1-the-append-to-mechanism).
- The email body/attachments are preserved as a real `Communication` (with `File` attachments re-parented onto the new document), not just metadata — so nothing about the original message is lost. See [Q1](#1-the-append-to-mechanism).
- There's no bespoke "intake queue" doctype — the handoff-to-a-human step is just the same generic `ToDo`/"Assign To" mechanism every Frappe document has, plus, in ERPNext specifically, Lead/Opportunity/Issue already being end-user-facing doctypes that show up in list views assigned to a team. See [Q2](#2-intake-queue--handoff-pattern).
- Wiring in a **new custom doctype is pure configuration** — tick "Allow document creation via Email" (`email_append_to`) on the DocType, name a `Sender` and `Subject` field, then pick it in the Email Account's `Append To` dropdown. No server-side hook or override is required for the base flow. See [Q3](#3-wiring-a-custom-client-request-doctype-into-append-to).
- Threading identifies replies via the `In-Reply-To` header first (matched against `Communication.message_id` or `Email Queue`), falling back to subject+sender matching only when that fails — it does **not** use a `References` header or a bracketed `[thread-id]` scheme (a leftover, unused `get_thread_id()` helper exists in code but is never called). Attachments are capped by a real but *disabled-by-default* per-account/domain `Attachment Limit`, with a 25 MB system-wide fallback for the underlying `File` doctype; a sender does **not** need to match an existing Contact — Frappe auto-creates a `Contact` from an unknown sender if `create_contact` (default: on) is enabled, independently of document creation. See [Q4](#4-known-limitations--gotchas).

---

## 1. The Append To mechanism

**Yes — this is exactly the "auto-create a document from an inbound email" feature, and it lives in the framework (`frappe/frappe`), not `erpnext`.**

### What triggers it

`Email Account` has an `append_to` Link field (to `DocType`):

```
"description": "Append as communication against this DocType (must have fields: \"Sender\" and \"Subject\"). These fields can be defined in the email settings section of the appended doctype.",
"fieldname": "append_to",
"fieldtype": "Link",
"options": "DocType"
```
[`email_account.json#L236-L245`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/email_account.json#L236-L245)

The scheduler calls `EmailAccount.receive()`, which pulls messages via `get_inbound_mails()` and, for each one, builds an `InboundMail` (imported from `frappe.email.receive`) and calls `.process()`:

```python
def receive(self):
	"""Called by scheduler to receive emails from this EMail account using POP3/IMAP."""
	exceptions = []
	inbound_mails = self.get_inbound_mails()
	for mail in inbound_mails:
		communication = mail.process()
		...
```
[`email_account.py#L687-L720`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/email_account.py#L687-L720) — note `frappe/email/receive.py` still exists at this path in v16 (the task brief's caveat that it might have moved does not apply); `InboundMail` and its processing logic live there, not in `email_account.py` itself.

`InboundMail.process()` decides "reuse an existing Communication" vs. "build a new one," and inside `_build_communication_doc()`, if no existing reference document is found and `append_to` is set, it creates a brand-new document of that doctype:

```python
append_to = self.append_to if self.email_account.use_imap else self.email_account.append_to

if self.reference_document():
	data["reference_doctype"] = self.reference_document().doctype
	data["reference_name"] = self.reference_document().name
elif append_to and append_to != "Communication":
	reference_name = self._create_reference_document(append_to)
	if reference_name:
		data["reference_doctype"] = append_to
		data["reference_name"] = reference_name
```
[`receive.py#L714-L731`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L714-L731)

`_create_reference_document()` is the actual document-creation call:

```python
def _create_reference_document(self, doctype):
	"""Create reference document if it does not exist in the system."""
	parent = frappe.new_doc(doctype)
	email_fields = self.get_email_fields(doctype)

	if email_fields.subject_field:
		parent.set(email_fields.subject_field, frappe.as_unicode(self.subject)[:140])
	if email_fields.sender_field:
		parent.set(email_fields.sender_field, frappe.as_unicode(self.from_email))
	if email_fields.sender_name_field:
		parent.set(email_fields.sender_name_field, frappe.as_unicode(self.from_real_name))
	if email_fields.recipient_account_field:
		parent.set(email_fields.recipient_account_field, self.email_account.name)

	parent.flags.ignore_mandatory = True
	try:
		parent.insert(ignore_permissions=True)
		return parent.name
	except frappe.DuplicateEntryError:
		return frappe.db.get_value(doctype, {email_fields.sender_field: self.from_email})
```
[`receive.py#L915-L939`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L915-L939) — note `ignore_mandatory=True` and `insert(ignore_permissions=True)`: creation is not blocked by the target doctype's own mandatory-field rules or by any user's permission to create that doctype. This is confirmed directly by Frappe's own test suite, which uses `ToDo` (a doctype with **no** `subject_field`/`sender_field` declared) as an `append_to` target and asserts a new `ToDo` is created from a raw inbound email: [`test_email_account.py#L418-L427`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/test_email_account.py#L418-L427).

### What fields it populates

`subject_field` / `sender_field` (plus `sender_name_field` and `recipient_account_field`) are declared **on the target DocType itself** (via `DocType`'s own form, or Customize Form's Property Setter mechanism), not on Email Account:

```
{"fieldname": "subject_field", "fieldtype": "Data", "label": "Subject Field"},
{"fieldname": "sender_field", "fieldtype": "Data", "label": "Sender Email Field", "mandatory_depends_on": "email_append_to"},
{"fieldname": "email_append_to", "fieldtype": "Check", "label": "Allow document creation via Email"},
{"fieldname": "sender_name_field", "fieldtype": "Data", "label": "Sender Name Field"},
{"fieldname": "recipient_account_field", "fieldtype": "Data", "label": "Recipient Account Field"}
```
[`doctype.json#L513-L720`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/core/doctype/doctype/doctype.json#L513-L720) — `get_email_fields()` reads these straight off `frappe.get_meta(doctype)`:
```python
@staticmethod
def get_email_fields(doctype):
	"""Return Email related fields of a doctype."""
	fields = frappe._dict()
	email_fields = ["subject_field", "sender_field", "sender_name_field", "recipient_account_field"]
	meta = frappe.get_meta(doctype)
	for field in email_fields:
		if hasattr(meta, field):
			fields[field] = getattr(meta, field)
	return fields
```
[`receive.py#L968-L979`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L968-L979)

### The original email + attachments are preserved

Every processed mail becomes a real `Communication` document (`reference_doctype`/`reference_name` pointed at the new/matched document) — [`communication.json#L39-L246`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/core/doctype/communication/communication.json#L39-L246) — and attachments are written as real `File` records attached to that Communication:
```python
def save_attachments_in_doc(self, doc):
	"""Save email attachments in given document."""
	for attachment in self.attachments:
		_file = frappe.get_doc({
			"doctype": "File",
			"file_name": unquote(attachment["fname"]),
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": attachment["fcontent"],
		})
		_file.save()
```
[`receive.py#L632-L663`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L632-L663), called from `_build_communication_doc()` right after the Communication itself is inserted: [`receive.py#L739-L750`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L739-L750). So nothing is thrown away: the new document is linked to the Communication (via `reference_doctype`/`reference_name`), and the Communication itself carries the original attachments and content (HTML sanitized via `sanitize_html`).

### Can it target an arbitrary custom doctype?

**Yes, gated only by one Check field, `email_append_to`, on the DocType.** The whitelisted Link-field query function backing the `append_to` dropdown is:

```python
@frappe.whitelist()
def get_append_to(doctype=None, txt=None, searchfield=None, start=None, page_len=None, filters=None):
	txt = txt if txt else ""
	filters = {"istable": 0, "issingle": 0, "email_append_to": 1}
	# Set Email Append To DocTypes via DocType
	email_append_to_list = [
		dt.name for dt in frappe.get_all("DocType", filters=filters, fields=["name", "email_append_to"])
	]
	# Set Email Append To DocTypes set via Customize Form
	email_append_to_list.extend(
		dt.doc_type
		for dt in frappe.get_list("Property Setter", filters={"property": "email_append_to", "value": 1}, fields=["doc_type"])
	)
	return [[d] for d in set(email_append_to_list) if txt in d]
```
[`email_account.py#L900-L917`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/email_account.py#L900-L917) — for IMAP accounts, `EmailAccount.validate()` re-checks each folder's `append_to` against this same allow-list before letting the Email Account be saved:
```python
valid_doctypes = {d[0] for d in get_append_to()}
for folder in self.imap_folder:
	if folder.append_to and folder.append_to not in valid_doctypes:
		frappe.throw(_("Append To can be one of {0}").format(comma_or(valid_doctypes)))
```
[`email_account.py#L165-L172`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/email_account.py#L165-L172). Notably the second clause in `get_append_to()` means the flag is settable **without modifying the doctype's own JSON** — a Property Setter (i.e., Frappe's "Customize Form" UI, no code) is enough for any doctype, standard or custom.

ERPNext ships three of its own doctypes pre-flagged this way out of the box: **Issue** (`sender_field: "raised_by"`, `subject_field: "subject"`), **Lead** (`sender_field: "email_id"`, `subject_field: "title"`), and **Opportunity** (`sender_field: "contact_email"`, `subject_field: "title"`) — confirmed directly in their doctype JSON: [`issue.json#L9`](https://github.com/frappe/erpnext/blob/8378b6e203841c056925420cc44e6d631c915cf1/erpnext/support/doctype/issue/issue.json#L9), [`lead.json#L10`](https://github.com/frappe/erpnext/blob/8378b6e203841c056925420cc44e6d631c915cf1/erpnext/crm/doctype/lead/lead.json#L10), [`opportunity.json#L12`](https://github.com/frappe/erpnext/blob/8378b6e203841c056925420cc44e6d631c915cf1/erpnext/crm/doctype/opportunity/opportunity.json#L12). No fixture/patch in `erpnext/hooks.py` or `erpnext/setup/install.py` actually creates or pre-configures an Email Account pointed at any of them, though — grepping `erpnext/hooks.py` for `Email Account`/`append_to` returns nothing; an admin still has to create the Email Account and pick the doctype manually. The official manual corroborates the Issue case end-to-end: *"you can send support queries to ERPNext at support@erpnext.com and it will automatically create an Issue in our system... Issues are automatically created if you use the append to feature in Email Account"* — [Issue — docs.frappe.io/erpnext/issue](https://docs.frappe.io/erpnext/issue), and the general mechanism (not Issue-specific) is documented as: *"This feature creates documents when an email is sent to a particular pre-configured email. For example, you can link support@example.com to the Issue DocType... Similarly, if you link jobs@example.com... a Job Applicant document is automatically created."* — [Email Account — docs.frappe.io/erpnext/email-account](https://docs.frappe.io/erpnext/email-account) (§"Automatic Document Creation Through Linked Emails").

---

## 2. Intake queue / handoff pattern

**No dedicated "intake queue" doctype exists — the handoff is the same generic `ToDo`/"Assign To" mechanism every Frappe document already has, not something purpose-built for email intake.**

`ToDo` is a plain reference-doctype/reference-name record created by the whitelisted `frappe.desk.form.assign_to.add()`:
```python
d = frappe.get_doc({
	"doctype": "ToDo",
	"allocated_to": assign_to,
	"reference_type": args["doctype"],
	"reference_name": str(args["name"]),
	"description": args.get("description"),
	"priority": args.get("priority", "Medium"),
	"status": "Open",
	...
}).insert(ignore_permissions=True)
...
notify_assignment(d.assigned_by, d.allocated_to, d.reference_type, d.reference_name, action="ASSIGN", ...)
```
[`assign_to.py#L57-L133`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/desk/form/assign_to.py#L57-L133) — this is the standard "Assign To" button available on every document's form (including a freshly auto-created Lead/Opportunity/Issue/custom doctype), sending a notification to the assignee. Nothing in the `InboundMail`/`EmailAccount` code path calls `assign_to.add()` automatically — creating the reference document and assigning it to someone are two independent, manual steps unless a site adds its own automation (e.g. a Notification/Assignment Rule) on top.

**ERPNext's own CRM module (Lead/Opportunity) is not thin and has not been spun out of `frappe/erpnext`** — as of the `version-16` branch it still lives at `erpnext/crm/doctype/{lead,opportunity}/` with full business logic (`erpnext/crm/doctype/lead/`, `erpnext/crm/doctype/opportunity/` present in the v16 tree, confirmed via the GitHub contents API: `https://api.github.com/repos/frappe/erpnext/contents/erpnext/crm/doctype?ref=8378b6e2038...`). Frappe separately publishes a standalone product, **Frappe CRM** (`frappe/crm` — *"Fully featured, open source CRM"*, per its GitHub repo description), which is a different, independently-installed app built on the framework rather than a replacement for ERPNext's own CRM module; it was out of scope to investigate deeply here since ERPNext's own Lead/Opportunity turned out not to be thin, per the task brief's own conditional. Neither Lead nor Opportunity has any special "someone received this, someone else converts it" workflow baked in beyond being an ordinary assignable, list-viewable doctype — the "handoff" is exactly the ToDo/Assign-To pattern above, applied to whatever document `append_to` created.

---

## 3. Wiring a custom "Client Request" doctype into Append To

**Pure configuration — no server-side hook or code override is required for the base auto-create-on-email flow.** What's actually needed, all discoverable from the same DocType-level fields used by ERPNext's own Issue/Lead/Opportunity ([Q1](#1-the-append-to-mechanism)):

1. **On the custom doctype itself** (via the DocType form directly, since it's already a custom doctype you own — no need to go through Customize Form/Property Setter, though that path works too for standard doctypes):
   - Tick `email_append_to` ("Allow document creation via Email").
   - Set `sender_field` to the fieldname that should hold the sender's email (`mandatory_depends_on: email_append_to` — i.e. Frappe enforces that you name one) — [`doctype.json#L519-L524`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/core/doctype/doctype/doctype.json#L519-L524).
   - Optionally set `subject_field` (for subject-line reply-matching, [Q4](#4-known-limitations--gotchas)) and `sender_name_field`/`recipient_account_field`.
2. **On the Email Account**: set `append_to` to the new doctype's name (only possible once step 1's `email_append_to` flag is ticked — otherwise `get_append_to()` excludes it from the Link dropdown entirely, see [Q1](#1-the-append-to-mechanism)) and `enable_incoming=1` with valid IMAP/POP3 credentials.
3. **Nothing else** — no `hooks.py` doc_event, no custom whitelisted method, no override of `InboundMail`. `_create_reference_document()` calls `frappe.new_doc(doctype)` generically and inserts with `ignore_mandatory=True`/`ignore_permissions=True` ([Q1](#1-the-append-to-mechanism)), so a custom doctype with other mandatory fields (e.g. a required `status` or `priority` field with a default) will still be created successfully — those fields just come through as empty/default unless the doctype gives them a `default` value, since only `subject_field`/`sender_field`/`sender_name_field`/`recipient_account_field` get explicitly populated from the email.

**Email body and attachments arrive automatically**, exactly as for Issue/Lead/Opportunity: the inbound `Communication` is linked to the new Client Request document via `reference_doctype`/`reference_name`, and any email attachments are saved as `File` records attached to that Communication (not directly to the Client Request document itself) — see the `save_attachments_in_doc()` citation in [Q1](#1-the-append-to-mechanism). A Client Request's form would show the email in its Activity/Emails timeline (standard Frappe document timeline behavior for any doctype, driven by `reference_doctype`/`reference_name` matching), the same way RFQ's own emails show up per the sibling RFQ research doc.

**If the doctype has no natural single-value "subject line"** (a plausible case for a bespoke Client Request record whose "subject" might be, e.g., a computed summary), `subject_field` can be left unset — the tradeoff is purely on the read side (subject-based reply matching becomes unavailable, see [Q4](#4-known-limitations--gotchas)), not on the write/creation side, which Frappe's own `ToDo`-as-`append_to`-target test proves works with **no** `subject_field`/`sender_field` declared at all ([`test_email_account.py#L418-L427`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/test_email_account.py#L418-L427)) — though `sender_field`'s `mandatory_depends_on` means the DocType form itself will insist on a sender field name once `email_append_to` is ticked.

---

## 4. Known limitations / gotchas

### Threading — how a reply is matched to an existing document vs. creating a new one

**Primary signal: the `In-Reply-To` header, matched against an existing `Communication.message_id` or `Email Queue` record — not a `References` header, and not a bracketed thread-id scheme (that code path exists but is dead).** `parent_communication()` is tried first:

```python
def parent_communication(self):
	"""Find a related communication so that we can prepare a mail thread.
	The way it happens is by using in-reply-to header...
	1. If mail is a reply to already sent mail, then we can get parent communicaion from
	        Email Queue record or message_id on communication.
	2. Sometimes we send communication name in message-ID directly, use that to get parent communication.
	3. Sender sent a reply but reply is on top of what (s)he sent before,
	        then parent record exists directly in communication.
	"""
	if not self.is_reply():
		return ""
	communication = Communication.find_one_by_filters(message_id=self.in_reply_to, order_by="creation DESC")
	if not communication:
		if self.parent_email_queue() and self.parent_email_queue().communication:
			communication = Communication.find(self.parent_email_queue().communication, ignore_error=True)
		else:
			reference = self.in_reply_to
			if "@" in self.in_reply_to:
				reference, _ = self.in_reply_to.split("@", 1)
			communication = Communication.find(reference, ignore_error=True)
	...
```
[`receive.py#L802-L835`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L802-L835), where `is_reply()` is simply `bool(self.in_reply_to)` and `in_reply_to` is parsed straight from the `In-Reply-To` header: `in_reply_to = self.mail.get("In-Reply-To") or ""` — [`receive.py#L433-L436`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L433-L436). Searching all of `receive.py`, `communication.py`, and `email_account.py` for `References` (the email header) returns no matches — Frappe does not consult the `References` header at all, only `In-Reply-To`.

If `In-Reply-To`/parent-communication resolution fails (or the mail isn't a reply at all — e.g. a brand-new inbound message, or a reply whose mail client dropped the header), `reference_document()` falls back to **subject + sender matching** against the `append_to` doctype:
```python
def match_record_by_subject_and_sender(self, doctype):
	"""...
	1. Sometimes record name is part of subject. We can get document by parsing name from subject
	2. Find by matching sender and subject
	3. Find by matching subject alone (Special case: system user via Outlook, sender match bypassed)
	NOTE: We consider not to match by subject if match record is very old.
	"""
	name = self.get_reference_name_from_subject()
	email_fields = self.get_email_fields(doctype)
	record = self.get_doc(doctype, name, ignore_error=True) if name else None
	if not record:
		if not email_fields.subject_field:
			return None
		subject = self.clean_subject(self.subject)
		filters = {email_fields.subject_field: ("like", f"%{subject}%"), "creation": (">", self.get_relative_dt(days=-60))}
		if email_fields.sender_field and not (len(subject) > 10 and is_system_user(self.from_email)):
			filters[email_fields.sender_field] = self.from_email
		name = frappe.db.get_value(self.email_account.append_to, filters=filters)
		record = self.get_doc(doctype, name, ignore_error=True) if name else None
	return record
```
[`receive.py#L875-L913`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L875-L913) — note the explicit 60-day window (`creation > now - 60 days`): an old thread revived by a reply after 60 days will **not** be matched and instead spawns a brand-new document. A leftover `get_thread_id()` method exists (`re.compile(r"(?<=\[)[\w/-]+")`, meant to extract a `[thread-id]`-style token from the subject — [`receive.py#L665-L668`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L665-L668)) but grepping the entire `frappe/email/` module tree (`receive.py`, `email_body.py`, `smtp.py`, `queue.py`, `inbox.py`, `utils.py`) for callers of `get_thread_id()` turns up none — it is dead code in the version checked, not an active threading mechanism. **Practical implication for a Client Request doctype without a `subject_field`:** replies would never be subject-matched, so multi-reply threading would rely entirely on `In-Reply-To` continuing to survive round-trips (usually true, but not guaranteed with all mail clients/relays) — if that's a concern, declaring a `subject_field` is cheap insurance even if the field isn't otherwise user-facing.

### Attachment size limits

**Two independent, separately-configured limits, both effectively opt-in/soft:**

1. **Per inbound-email attachment, via Email Account (or its Email Domain default), disabled by default:**
   ```python
   def get_attachment(self, part) -> None:
   	fcontent = part.get_payload(decode=True)
   	...
   	attachment_limit = cint(email_account.attachment_limit) if email_account else 0
   	if attachment_limit and len(fcontent) > attachment_limit * 1024 * 1024:
   		return  # skip attachments that are larger than the specified limit
   ```
   [`receive.py#L594-L604`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L594-L604) — silently dropped (no error surfaced), and the field description confirms intent: `"description": "Ignore attachments over this size"`, `"label": "Attachment Limit (MB)"` — [`email_account.json#L226-L233`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/email_account.json#L226-L233), `fetch_from: "domain.attachment_limit"` meaning it defaults from the linked `Email Domain` record if unset on the account itself. Neither has a non-empty default in the shipped JSON — i.e., **no size limit is enforced here unless an admin sets one.**
2. **System-wide `File` size cap, applied when the attachment is actually saved as a `File` record:**
   ```python
   def get_max_file_size() -> int:
   	return (
   		cint(frappe.get_system_settings("max_file_size")) * 1024 * 1024
   		or cint(frappe.conf.get("max_file_size"))
   		or 25 * 1024 * 1024
   	)
   ```
   [`frappe/core/api/file.py#L85-L90`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/core/api/file.py#L85-L90) — a **25 MB default** if neither `System Settings.max_file_size` nor site-config `max_file_size` is set, raising `MaxFileSizeReachedError`. Critically, when this happens during inbound-mail attachment saving, it is **caught and swallowed**, not propagated as a processing failure:
   ```python
   def save_attachments_in_doc(self, doc):
   	for attachment in self.attachments:
   		try:
   			_file = frappe.get_doc({...}); _file.save()
   			saved_attachments.append(_file)
   		except MaxFileSizeReachedError:
   			# WARNING: bypass max file size exception
   			pass
   		except frappe.FileAlreadyAttachedException:
   			pass
   		except frappe.DuplicateEntryError:
   			pass
   	return saved_attachments
   ```
   [`receive.py#L632-L663`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/receive.py#L632-L663) — **an oversized attachment is silently dropped and the email/document is still created without it**; nothing in the flow notifies anyone that an attachment was lost. This is a genuine gotcha worth flagging to whoever operates the mailbox.

### Does the sender need to match an existing Contact/Customer/Lead first?

**No — document creation via `append_to` proceeds regardless of whether the sender is a known Contact.** Separately, and optionally, Frappe **auto-creates a `Contact`** for an unrecognized sender and links it to the resulting `Communication`'s timeline, gated by an `Email Account.create_contact` Check field (**default: on**, i.e. `"default": "1"`):
```python
def set_timeline_links(self):
	...
	create_contact_enabled = self.email_account and frappe.db.get_value("Email Account", self.email_account, "create_contact")
	contacts = get_contacts([self.sender, self.recipients, self.cc, self.bcc], auto_create_contact=create_contact_enabled)
	for contact_name in contacts:
		self.add_link("Contact", contact_name)
```
[`communication.py#L418-L438`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/core/doctype/communication/communication.py#L418-L438), and:
```python
def get_contacts(email_strings: list[str], auto_create_contact=False) -> list[str]:
	...
	if not contact_name and email and auto_create_contact:
		first_name = frappe.unscrub(email.split("@")[0])
		contact = frappe.get_doc({"doctype": "Contact", "first_name": contact_name, "name": contact_name})
		contact.add_email(email_id=email, is_primary=True)
		contact.insert(ignore_permissions=True)
```
[`communication.py#L531-L557`](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/core/doctype/communication/communication.py#L531-L557) — `"default": "1"` confirmed at [`email_account.json` `create_contact` field](https://github.com/frappe/frappe/blob/06613fc60b44d5736007ae3107cdab029b2ae045/frappe/email/doctype/email_account/email_account.json#L544-L552) (label: "Create Contacts from Incoming Emails"). This Contact-linking is entirely independent of the `append_to` reference-document creation path in [Q1](#1-the-append-to-mechanism) — turning `create_contact` off does not block or change document auto-creation, it only means an unknown sender's Communication won't get a Contact timeline link.

---

## Version differences

Two real, source-confirmed differences were found between v13 and v14+ (v14, v15, and v16 checked were consistent with each other in everything below); everything else — the `get_append_to()` allow-list query, the `email_append_to`/`subject_field`/`sender_field` DocType-level fields, the `Attachment Limit`/`create_contact` Email Account fields, and the `ToDo`/Assign-To handoff mechanism — showed no meaningful differences across the versions checked.

1. **The `append_to` processing logic moved from `EmailAccount` methods into a dedicated `InboundMail` class between v13 and v14.** In v13, `frappe/email/receive.py` contains only the lower-level `EmailServer`/`Email` classes (IMAP/POP3 connection handling, MIME parsing) — there is no `InboundMail.process()`/`reference_document()`/`match_record_by_subject_and_sender()` at all. Instead, the equivalent logic — matching a reply via `In-Reply-To`, then subject+sender, then creating a new parent document — lives directly on `EmailAccount` itself: `set_thread()`, `find_parent_from_in_reply_to()`, `find_parent_based_on_subject_and_sender()`, `create_new_parent()`, `set_sender_field_and_subject_field()` — [`v13/email_account.py#L544-L675`](https://github.com/frappe/frappe/blob/5ec534b8b6f25df94da00f247bdb1583baa05995/frappe/email/doctype/email_account/email_account.py). From v14 onward, this logic is refactored into `frappe.email.receive.InboundMail` as `parent_communication()`/`reference_document()`/`match_record_by_subject_and_sender()`/`_create_reference_document()` (confirmed present with near-identical bodies in [v14](https://github.com/frappe/frappe/blob/be2f6245febabc75f48196c250938d733aa9054f/frappe/email/receive.py#L723-L840), [v15](https://github.com/frappe/frappe/blob/95444a13d13bfaefda943a8597e1de3cf1f2b218/frappe/email/receive.py#L790-L913), and v16 as quoted throughout this document) — a structural refactor, not a behavior change: the same three-tier fallback (In-Reply-To → subject+sender → new document) exists in both eras.
2. **The `append_to` field's description ("must have fields: Sender and Subject...") was added in v14, absent in v13.** v13's `append_to` field carries no `description` string at all ([`v13/email_account.json#L217-L224`](https://github.com/frappe/frappe/blob/5ec534b8b6f25df94da00f247bdb1583baa05995/frappe/email/doctype/email_account/email_account.json#L217-L224)); the explanatory description first appears verbatim in v14's JSON and is unchanged through v16 ([`v14/email_account.json#L216-L217`](https://github.com/frappe/frappe/blob/be2f6245febabc75f48196c250938d733aa9054f/frappe/email/doctype/email_account/email_account.json#L216-L217)). Purely a UX/documentation-string change, not a functional one — the `get_append_to()` allow-list query and the DocType-level `email_append_to`/`sender_field`/`subject_field` fields are present and functionally identical in v13, v14, v15, and v16.

The `attachment_limit` (Email Account/Email Domain, `"Ignore attachments over this size"`) and `create_contact` (`"default": "1"`) fields were both already present in v13's `email_account.json`, so neither is a v14+ addition.
