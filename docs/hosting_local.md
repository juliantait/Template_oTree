# Hosting an oTree study on a machine you control

This is the how-to for serving a study built from this template from hardware you
own or administer: a lab PC, a spare server, or a small always-on box such as a
Mac Mini. It is written to be followed by anyone, a researcher or an agent doing
it for them, and it has enough concrete steps to stand a study up on a Mac Mini
from this page alone. Where a step needs a person at the machine or in a
dashboard, it is marked **HUMAN STEP**.

Companions: managed hosting (no hardware, a managed Postgres, a generated HTTPS
domain) is in [`hosting_railway.md`](./hosting_railway.md), which is also the
fuller reference for what any hosted deploy needs (the boot guard, the env vars,
verifying a deploy). The study-side Prolific wiring is in
[`running_on_prolific.md`](./running_on_prolific.md).

> **This repo ships no deploy config, and that holds here too.** No compose
> file, no tunnel config, no proxy config. This page is a written record of what
> a self-hosted deploy needs, so it can be looked up and done by hand. If you
> find yourself committing any of it, stop and raise it (`.claude/decisions/build_and_deploy.md`).

## When to host it yourself, and when not to

- **A lab study** run on the lab network needs no public exposure at all: run
  the container (or `otree prodserver`) on the lab machine and point the lab PCs
  at it. Skip the tunnel sections below.
- **An online study** (Prolific) on your own box works well for small and medium
  runs and testing, and costs nothing beyond the machine. The trade-off against
  [Railway](./hosting_railway.md): you own uptime, power, network and backups.
  If the box sleeps, reboots for an update, or loses Wi-Fi mid-session, your
  participants are stranded. For a large paid run where that risk matters, use a
  managed host.

## The shape

Three layers, and keeping them separate is what keeps this simple:

```
Participant browser
    |  https://<study-host>/room/<room_name>      (TLS ends at the tunnel)
    v
Tunnel: Cloudflare Tunnel or Tailscale Funnel
    |  forwards plain HTTP to http://localhost:<port>
    v
Docker container (this template's image) on localhost:<port>
    +- volume <study>-db mounted at /app/data (the sqlite database)
```

**The one lesson that matters: give each study its own hostname pointing
straight at its container, and do not serve it under a path prefix
(`https://<your-domain>/my-study/`) through a reverse proxy.** Almost every
problem in "Gotchas" below came from the path-prefix approach. With a dedicated
hostname, the tunnel terminates HTTPS and passes WebSockets through, and the
container sees a clean root path: no prefix stripping, no redirect rewriting.

## 1. Prepare the machine

- **Docker.** Install Docker Desktop, OrbStack, or Docker Engine (Linux). Check
  with `docker run --rm hello-world`.
- **A port.** Pick one free local port per study, written `<port>` below. The
  image listens on `$PORT`, which the Dockerfile defaults; override it with
  `-e PORT=<port>` and a matching `-p <port>:<port>`.
- **Keep it awake** (macOS). A sleeping Mac serves nobody.

  > **HUMAN STEP (needs an admin password at the machine).**
  > ```bash
  > sudo pmset -a sleep 0 disksleep 0      # never sleep the system or disks
  > sudo pmset -a autorestart 1            # power back on after a power cut
  > sudo pmset -a womp 1                   # wake on network access
  > pmset -g                               # check the settings took
  > ```
  > Also in System Settings: turn off automatic macOS updates that restart the
  > machine, and enable automatic login if your container runtime only starts
  > after a user logs in (Docker Desktop and OrbStack are login items). If the
  > box is remote, `sudo pmset repeat poweron MTWRFSU 08:00:00` gives a daily
  > power-on as a last resort.

  On a lab PC (Windows), set the power plan to never sleep and disable
  restart-for-updates during study weeks.
- **Wired network if you can.** A Wi-Fi link that silently drops takes the
  tunnel with it.

## 2. Build and run the container

From the repo root on the host:

```bash
docker build -t <study> .

docker run -d --name <study> --restart unless-stopped \
  -p <port>:<port> \
  -e PORT=<port> \
  -v <study>-db:/app/data \
  -e OTREE_PRODUCTION=1 \
  -e OTREE_AUTH_LEVEL=STUDY \
  -e OTREE_ADMIN_PASSWORD=<strong password> \
  -e OTREE_REST_KEY=<random> \
  -e OTREE_SECRET_KEY=<random> \
  <study>
```

What each piece is for (the full reasoning is in
[`hosting_railway.md`](./hosting_railway.md), "What a hosted deploy needs in
general"):

| Setting | Why |
|---|---|
| `OTREE_PRODUCTION=1` | Turns DEBUG off. Without it participants see skip buttons and quiz answers. Leave it out only for a smoke test. |
| `OTREE_AUTH_LEVEL=STUDY` + `OTREE_ADMIN_PASSWORD` | Locks the admin and `/demo`. Without them anyone who finds the URL can open the admin. |
| `OTREE_REST_KEY` | Needed for the REST calls that bind the room (step 4). |
| `OTREE_SECRET_KEY` | The dev fallback in `settings.py` must not face the internet. |
| `-v <study>-db:/app/data` | Keeps the sqlite database across container replacements. Without it, `docker rm` deletes every participant. |
| `--restart unless-stopped` | Brings the container back after a crash or a reboot, once the Docker runtime is running. |
| `DATABASE_URL` (optional) | Point at a Postgres instead of the sqlite file. Sqlite on a local volume is fine for a single box; see the Postgres caveats in `hosting_railway.md`. |
| `FORWARDED_ALLOW_IPS=*` | Already baked into the image. See "Gotchas". |

Never set `RESET_DB=1` as a standing variable: it wipes the database on every
boot. The boot guard otherwise initialises the database only when it is empty.

Generate the random values with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
Keep them outside the repository (a password manager, or a file in a gitignored
folder), never in a committed file.

Check it came up:

```bash
docker logs -f <study>                 # boot banner, then the server log
curl -s http://localhost:<port>/health # 200 once a session is bound, 503 before
```

## 3. Expose it: pick one tunnel

You need an HTTPS address participants can reach. A tunnel gives you one without
opening a port on your router or exposing your home or office IP. Both options
below run as a background service on the host and come back after a reboot.

### Option A: Cloudflare Tunnel (your own domain)

Use this when you have a domain on Cloudflare and want a stable, branded URL such
as `https://<study>.<your-domain>`.

> **HUMAN STEP (Cloudflare account).** The domain must be on Cloudflare, and the
> first login opens a browser.

```bash
brew install cloudflared                     # macOS; see Cloudflare's docs for Linux/Windows
cloudflared tunnel login                     # authorises this machine for your domain
cloudflared tunnel create <tunnel-name>      # prints a tunnel ID and writes a credentials file
cloudflared tunnel route dns <tunnel-name> <study>.<your-domain>
```

Config file (`~/.cloudflared/config.yml`):

```yaml
tunnel: <tunnel-id>
credentials-file: <path-to-the-credentials-json-it-wrote>
ingress:
  - hostname: <study>.<your-domain>
    service: http://localhost:<port>       # straight to the container
  - service: http_status:404               # catch-all, must stay last
```

Each new study is one more `hostname` rule above the catch-all, plus one
`cloudflared tunnel route dns` for its hostname. Install it as a service so it
survives reboots, and restart the service after each config edit:

```bash
sudo cloudflared service install           # macOS: a LaunchDaemon; Linux: systemd
sudo launchctl kickstart -k system/com.cloudflare.cloudflared   # macOS restart after config changes
```

On macOS the service reads its config from a system location (check the
`cloudflared service install` output); keep that copy in step with the one in
your home folder, or point the service at one file.

If `cloudflared tunnel route dns` writes the record into the wrong zone (it can
when the target domain is still pending in Cloudflare), create the CNAME by hand
in the dashboard: `<study>` to `<tunnel-id>.cfargotunnel.com`, proxied.

### Option B: Tailscale Funnel (no domain needed)

Use this when you do not have a domain. Funnel publishes a port on your
machine's Tailscale name, `https://<machine>.<tailnet>.ts.net`, to the public
internet.

> **HUMAN STEP (Tailscale account).** Install Tailscale, log in, and enable
> HTTPS certificates and Funnel for the tailnet in the admin console.

```bash
tailscale funnel --bg http://localhost:<port>                 # public, on 443
tailscale funnel --bg --https=8443 http://localhost:<port>    # or another allowed port
tailscale funnel status                                       # check what is published
```

Funnel only allows a few public ports (443, 8443, 10000), so one machine can
publish at most a few studies this way. For testers who are on your tailnet
(colleagues, not participants), `tailscale serve` instead of `funnel` publishes
the same thing privately.

### Lab network only

No tunnel. Participants on the lab PCs open `http://<host-lan-address>:<port>/room/<room_name>`.
Give the host a fixed address (a DHCP reservation) so the link does not change
between sessions.

## 4. Bind a session to the room

A room link serves nothing until a session is bound to it. **Bind through the
REST API, not the `otree` CLI**: the CLI's room argument is unreliable in recent
oTree versions. This template's `scripts/start.sh` does it, reusing an existing
binding instead of replacing it, and fails loudly if it cannot bind:

```bash
OTREE_BASE_URL=https://<study-host> \
OTREE_ROOM=<room_name> \
OTREE_SESSION_CONFIG=<session_config_name> \
OTREE_NUM_PARTICIPANTS=<n> \
OTREE_AUTH_LEVEL=STUDY \
OTREE_REST_KEY=<rest-key> \
bash scripts/start.sh
```

Under the hood that is `POST /api/sessions` with `session_config_name`,
`num_participants` and `room_name`. Check the binding:

```bash
curl -s -H "otree-rest-key: <rest-key>" https://<study-host>/api/rooms
curl -s -o /dev/null -w '%{http_code}\n' https://<study-host>/health   # expect 200
```

A large session takes a while to create (oTree builds every participant-round row
inside the request); that is not a failure, and re-running the script is safe.

Share `https://<study-host>/room/<room_name>` (for Prolific, append
`?participant_label={{%PROLIFIC_PID%}}`; see
[`running_on_prolific.md`](./running_on_prolific.md)). The admin is at
`https://<study-host>/admin/`.

## 5. Rehearse a crash before any paid run

1. Note the bound `session_code` from `/api/rooms`.
2. `docker restart <study>`, then reboot the whole machine once.
3. Confirm the container came back on its own, the tunnel answers, and
   `/api/rooms` shows the SAME session code. Same code means data and binding
   survive a restart.

## Persistence and backups

- The database lives in the Docker volume `<study>-db`, not in the image and not
  in the repo. `docker rm <study>` keeps it; `docker volume rm <study>-db`
  deletes it.
- **Export from the admin during and after the run** (Data tab), or with the
  script, which writes the wide and page-times CSVs:
  ```bash
  python scripts/export_data.py --base-url https://<study-host> --out <backup-dir>
  ```
- **Copy the raw database** as a second backup (safe while running for a quick
  snapshot; stop the container first for a guaranteed-consistent copy):
  ```bash
  docker cp <study>:/app/data/db.sqlite3 <backup-dir>/db-$(date +%Y%m%d-%H%M).sqlite3
  ```
  That copy is also what `scripts/predeploy_check.sh` wants before you deploy
  new code over a study with participants.
- Keep backups off the host disk (another machine or cloud storage). Avoid
  writing frequent large backups into a folder that syncs to other devices; every
  rewrite gets re-uploaded and re-downloaded.

## Updating, switching studies, and taking it down

- **New code for the same study:** never over a running session. Let it finish,
  run `scripts/predeploy_check.sh <copy-of-live-db>`, then:
  ```bash
  docker build -t <study> .
  docker stop <study> && docker rm <study>
  docker run ...same command as step 2, same volume...
  ```
- **A different study on the same port:** stop and remove the old container,
  then build and run the new one on the same `<port>` with its own volume. The
  tunnel keeps pointing at `localhost:<port>`, so nothing downstream changes.
  Reusing one fixed port for a rolling "test study" slot is a convenient
  convention.
- **Taking it offline but revivable:** `docker stop <study>` keeps the image,
  container and volume; `docker start <study>` brings it back. While it is
  stopped the public hostname returns a 502, which is expected; the tunnel rule
  can stay.

## Gotchas

- **`http://` links behind HTTPS.** The tunnel terminates TLS and forwards plain
  HTTP with an `X-Forwarded-Proto: https` header. Uvicorn ignores that header
  unless it trusts the sender, and the request arrives from the Docker gateway,
  not `127.0.0.1`. Without `FORWARDED_ALLOW_IPS=*` oTree builds `http://`
  redirects and asset links that break. The image bakes it in; if you build your
  own image, bake it in too, and pass `-e FORWARDED_ALLOW_IPS='*'` as well.
- **Path-prefix proxying through nginx (avoid).** If you must serve under
  `https://<your-domain>/<prefix>/`, all of these bite:
  - WebSockets fail (`HTTP 400 "Unsupported upgrade request."`) unless the
    location sets `proxy_http_version 1.1;`, `proxy_set_header Upgrade
    $http_upgrade;` and `proxy_set_header Connection $connection_upgrade;`, with a
    top-level `map $http_upgrade $connection_upgrade { default upgrade; '' close; }`.
    Setting `Connection "upgrade"` unconditionally breaks ordinary requests.
  - `proxy_pass http://localhost:<port>/;` needs the trailing slash, or nginx
    forwards the full prefixed path and oTree returns 404.
  - oTree builds `Location:` headers from the proxied request, so redirects leak
    `http://localhost/...`. You need `proxy_set_header Host $host;`,
    `proxy_set_header X-Forwarded-Proto $scheme;` and a `proxy_redirect` rewrite.
    Fragile; a dedicated hostname avoids all of it.
  - Any tool that regenerates the nginx config will wipe a hand-edited block.
- **Room binding via the CLI fails.** Symptoms in the logs: `unrecognized
  arguments: --room_name`, or `ModuleNotFoundError` when a helper snippet runs
  outside the environment oTree was installed in. Use the REST API (step 4).
- **The container is up but the study is dead.** A port that answers is not a
  working study. Check `/health` (200 means the database answers and a session is
  bound) rather than the container status. `scripts/verify_deploy.py` proves the
  running build is the commit you meant to deploy.
- **Reboots.** `--restart unless-stopped` only helps once the Docker runtime
  itself is running. On macOS that means the runtime starts at login, and the
  machine logs in automatically after a power cut. Test it (step 5).
- **macOS permission prompts.** After an update, macOS can show a permission
  dialog on the machine's own screen (for the container runtime or the tunnel)
  and block until someone clicks Allow. If containers hang in "Created" for no
  reason, look at the physical screen.
- **Everything on one box.** Other heavy jobs on the host (builds, data analysis,
  other containers) compete with the study for memory. Cap other containers'
  memory, and keep the host quiet during a session.
