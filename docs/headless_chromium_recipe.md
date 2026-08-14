# Running headless Chromium here — the no-root recipe

**Status: verified working in this container on 2026-08-10.** A previous worker
recorded that headless Chromium could not run here because installing its system
libraries needs root. That is **wrong**, and it cost the template a whole class
of testing: nothing in it had ever been *rendered*. You do not need root. You
need nine `.deb` files unpacked into a directory you own and one environment
variable.

This file is the whole recipe, start to finish, so nobody rediscovers it.

---

## Why any of this is needed

Playwright downloads a Chromium build into `~/.cache/ms-playwright/` without
root. That binary is dynamically linked against system libraries (audio,
accessibility, a few X protocol libraries) that a slim container does not carry.
Missing them, the browser fails to launch — which looks exactly like "you can't
run a browser here", but is only "nine files are absent".

The libraries are needed at **load** time, not install time, so they do not have
to be installed system-wide. Unpack them anywhere and point the dynamic loader
at that directory with `LD_LIBRARY_PATH`.

## Step 1 — install Playwright and download the browser (no root)

```bash
python3 -m venv "$SCRATCH/otreevenv"
"$SCRATCH/otreevenv/bin/pip" install playwright pillow uvicorn requests
"$SCRATCH/otreevenv/bin/playwright" install chromium     # ~115 MB into ~/.cache
```

`pillow` is not optional for this repo's render checks: the scroll-affordance
assertions are made on **rendered pixels**, so something has to decode the PNG.

## Step 2 — find out exactly what is missing

Never guess the package list; ask the binary.

```bash
ldd ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | grep 'not found' | sort -u
```

In this container (Ubuntu 24.04) that printed exactly nine:

| missing `.so`            | Ubuntu 24.04 package   |
|--------------------------|------------------------|
| `libasound.so.2`         | `libasound2t64`        |
| `libatk-1.0.so.0`        | `libatk1.0-0t64`       |
| `libatk-bridge-2.0.so.0` | `libatk-bridge2.0-0t64`|
| `libatspi.so.0`          | `libatspi2.0-0t64`     |
| `libXcomposite.so.1`     | `libxcomposite1`       |
| `libXdamage.so.1`        | `libxdamage1`          |
| `libXfixes.so.3`         | `libxfixes3`           |
| `libxkbcommon.so.0`      | `libxkbcommon0`        |
| `libXrandr.so.2`         | `libxrandr2`           |

Note the `t64` suffixes: Ubuntu 24.04 renamed several of these in the 64-bit
`time_t` transition, so the pre-24.04 names (`libasound2`, `libatk1.0-0`) do not
resolve. Take the names from `apt-cache search`, not from an old blog post.

## Step 3 — a private apt root, so `apt-get update` needs no root

`apt-get download` fails with *"has no candidate"* when the package index is
empty, and `apt-get update` cannot write to `/var/lib/apt/lists` as a normal
user. Point apt at directories you own instead:

```bash
cd "$SCRATCH/sysroot"
mkdir -p aptroot/lists/partial aptroot/cache/archives/partial aptroot/etc debs
cp /etc/apt/sources.list.d/ubuntu.sources aptroot/etc/

cat > aptroot/apt.conf <<EOF
Dir::State::Lists "$PWD/aptroot/lists";
Dir::Cache "$PWD/aptroot/cache";
Dir::Cache::archives "$PWD/aptroot/cache/archives";
Dir::Etc::SourceList "/dev/null";
Dir::Etc::SourceParts "$PWD/aptroot/etc";
Dir::State::status "/var/lib/dpkg/status";
Acquire::Languages "none";
EOF

export APT_CONFIG=$PWD/aptroot/apt.conf
apt-get update            # ~30 MB of index, no root needed
```

`Dir::Etc::SourceList "/dev/null"` plus `SourceParts` pointing at your own
directory is what stops apt reading the host's third-party sources (docker,
nodesource) that you do not need. One harmless `rm: cannot remove
'/var/cache/apt/archives/partial/*.deb': Permission denied` warning is normal —
the download still lands in your own cache.

## Step 4 — download and unpack into the sysroot

```bash
cd debs
apt-get download libasound2t64 libatk1.0-0t64 libatk-bridge2.0-0t64 \
                 libatspi2.0-0t64 libxcomposite1 libxdamage1 libxfixes3 \
                 libxkbcommon0 libxrandr2
cd ..
mkdir -p root
for d in debs/*.deb; do dpkg-deb -x "$d" root/; done
```

`dpkg-deb -x` is a plain archive extraction — no dpkg database, no root, no
side effects on the system. Total download: about 764 kB.

The layout you end up with (the part that matters):

```
$SCRATCH/sysroot/
├── aptroot/            # private apt state (throwaway)
├── debs/               # the nine .deb files
└── root/
    └── usr/lib/x86_64-linux-gnu/
        ├── libasound.so.2
        ├── libatk-1.0.so.0
        ├── libatk-bridge-2.0.so.0
        ├── libatspi.so.0
        ├── libXcomposite.so.1
        ├── libXdamage.so.1
        ├── libXfixes.so.3
        ├── libxkbcommon.so.0
        └── libXrandr.so.2
```

## Step 5 — verify, then run

```bash
export LD_LIBRARY_PATH=$SCRATCH/sysroot/root/usr/lib/x86_64-linux-gnu
ldd ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome | grep 'not found'   # → nothing
LD_LIBRARY_PATH=$LD_LIBRARY_PATH "$SCRATCH/otreevenv/bin/python" tests/render_check.py
```

`LD_LIBRARY_PATH` must be set for the process that **launches** the browser —
exporting it in the shell that runs the test is enough, because the browser is a
child process. No sandbox flags were needed here; `pw.chromium.launch()` works
as-is (`--no-sandbox` also works if a future container refuses to unshare).

## Gotchas worth knowing before you trust a screenshot

- **Playwright hides scrollbars by default.** `--hide-scrollbars` is one of its
  default headless arguments, so every screenshot silently loses the clearest
  "this region scrolls" signal, and any check measuring that affordance off the
  pixels is judging a page no participant sees. Launch with
  `pw.chromium.launch(ignore_default_args=['--hide-scrollbars'])`. This bit us:
  a scroll affordance measured as absent was present all along, and the reverse
  is just as possible.
- **Fonts.** Text rendered correctly here with the container's own fonts; if a
  future box renders tofu boxes, unpack `fonts-dejavu-core` into the same
  sysroot the same way.
- **Emoji are tofu without an emoji font** (hit 2026-08-12 by the
  experimenter-dashboard render check: its terminal-state emoji all rendered
  as boxes while every DOM assertion passed — a measured check on textContent
  does not see fonts). Fix, no root needed: `apt-get download
  fonts-noto-color-emoji` via the same private apt root, `dpkg-deb -x` it,
  then copy `NotoColorEmoji.ttf` into `~/.fonts/` — fontconfig picks
  `~/.fonts` up without any cache step Chromium needs. Also from the same
  incident: U+2717 BALLOT X is tofu in the container's TEXT fonts even though
  ✓ U+2713 renders; prefer × (U+00D7), which every font carries.
- **`page.evaluate` still works with `java_script_enabled=False`.** Playwright
  evaluates in an isolated world, so you can drive and measure a page whose own
  scripts never ran — which is exactly how the no-JS legs are asserted.
- **Screenshot in production mode.** With `OTREE_PRODUCTION` set, oTree's DEBUG
  var-dump panel and this template's testing-only skip buttons are absent, so
  the screenshots show the participant's page rather than the developer's.

## Xvfb for the HEADED legs (the outro no-eject check) — same no-root trick

**Headless Chromium can never fire a real blur.** Measured 2026-08-14, both
builds (headless shell and `--headless=new`): every page is pinned
`visible`/focused forever — `bring_to_front`, `window.open`, CDP
`Target.activateTarget`, `Page.setWebLifecycleState` fire *nothing*, and
`Emulation.setVisibilityState` does not exist any more. So
`check_outro_never_ejects` (render_check.py) needs a **headed** Chromium on a
virtual display, where a same-window tab switch fires the real `blur`/`focus`
events the tab monitor listens for.

```bash
cd /home/dev/.chromium-sysroot            # the same private apt root as above
export APT_CONFIG=$PWD/aptroot/apt.conf
apt-get -o Debug::NoLocking=1 -y --download-only install xvfb
for d in aptroot/cache/archives/*.deb; do dpkg-deb -x "$d" root/; done
```

Two gotchas, both already handled by the test itself (`_start_xvfb`):

- **Xvfb hardcodes `/usr/bin` as the xkbcomp directory** (compile-time
  `XkbBinDirectory`; there is no flag and no env var in this build). Without
  root the fix is a byte-patch of a *temp copy*: replace `/usr/bin\0` with the
  equal-length `/tmp/xkb\0` and symlink the sysroot's `xkbcomp` at
  `/tmp/xkb/xkbcomp`. The test does this at runtime; nothing in the sysroot
  is modified.
- **Playwright's focus emulation eats the events.** Playwright enables
  `Emulation.setFocusEmulationEnabled` on every page it drives, which keeps
  the page reporting focused through a real tab switch. Disable it for the
  page under test, then activate the other tab via a browser-level CDP
  session (`Target.activateTarget`) — the blur that fires is Chrome's own.

Headed Chrome also refuses to start where unprivileged user namespaces are
restricted unless Playwright's default `--no-sandbox`-equivalent applies;
`pw.chromium.launch(headless=False, env={..., 'DISPLAY': ':99'})` through
Playwright worked here as-is.

## Where this is used

- `tests/render_check.py` — renders every participant-facing page at three
  viewports into `_ai/render_check/`, then asserts the layout contract by
  measurement (card gaps, scrolling, focus rings, the monitor overlay, the
  scroll affordance measured off the pixels).
- `skills_claude/writing_tests.md` — the "Rendering checks" section, which is
  where a future agent will look first.
