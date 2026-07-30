# Issue tracker: Trello

Tickets for this repo live as cards on a Trello board. There is no `gh`-style CLI — use Trello's REST API via `curl`.

**Specs are not tickets.** A spec (PRD) is a long document and lives in the repo under `docs/specs/`, versioned alongside `CONTEXT.md` and `docs/adr/`. A card is one independently-completable unit of work that *links* to the relevant spec sections — it never restates them. Trello's card description limit (16,384 chars) is a feature here, not an obstacle: if a card body wants to be longer than that, it's a spec, not a card. Anything that turns out to be a durable *decision* graduates out of a card comment into a new ADR.

## This repo's board

**erpBest — Procurement & Stock Pilot**: <https://trello.com/b/Uc66L0xl/erpbest-procurement-stock-pilot> (board id `Uc66L0xl`, private).

Lists: `Backlog → Ready → In Progress → Review → Done`. Labels: the five triage labels below, plus `blocked`.

## Credentials

An API key and token are required on every call, as query params (`key=`/`token=`). Generate them at <https://trello.com/power-ups/admin> — create a Power-Up, then generate an API key, then a token.

Never commit these or echo them into a transcript. Read them from an untracked file and pass them through the shell:

```bash
source <(sed 's/^/export TRELLO_/' path/to/trello-creds)   # key=... / token=... → TRELLO_key/TRELLO_token
AUTH="key=$TRELLO_key&token=$TRELLO_token"
```

## Board and list IDs

A board URL looks like `https://trello.com/b/<shortLink>/<slug>`. The `<shortLink>` works directly as a board id in the API.

```bash
# Lists on the board (get the id of the list new cards go into)
curl -s "https://api.trello.com/1/boards/$BOARD/lists?fields=name&$AUTH"
# Labels defined on the board (ids needed to label a card)
curl -s "https://api.trello.com/1/boards/$BOARD/labels?fields=name,color&$AUTH"
```

## Conventions

- **Create a card**: `POST /1/cards` with `idList`, `name`, `desc`. Use `--data-urlencode` so Markdown bodies survive intact:
  ```bash
  curl -s -X POST "https://api.trello.com/1/cards?$AUTH" \
    --data-urlencode "idList=$LIST" \
    --data-urlencode "name=Card title" \
    --data-urlencode "desc@path/to/body.md"
  ```
  Descriptions render Markdown. The response includes the card's `id`, `shortLink`, and `shortUrl`.
- **Read a card**: `GET /1/cards/<id>` (`<id>` may be the full id or the `shortLink` from its URL). Add `?fields=name,desc,idList,labels` to trim, and fetch comments separately (below).
- **List cards**: `GET /1/boards/<board>/cards?fields=name,idList,labels` for the whole board, or `GET /1/lists/<list>/cards` for one list. Filter with `jq`.
- **Comment on a card**: `POST /1/cards/<id>/actions/comments` with `text`.
- **Read comments**: `GET /1/cards/<id>/actions?filter=commentCard`, then `jq '.[].data.text'`.
- **Apply / remove a label**: `POST /1/cards/<id>/idLabels` with `value=<labelId>` / `DELETE /1/cards/<id>/idLabels/<labelId>`. Label ids come from the board's label list — Trello labels are per-board objects, not free-form strings, so a label must exist on the board before it can be applied.
- **Move a card** (the primary way progress is recorded): `PUT /1/cards/<id>` with `idList=<listId>`.
- **Close (archive)**: `PUT /1/cards/<id>` with `closed=true`. Trello archives rather than deletes; leave a comment first if the reason matters.
- **Attach a file**: `POST /1/cards/<id>/attachments` with `file=@path`. Prefer linking to a repo path over attaching — attachments aren't diffable and go stale silently.

## Lists as workflow state

`Backlog → Ready → In Progress → Review → Done`. A card's list *is* its status; there is no separate status field. Card position within a list carries priority (topmost first) — `PUT /1/cards/<id>` with `pos=top`/`bottom`/a number.

## Triage labels

The canonical triage vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) exists as board labels — see `docs/agents/triage-labels.md`. Because Trello labels are per-board objects, each must be created on the board once before use:

```bash
curl -s -X POST "https://api.trello.com/1/labels?$AUTH" \
  --data-urlencode "name=ready-for-agent" --data-urlencode "color=green" --data-urlencode "idBoard=$BOARD"
```

## Pull requests as a triage surface

**PRs as a request surface: no.** _(`/triage` reads this flag.)_ Trello is not connected to the repo's PRs; inbound code contributions are not part of this flow.

## When a skill says "publish to the issue tracker"

Create a card in **Backlog** and apply the appropriate triage label. If the content is spec-length, commit it to `docs/specs/` first and have the card point at it.

## When a skill says "fetch the relevant ticket"

`GET /1/cards/<id>` plus its `commentCard` actions.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single card; **tickets** are separate cards on the same board.

- **Map**: one card labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body in its description. Update it with `PUT /1/cards/<id>` and `desc`.
- **Child ticket**: its own card, labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`), with `Part of: <map card shortUrl>` as the first line of its description. Add it to a checklist on the map card so the map shows the frontier at a glance: `POST /1/cards/<map>/checklists` once, then `POST /1/checklists/<id>/checkItems` with `name=<child shortUrl>`.
- **Blocking**: Trello has no native issue dependencies on standard plans. Use a `Blocked by: <card shortUrl>, <card shortUrl>` line at the top of the child's description, and apply a `blocked` board label so it's visible without opening the card. A ticket is unblocked when every card named there is archived or in **Done**.
- **Frontier query**: cards in **Ready** with no assigned member, dropping any whose `Blocked by:` line names a card not yet in Done; topmost position wins.
- **Claim**: `POST /1/cards/<id>/idMembers` with `value=<memberId>` (your own id via `GET /1/members/me?fields=id`), and move the card to **In Progress**.
- **Resolve**: comment the answer on the card, move it to **Done**, then append a context pointer (link + one-line summary) to the map card's Decisions-so-far.
