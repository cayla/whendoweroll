# Fly.io

## One-time

1. Install [flyctl](https://fly.io/docs/hands-on/install-flyctl/).
2. `fly auth login`
3. Pick a **globally unique** app name. Edit `fly.toml` top-level `app = "..."` if `dnd-scheduler` is taken.
4. Create the app (if it does not exist yet):

   ```bash
   fly apps create <your-app-name-from-fly.toml>
   ```

5. **Persistent SQLite** — create a volume in the **same region** as `primary_region` in `fly.toml` (default `iad`):

   ```bash
   fly volumes create dnd_data --region iad --size 1
   ```

   The volume name `dnd_data` must match `[[mounts]]` → `source` in `fly.toml`.

   **About Fly’s “create two or more volumes” warning** — Volumes are [pinned to one physical host](https://fly.io/docs/volumes/overview/). If that host has a bad day, a single volume can be unavailable until Fly recovers or you restore from backup. Fly therefore nudges you toward **two volumes** so you can run **two Machines** in the same region and stay up if one host dies.

   For **this app + SQLite**, one volume is the normal choice: SQLite expects a **single writable file** anyway, so a second volume does **not** give you automatic HA (you’d need a replicated database or external store, not two independent SQLite files). Treat the warning as “know the tradeoff”: fine for a personal scheduler; if you need strong uptime guarantees, plan **Postgres** (e.g. Fly Postgres) or accept operational risk on SQLite.

6. Optional secrets / env (no secrets required for the stock SQLite path):

   ```bash
   fly secrets set DND_SCHEDULER_DISABLE_NEW_CAMPAIGNS=1
   ```

   The image already sets `DND_SCHEDULER_DB_URL=sqlite:////data/dnd_scheduler.sqlite3`; override with `fly secrets set` if you change layout.

## Deploy from laptop

```bash
fly deploy
```

By default that builds the `production` stage from this repo’s `Dockerfile` on Fly’s builders.

To deploy the same image CI pushed to GitHub Container Registry (after a **`main`** workflow run):

```bash
fly deploy --image ghcr.io/<owner>/dnd-scheduler:<git-sha>
```

Use the **commit SHA** tag from the Actions run (immutable). The workflow also updates a **`latest`** tag on each `main` push.

**GHCR pull access:** Fly Machines must be allowed to pull the image. Easiest path: in GitHub, open the **Packages** entry for this image and set visibility to **public**. For a private package, configure Fly with a registry credential (see [Using GHCR on Fly.io](https://fly.io/docs/app-guides/using-github-container-registry/)).

## GitHub Actions (merge → build → push → deploy)

1. Create a deploy token: [Fly.io tokens](https://fly.io/dashboard/personal/tokens) or `fly tokens create deploy -x 8760h`.
2. In the GitHub repo: **Settings → Secrets and variables → Actions** → add **`FLY_API_TOKEN`**.

Pushes to **`main`** run `.github/workflows/ci.yml`: build the **test** Docker stage and run pytest, then build **production**, push **`ghcr.io/<repo-owner>/<repo>:<sha>`** and **`:latest`**, then **`fly deploy --image`** with the SHA tag. Pull requests run build + tests only (no push, no deploy).

## Notes

- **Single Machine + volume**: SQLite is fine for a small single-tenant workload; scale-out would need a different datastore.
- **Cold starts**: With `min_machines_running = 0`, the first request after idle may wake a Machine; set `min_machines_running = 1` in `fly.toml` if you want it always warm (extra cost).
