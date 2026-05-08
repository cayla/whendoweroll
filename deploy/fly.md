# Fly.io

## One-time

1. Install [flyctl](https://fly.io/docs/hands-on/install-flyctl/).
2. `fly auth login`
3. Pick a **globally unique** app name. Edit `fly.toml` top-level `app = "..."` if `whendoweroll` is taken.
4. Create the app (if it does not exist yet):

   ```bash
   fly apps create <your-app-name-from-fly.toml>
   ```

5. **Persistent SQLite** — create a volume in the **same region** as `primary_region` in `fly.toml` (default `iad`):

   ```bash
   fly volumes create whendoweroll_data --region iad --size 1
   ```

   The volume name `whendoweroll_data` must match `[[mounts]]` → `source` in `fly.toml`.

   The image runs as a non-root user (`appuser`, UID **1000**). The build-time
   `chown` on `/data` is masked the moment Fly mounts the volume, so on the
   first deploy after creating (or recreating) a volume you need to set its
   ownership once from inside a running Machine:

   ```bash
   fly ssh console
   chown -R 1000:1000 /data
   chmod u+rwX /data
   exit
   fly machine restart
   ```

   After that the volume keeps the right ownership across deploys because the
   UID is pinned in the Dockerfile.

   **About Fly’s “create two or more volumes” warning** — Volumes are [pinned to one physical host](https://fly.io/docs/volumes/overview/). If that host has a bad day, a single volume can be unavailable until Fly recovers or you restore from backup. Fly therefore nudges you toward **two volumes** so you can run **two Machines** in the same region and stay up if one host dies.

   For **this app + SQLite**, one volume is the normal choice: SQLite expects a **single writable file** anyway, so a second volume does **not** give you automatic HA (you’d need a replicated database or external store, not two independent SQLite files). Treat the warning as “know the tradeoff”: fine for a personal scheduler; if you need strong uptime guarantees, plan **Postgres** (e.g. Fly Postgres) or accept operational risk on SQLite.

6. Optional secrets / env (no secrets required for the stock SQLite path):

   ```bash
   fly secrets set WHENDOWEROLL_DISABLE_NEW_CAMPAIGNS=1
   ```

   **Super admin** (`/internal/super-admin`): set a stable password and cookie signing secret so restarts do not rotate them:

   ```bash
   fly secrets set WHENDOWEROLL_SUPER_ADMIN_PASSWORD='...' WHENDOWEROLL_SUPER_ADMIN_COOKIE_SECRET='...'
   ```

   If you omit these, the app logs a random password once per process start (check `fly logs`).

   The image already sets `WHENDOWEROLL_DB_URL=sqlite:////data/whendoweroll.sqlite3`; override with `fly secrets set` if you change layout.

## Deploy from laptop

```bash
fly deploy
```

By default that builds the `production` stage from this repo’s `Dockerfile` on Fly’s builders.

To deploy the same image CI pushed to GitHub Container Registry (after a **`main`** workflow run):

```bash
fly deploy --image ghcr.io/<owner>/whendoweroll:<git-sha>
```

Use the **commit SHA** tag from the Actions run (immutable). The workflow also updates a **`latest`** tag on each `main` push.

**Registry visibility:** This flow assumes the image lives on a **public** registry (GHCR is fine once the package is **public** in GitHub), which matches how Fly documents deploying from Docker Hub or another public registry—see [To deploy a public image from Docker Hub or another public registry](https://fly.io/docs/blueprints/using-the-fly-docker-registry/#to-deploy-a-public-image-from-docker-hub-or-another-public-registry) in Fly’s [Managing Docker Images with Fly.io’s Private Registry](https://fly.io/docs/blueprints/using-the-fly-docker-registry/) blueprint. For images that stay **private**, Fly’s own path is build/push to **`registry.fly.io/<app>:<tag>`** with `fly auth docker`, then `fly deploy --image` (same guide, [private image](https://fly.io/docs/blueprints/using-the-fly-docker-registry/#to-deploy-a-private-image-pushed-to-flyios-registry) section).

## GitHub Actions (merge → build → push → deploy)

1. Create a deploy token: [Fly.io tokens](https://fly.io/dashboard/personal/tokens) or `fly tokens create deploy -x 8760h`.
2. In the GitHub repo: **Settings → Secrets and variables → Actions** → add **`FLY_API_TOKEN`**.

Pushes to **`main`** run `.github/workflows/ci.yml`: build the **test** Docker stage and run pytest, then build **production**, push **`ghcr.io/<repo-owner>/<repo>:<sha>`** and **`:latest`**, then **`fly deploy --image`** with the SHA tag. Pull requests run build + tests only (no push, no deploy).

## Notes

- **Single Machine + volume**: SQLite is fine for a small single-tenant workload; scale-out would need a different datastore.
- **Cold starts**: This repo's `fly.toml` ships with `min_machines_running = 1` so the Machine stays warm. Drop it to `0` if you'd rather pay nothing while idle and accept a wake-up delay on the first request.
