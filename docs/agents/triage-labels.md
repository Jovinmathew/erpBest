# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| --------------------------- | --------------------- | ----------------------------------------- |
| `needs-triage`              | `needs-triage`        | Maintainer needs to evaluate this card    |
| `needs-info`                | `needs-info`          | Waiting on reporter for more information  |
| `ready-for-agent`           | `ready-for-agent`     | Fully specified, ready for an AFK agent   |
| `ready-for-human`           | `ready-for-human`     | Requires human implementation             |
| `wontfix`                   | `wontfix`              | Will not be actioned                      |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

These exist as **Trello board labels** — per-board objects rather than free-form strings, so each must be created on the board once before it can be applied to a card. See `docs/agents/issue-tracker.md` for the create/apply calls.
