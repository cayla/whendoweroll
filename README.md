# D&D Scheduler

A lightweight Python web app for scheduling tabletop sessions. No accounts —
each campaign hands out three kinds of unguessable URL: an admin link, a
public read-only link, and one private link per player.

## What it does

- DM creates a campaign with a name, timezone, and the player roster.
- DM defines time slots: any number of recurring weekly windows
  (Friday 18:00–21:00, Sunday 11:00–14:00, …) plus one-off sessions.
- Each player gets a private URL. Opening it shows every slot with
  Yes / No buttons. Their answers stick "indefinitely" — saying yes to
  Friday means yes to *every* future Friday until they change it.
- For **recurring** slots only, players can add **one-off conflicts** (for
  example "I'm free every Friday except May 29th"). Those exceptions feed
  into consensus, the public "yes" counts, and their personal calendar.
  The per-date table only lists slots you currently have as **Yes**; set the
  whole row to **No** or clear it and those dates (and saved opt-outs) go
  away until you opt in again.
- **JSON export** (admin URL): full snapshot of the campaign — roster, slots,
  availability, and opt-outs. Secrets are never included.
- **iCalendar**: each player has `…/p/{token}/calendar.ics` with their own
  free windows; the admin page links to `calendar-consensus.ics` (everyone
  available, respecting opt-outs).
- The campaign home page shows two answers prominently:
  - **Next session: everyone** — earliest window where every player said yes.
  - **Next session: all but one** — earliest window with at most one holdout
    (with the holdout's name, so the DM can nudge them).

A response of "no answer yet" is treated as **not available** for those
calculations, so the DM never over-promises.

### Display timezone (player + public pages)

Times default to the **campaign** timezone (how recurring rules are defined).
Visitors can switch to their own IANA zone: a `dnd_viewer_tz` cookie (path `/`)
stores the choice. On first load, a small script reads
`Intl.DateTimeFormat().resolvedOptions().timeZone`, sets the cookie, and
reloads once so times match the browser without opening the dropdown.

## Run it

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --group dev
uv run uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000> and create a campaign.

## Docker (ECS / Fargate-friendly)

The image runs **uvicorn** as a non-root user and stores SQLite at
`/data/dnd_scheduler.sqlite3` by default. Dependencies are installed with
**uv** from [`pyproject.toml`](pyproject.toml) and a frozen
[`uv.lock`](uv.lock) (production images use `uv sync --frozen` without dev
groups). Mount an **EFS**
(or EBS) volume on
`/data` so the file survives task restarts. Use **one task** (or one worker)
per SQLite file — SQLite is not a multi-writer cluster store. For horizontal
scale, point `DND_SCHEDULER_DB_URL` at Postgres instead.

```bash
docker compose up --build
```

Build only:

```bash
docker build -t dnd-scheduler .
docker run -p 8000:8000 -v dnd-data:/data dnd-scheduler
```

## Fly.io

See [deploy/fly.md](deploy/fly.md) for `fly.toml`, a persistent **volume** for
SQLite on `/data`, and **GitHub Actions** deploy on push to `main`.

## Tests

```bash
uv run pytest
```

The suite covers consensus math (including per-occurrence opt-outs),
recurring-slot expansion across a DST boundary, iCal output, admin JSON
export auth, and the capability URL boundaries.

## Layout

| File | What it does |
|------|----|
| [app/main.py](app/main.py) | FastAPI app + lifespan that creates SQLite tables on boot. |
| [app/models.py](app/models.py) | SQLModel tables: campaigns, players, slots, availability, occurrence opt-outs. |
| [app/security.py](app/security.py) | Token generation + SHA-256 hashing for the capability URLs. |
| [app/deps.py](app/deps.py) | Lookups that resolve a public id + secret/token to a row. |
| [app/services/slots.py](app/services/slots.py) | Expands recurring + ad-hoc slots into concrete occurrences. |
| [app/services/consensus.py](app/services/consensus.py) | Finds the earliest occurrence with at most N missing players. |
| [app/services/availability.py](app/services/availability.py) | Reads/writes the availability rows. |
| [app/services/opt_outs.py](app/services/opt_outs.py) | Per-date opt-outs on top of standing "yes" answers. |
| [app/services/ical.py](app/services/ical.py) | Minimal RFC 5545 calendar file builder. |
| [app/services/campaign_export.py](app/services/campaign_export.py) | JSON backup payload (no secrets). |
| [app/routes/](app/routes) | Index, public, admin, and player route modules. |
| [templates/](templates) | Jinja templates (Tailwind via CDN, htmx for partial updates). |

## Security model

URLs *are* the credentials. Tokens are stored only as SHA-256 hashes, so a
leaked database file does not give anyone access. If a player URL leaks,
the admin can regenerate it from the dashboard, which invalidates the old
one.

Because tokens are sensitive, they live in path segments rather than query
strings (so they don't end up in access logs). Use HTTPS in production.

## Hosting notes

SQLite + a single uvicorn worker is enough for a few campaigns and
players. If you ever want multiple workers, point `DND_SCHEDULER_DB_URL`
at Postgres and you're done — there is no SQLite-specific code in the
services.
