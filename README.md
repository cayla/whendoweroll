# When Do We Roll

A lightweight Python web app for scheduling tabletop sessions. No accounts —
each campaign hands out three kinds of unguessable URL: an admin link, a
public read-only link, and one private link per player.

## What it does

- The campaign creator (typically a mandatory attendee — e.g. the GM) sets up
  a campaign with a name, timezone, and the player roster.
- They define time slots: any number of recurring weekly windows
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
- **JSON import** (home page): upload a previously exported file and the app
  materializes it into a brand-new campaign with a fresh admin link and
  fresh per-player links. Useful as a backup-and-restore path or for
  duplicating an existing campaign template.
- **iCalendar**: every campaign has a single shared feed at
  `…/c/{public_id}/calendar-consensus.ics`. It lists the upcoming windows
  that qualify under the campaign's **scheduling policy** (see below), after
  **public tempo** thinning (see below); near-consensus windows (one player
  missing) are prefixed with `[missing: <name>]` so they're easy to spot in
  a calendar. Opt-outs are honoured. The link is surfaced on the admin,
  public, and per-player pages — there is no per-player feed.
- The campaign home page shows the next two qualifying sessions as
  prominent cards: solid emerald when full consensus, dashed amber for a
  near-consensus window (the holdout's name is shown so the organizer can
  nudge them). Both cards are doubled up with a black-and-white
  adventuring-party silhouette — the near-consensus card fades one party
  member out — so the difference reads at a glance for color-blind
  viewers too.
- A campaign can mark **any number of players as mandatory attendees**
  (e.g. the GM, or co-GMs). When set, *all* mandatory attendees must be
  available for any window to count toward consensus on the public page
  and the ICS feed, regardless of policy.

A response of "no answer yet" is treated as **not available** for those
calculations, so the organizer never over-promises.

### Scheduling policy

The campaign's **scheduling policy** decides which upcoming windows count
as a real session — it drives both the two summary cards on the public
page and the consensus calendar feed (so subscribers can rely on it as
the actual play schedule). Mandatory-attendee rules apply on top of every
policy. Pick one in admin → Settings:

| Policy | What it surfaces |
| --- | --- |
| **Strict — everyone every time** | Only windows where every player is available. The "near-consensus" card disappears. |
| **Allow one missing — never two in a row** *(default)* | Windows with at most one holdout, but never two short-handed sessions back-to-back. |
| **Allow one missing — but rotate who** | Windows with at most one holdout, and the same player can't be the holdout in two consecutive sessions. |
| **Allow one missing — always** | Windows with at most one holdout, no further constraint. |

### Public tempo (cards + calendar only)

**Player** pages always show the full expanded list of recurring and ad-hoc
windows. The **public** campaign page and the **consensus `.ics` feed** use a
campaign-level **tempo** setting (admin → Settings) to thin *recurring* rows
so the roster is not overwhelmed:

| Mode | Meaning |
| --- | --- |
| **Weekly** | Momentum chain with a **7-day** anchor between kept listings. |
| **Every two weeks (~14 days)** | Same idea with a **14-day** anchor (this is *not* “two sessions per calendar month”). |
| **About once a month** | Anchors advance by **one calendar month** (same local time-of-day; short months clamp). |

How it works: the **first** kept row is the earliest recurring start that meets
the same **per-window** bar as the summary cards (full vs one missing, per
policy). Each **next** row is chosen among later starts inside a lookahead
bracket, **closest in time** to the next anchor (with sensible tie-breaks).
Ad-hoc sessions are not tempo-thinned.

The two **summary cards** and the ICS builder then run **`find_next_meets`**
on that already-thinned list. That step adds **between-window** guardrails
(e.g. never two near-consensus sessions in a row). So the first solid-green
card is not always the first tempo-chain row: it is the first window that
passes **both** the tempo pass and the guardrail pass.

With **Prefer full party** enabled in admin → Settings (on by default), whenever
a summary card would be **all-but-one** (one holdout), the picker checks the
**full expanded horizon** (not just tempo-thinned rows) for a **full** window
within **48 hours** afterward and promotes it when found (e.g. Friday short one
vs Saturday everyone). Policies that never allow a holdout skip this rule.

With **no players** on the roster, public/ICS recurring listings stay empty
until someone exists to satisfy the policy bar.

**JSON import** still accepts the legacy string `twice_per_month` on old
exports; it is normalized to **`two_weeks`**.

### Display timezone (player + public pages)

Times default to the **campaign** timezone (how recurring rules are defined).
Visitors can switch to their own IANA zone: a `whendoweroll_viewer_tz` cookie
(path `/`) stores the choice. On first load, a small script reads
`Intl.DateTimeFormat().resolvedOptions().timeZone`, sets the cookie, and
reloads once so times match the browser without opening the dropdown.

## Run it

You need **[uv](https://docs.astral.sh/uv/getting-started/installation/)** (Python) and **[Node.js](https://nodejs.org/)** (npm) for local development — Node is only used to compile CSS, not at runtime.

```bash
npm ci && npm run build:css   # compile Tailwind → static/css/tailwind.css
uv sync --group dev
uv run uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000> and create a campaign.

If styles look unstyled or layout is broken, run `npm run build:css` again (see [Frontend (Tailwind CSS)](#frontend-tailwind-css)).

To skip the by-hand setup on a fresh dev DB,
[`test-campaign-export.json`](test-campaign-export.json) is a checked-in
backup with a few players and recurring slots. Upload it via the **Restore
a backup** form on the home page and you'll land on a created-campaign
page with a fresh admin link and per-player links.

## Frontend (Tailwind CSS)

Templates use **Tailwind CSS v3** utility classes. Shared component styling and theme tokens live in [`static/css/app.css`](static/css/app.css) (plain CSS variables — not `@apply`). The compiled utility bundle is [`static/css/tailwind.css`](static/css/tailwind.css); **do not edit that file by hand**.

| File | Role |
| --- | --- |
| [`package.json`](package.json) / [`package-lock.json`](package-lock.json) | npm scripts and Tailwind dev dependency. |
| [`tailwind.config.js`](tailwind.config.js) | Scans `templates/` and `static/js/`; theme colors map to CSS variables from `app.css`. |
| [`static/css/tailwind-src.css`](static/css/tailwind-src.css) | Tailwind entry (`@tailwind` directives). |
| [`static/css/tailwind.css`](static/css/tailwind.css) | **Build output** — linked from [`templates/base.html`](templates/base.html) before `app.css`. |

Build (required after changing classes in templates or JS):

```bash
npm ci              # first time, or when package-lock.json changes
npm run build:css   # writes static/css/tailwind.css (minified)
```

**htmx** is still loaded from jsDelivr in `base.html`; only Tailwind moved off the CDN (which logged a production warning in the browser).

**Docker / CI:** The [`Dockerfile`](Dockerfile) `assets` stage runs `npm run build:css` and copies the result into the `test` and `production` images. Deployed environments do not need Node installed.

**`docker compose up` with a bind mount:** The repo directory is mounted over `/app`, so the container uses your host's `static/css/tailwind.css`. Run `npm run build:css` on the host after pulling or editing templates, or styles will be missing even though the image built successfully.

## Docker (ECS / Fargate-friendly)

The image runs **uvicorn** as a non-root user and stores SQLite at
`/data/whendoweroll.sqlite3` by default. Python dependencies are installed with
**uv** from [`pyproject.toml`](pyproject.toml) and a frozen
[`uv.lock`](uv.lock) (production images use `uv sync --frozen` without dev
groups). A **Node** build stage compiles Tailwind before the final image is
assembled — no Node runtime in production. Mount an **EFS**
(or EBS) volume on
`/data` so the file survives task restarts. Use **one task** (or one worker)
per SQLite file — SQLite is not a multi-writer cluster store. For horizontal
scale, point `WHENDOWEROLL_DB_URL` at Postgres instead.

```bash
docker compose up --build
```

With the default bind mount, also run `npm run build:css` on the host so
`static/css/tailwind.css` exists under the mounted tree (see above).

Build only:

```bash
docker build -t whendoweroll .
docker run -p 8000:8000 -v whendoweroll_data:/data whendoweroll
```

## Fly.io

See [deploy/fly.md](deploy/fly.md) for `fly.toml`, a persistent **volume** for
SQLite on `/data`, and **GitHub Actions** deploy on push to `main`.

## Tests

```bash
uv run pytest
```

Or via Docker (builds Tailwind inside the image; no host `npm` required):

```bash
docker compose --profile test run --build --rm test
```

The suite covers consensus math (including per-occurrence opt-outs and
each scheduling policy's window-selection + sequence guardrails),
public tempo thinning, recurring-slot expansion across a DST boundary,
iCal output, admin JSON export auth, import/restore, SQLite migrations,
and the capability URL boundaries.

## Layout

| File | What it does |
|------|----|
| [app/main.py](app/main.py) | FastAPI app + lifespan that creates SQLite tables on boot. |
| [app/db.py](app/db.py) | Engine, session factory, and small SQLite startup migrations. |
| [app/settings.py](app/settings.py) | Process-level env settings (e.g. disable new campaigns) + super-admin runtime override. |
| [app/models.py](app/models.py) | SQLModel tables: campaigns, players, slots, availability, occurrence opt-outs. |
| [app/security.py](app/security.py) | Token generation + SHA-256 hashing for the capability URLs. |
| [app/super_admin_auth.py](app/super_admin_auth.py) | Operator challenge password + signed session cookie for `/internal/super-admin`. |
| [app/deps.py](app/deps.py) | Lookups that resolve a public id + secret/token to a row. |
| [app/display_time.py](app/display_time.py) | Viewer-local time formatting for player / public templates. |
| [app/templates_setup.py](app/templates_setup.py) | Single Jinja environment + custom filters, plus the timezone choice list. |
| [app/view_timezone.py](app/view_timezone.py) | Per-viewer display-timezone cookie helpers. |
| [app/services/slots.py](app/services/slots.py) | Expands recurring + ad-hoc slots into concrete occurrences. |
| [app/services/consensus.py](app/services/consensus.py) | Finds upcoming qualifying windows under the campaign's scheduling policy (honoring mandatory attendees and per-occurrence opt-outs); sequence guardrails run after public tempo thinning. |
| [app/services/public_occurrence_filter.py](app/services/public_occurrence_filter.py) | Thins recurring occurrences for the public page and consensus ICS by campaign tempo (player pages use full expansion). |
| [app/services/availability.py](app/services/availability.py) | Reads/writes the availability rows. |
| [app/services/opt_outs.py](app/services/opt_outs.py) | Per-date opt-outs on top of standing "yes" answers. |
| [app/services/occurrence_match.py](app/services/occurrence_match.py) | Validates a client-submitted instant against a slot's expansion. |
| [app/services/timeutil.py](app/services/timeutil.py) | UTC normalization for occurrence keys (DB round-trips). |
| [app/services/ical.py](app/services/ical.py) | Minimal RFC 5545 calendar file builder. |
| [app/services/campaign_export.py](app/services/campaign_export.py) | JSON backup payload (no secrets). |
| [app/services/campaign_import.py](app/services/campaign_import.py) | Restore an export into a brand-new campaign. |
| [app/services/campaign_delete.py](app/services/campaign_delete.py) | Cascade delete a campaign and all its dependent rows. |
| [app/routes/](app/routes) | Index, public, admin, player, and super-admin route modules. |
| [templates/](templates) | Jinja templates + htmx partial updates. |
| [static/css/app.css](static/css/app.css) | Theme tokens and component classes (buttons, tables, home page, …). |
| [static/css/tailwind.css](static/css/tailwind.css) | Compiled Tailwind utilities (generated; run `npm run build:css`). |
| [static/js/](static/js/) | Small page scripts (theme, modals, admin confirm dialog). |
| [package.json](package.json) | `npm run build:css` — Tailwind CLI for local dev and Docker `assets` stage. |

## Security model

URLs *are* the credentials. Tokens are stored only as SHA-256 hashes, so a
leaked database file does not give anyone access. If a player URL leaks,
the admin can regenerate it from the dashboard, which invalidates the old
one.

Because tokens are sensitive, they live in path segments rather than query
strings (so they don't end up in access logs). Use HTTPS in production.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `WHENDOWEROLL_DB_URL` | SQLAlchemy database URL (default: file-backed SQLite). |
| `WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS` | When set, home-page create/import returns 403. |
| `WHENDOWEROLL_SUPER_ADMIN_PASSWORD` | Operator password for `/internal/super-admin` (see [deploy/fly.md](deploy/fly.md)). |
| `WHENDOWEROLL_SUPER_ADMIN_COOKIE_SECRET` | Signs the super-admin session cookie (long random string). |
| `WHENDOWEROLL_STATIC_VERSION` | Optional override for cache-busting query params on `/static` CSS/JS (otherwise a content hash). |

## License

MIT — see [LICENSE](LICENSE).

## Hosting notes

SQLite + a single uvicorn worker is enough for a few campaigns and
players. If you ever want multiple workers, point `WHENDOWEROLL_DB_URL`
at Postgres and you're done — there is no SQLite-specific code in the
services.
