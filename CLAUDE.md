## Agent skills

### Issue tracker

Tickets live as cards on a Trello board, via Trello's REST API (`curl`) — not GitHub Issues. See `docs/agents/issue-tracker.md`.

Specs (PRDs) are documents, not tickets: they live in `docs/specs/`, and cards link to them rather than restating them.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` — as Trello board labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.
