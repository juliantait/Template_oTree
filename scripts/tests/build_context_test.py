#!/usr/bin/env python3
""".dockerignore — BOTH DIRECTIONS: what left the build context, and what stayed.

WHY THIS EXISTS WHEN THE FILE IS ALREADY CLEAN
==============================================
This template's `.dockerignore` already excludes `data/`, `db.sqlite3`, `_ai/`,
`.venv/`, `previews/`, `*.log`, `.env` and the host-side `*.command` launchers,
and it already spells the nested cases `**/`. So there is no hazard here to
remove — and that is precisely the problem this file solves. **A clean
`.dockerignore` is a state, not a property.** The Dockerfile is `COPY . .`, so
every future directory somebody adds ships by default, and the two ways that
goes wrong are silent in opposite directions:

  * a HAZARD arrives (an `exports/` of participant CSVs, a curl cookie jar, a
    database snapshot) and is baked into an image that gets pushed to a
    registry and keeps every layer forever; nothing fails, the study runs fine;
  * a line added to stop that ALSO EXCLUDES SOMETHING THE APP RENDERS FROM.
    That is not hypothetical: a build-context fault shipped `_templates` EMPTY
    on 2026-08-11 in the study this template came from, and the live room
    welcome page returned 500 for every participant who followed the entry URL
    while every source-tree test stayed green.

Neither direction produces an error, a red test or a 5xx anywhere a developer
looks. So both directions are asserted here.

WHAT THIS ASSERTS
=================
  A. THE RULES PARSE, and the file still carries the entries it must.
  B. THE MATCHER IS DOCKER'S MATCHER — self-tested against the pattern
     semantics that actually bite (a pattern with no `/` matches at the CONTEXT
     ROOT ONLY, `*` does not cross `/`, `**/` matches zero or more segments).
     Asserted rather than assumed: every claim below is only as good as this.
  C. WHAT LEFT — by PATH and by CONTENT. Content matters because "no path
     starts with `data/`" is a claim about names, and the requirement is about
     bytes: a `data_backup/`, a `db.sqlite3.old` or a `cookies.txt.bak` slips a
     name check while carrying exactly the same participant answers, Prolific
     IDs and admin session cookies.
  D. WHAT STAYED — every path the app renders from, DERIVED (see below), never
     retyped.
  E. THE GUARD ACTUALLY FIRES. Every absence asserted in C and D is paired with
     a demonstration that the same check goes RED when the property is broken —
     an over-broad rule set for D, no rules at all for C, and synthetic hazard
     files for each content detector. An absence-only test is indistinguishable
     from a test of nothing (CLAUDE.md, testing standard).
  F. THE SIZE, measured over the same tree at the same moment, not remembered
     from a terminal.

WHERE THE MUST-SURVIVE LIST COMES FROM, AND WHY NOT THE DOCKERFILE
==================================================================
It is DERIVED FROM THE SOURCE TREE, plus the two files that already answer part
of the question in one place each. It is not a list of paths typed into this
file, and it is not parsed out of the Dockerfile — the Dockerfile is `COPY . .`
and names no template, asset or module at all, so parsing it for the app's
runtime material would yield an empty requirement that passes against anything.
What the Dockerfile DOES name is the boot path (`/app/scripts/db_state.py`,
`requirements.txt`), and those it is parsed for. The four categories:

  * every `.html` in the tree (`_templates/`, the app packages, the shared
    partials under `_static/global/html/`);
  * every served file under `_static/`, with "served" decided by
    `prelaunch_check.IGNORED_NAMES` / `IGNORED_DIRS` — the asset guard's own
    definition, imported, not restated — and cross-checked against the file
    count `prelaunch_check.hash_static()` itself reports;
  * every `.py` outside `scripts/` (host-side tooling, which the image carries
    but does not render from);
  * every `/app/...` path the Dockerfile actually names.

Anything added to any of those is required to survive from the moment it exists,
with nobody remembering to update this file. See DECISIONS.md, "The build
context's must-survive list is derived from the source tree, never from the
ignore rules".

THE ONE DELIBERATE FRICTION: `SOURCE_PRUNE` below is DECLARED HERE and must
never be read from `.dockerignore`. If the requirement were derived from the
ignore rules, excluding a directory would delete the requirement that it
survive, and every widening would pass itself. So adding a new excluded
directory means a second edit, in this file, where a reviewer sees it. That
cost is the mechanism.

WHAT THIS IS NOT
================
It is not `docker build`. It computes the context the daemon WOULD receive,
using Docker's pattern semantics, and checks that. It cannot see a `COPY`
that lands in the wrong place, or anything that happens after the context is
sent. There is no image verifier in this template to defer that half to.

Run:  python3 scripts/tests/build_context_test.py
No server, no database, no browser, no oTree — filesystem plus one import of
the pre-launch guard. Exit 0 = both directions hold.
"""
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

# The asset guard is the single definition of "which files under _static/ are
# served"; scripts/ is where it lives.
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
import prelaunch_check as pc  # noqa: E402  (imports settings, prints the banner)

IGNORE_FILE = os.path.join(REPO_ROOT, '.dockerignore')

FAILURES = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        FAILURES.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


def human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f}{unit}' if unit != 'B' else f'{n}B'
        n /= 1024


# ---------------------------------------------------------------------------
# Docker's ignore matcher (moby/patternmatcher semantics)
# ---------------------------------------------------------------------------
def load_patterns(path):
    """The non-comment, non-blank entries of a .dockerignore, cleaned the way
    Docker cleans them: trailing slash stripped, leading `./` removed.

    A `#` only starts a comment at the START of a line — `data/  # snapshots`
    is a pattern for a directory whose name contains spaces and a hash, which
    is why the file's own header says so.
    """
    out = []
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            entry = line.strip()
            if not entry or entry.startswith('#'):
                continue
            entry = entry.rstrip('/')
            if entry.startswith('./'):
                entry = entry[2:]
            if entry:
                out.append(entry)
    return out


def compile_pattern(pattern):
    """One .dockerignore pattern as a regex, following moby's translation.

    The three behaviours that decide every assertion in this file:
      * `*` and `?` never cross a `/` — they are SEGMENT wildcards;
      * `**/` matches ZERO OR MORE segments, so `**/db.sqlite3` also matches a
        root-level `db.sqlite3`;
      * everything else is literal, and the pattern is anchored at the CONTEXT
        ROOT — which is what makes a pattern with no `/` match at the root only.
    """
    i, n, rx = 0, len(pattern), ''
    while i < n:
        ch = pattern[i]
        if ch == '*':
            if pattern[i:i + 2] == '**':
                i += 2
                if i < n and pattern[i] == '/':
                    i += 1
                    rx += '(?:[^/]*/)*'      # zero or more whole segments
                else:
                    rx += '.*'
            else:
                i += 1
                rx += '[^/]*'
        elif ch == '?':
            i += 1
            rx += '[^/]'
        elif ch == '/':
            i += 1
            rx += '/'
        else:
            j = i
            while j < n and pattern[j] not in '*?/':
                j += 1
            rx += re.escape(pattern[i:j])
            i = j
    return re.compile('(?s:' + rx + r')\Z')


def compile_all(patterns):
    return [compile_pattern(p) for p in patterns]


def excluded(rel, compiled):
    """Would `docker build` drop this context-relative path?

    Tested against the path AND every one of its parent prefixes, because a
    pattern that matches a directory takes its whole subtree with it.
    """
    parts = rel.split('/')
    prefixes = ['/'.join(parts[:k]) for k in range(1, len(parts) + 1)]
    for rx in compiled:
        for prefix in prefixes:
            if rx.match(prefix):
                return True
    return False


def build_context(root, patterns):
    """{relative path: size} for everything `docker build` would send."""
    compiled = compile_all(patterns)
    out = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = '' if rel_dir == '.' else rel_dir.replace(os.sep, '/')
        dirnames[:] = [d for d in dirnames
                       if not excluded(f'{rel_dir}/{d}'.lstrip('/'), compiled)]
        for name in filenames:
            rel = f'{rel_dir}/{name}'.lstrip('/')
            if excluded(rel, compiled):
                continue
            try:
                out[rel] = os.path.getsize(os.path.join(root, rel))
            except OSError:
                out[rel] = 0             # dangling symlink: nothing to leak
    return out


# ---------------------------------------------------------------------------
# THE CONTENT DETECTORS — a hazard is decided by bytes, not by a filename
# ---------------------------------------------------------------------------
SQLITE_MAGIC = b'SQLite format 3\x00'
OTREE_TABLE_MARKERS = (b'otree_participant', b'otree_session')
COOKIE_JAR_MARKERS = (b'# Netscape HTTP Cookie File',
                      b'# HTTP Cookie File')
# An oTree wide export's header row. `participant.code` is in every one of them
# and in nothing else this repo writes.
EXPORT_HEADER_MARKERS = (b'participant.code', b'participant.label',
                         b'participant._current_app_name')


def classify(path, head):
    """What kind of hazard is this file, judged from its first bytes?

    Returns a short label or None. Deliberately name-independent: `exports/`
    renamed to `analysis/`, `cookies.txt` saved as `jar`, or a snapshot called
    `db.sqlite3.old` are the same hazard, and a name check misses all three.
    """
    if head.startswith(SQLITE_MAGIC):
        return 'database'
    if any(head.startswith(m) for m in COOKIE_JAR_MARKERS):
        return 'cookie jar'
    # A CSV HEADER FIELD, not merely the words. `participant.code` appears as
    # prose in this repo's own docs and templates, and a substring test flagged
    # exactly that on the first run — so the marker has to be a whole
    # comma-separated field, which is what it is in an export and nowhere else.
    first_line = head.split(b'\n', 1)[0].strip()
    fields = [f.strip().strip(b'"') for f in first_line.split(b',')]
    if len(fields) > 1 and any(f in EXPORT_HEADER_MARKERS for f in fields):
        return 'participant data export'
    return None


def scan_for_hazards(root, context):
    """[(rel, label, detail)] for every file in `context` that carries one."""
    found = []
    for rel in sorted(context):
        path = os.path.join(root, rel)
        try:
            with open(path, 'rb') as fh:
                head = fh.read(8192)
        except OSError:
            continue
        label = classify(path, head)
        if not label:
            continue
        detail = ''
        if label == 'database':
            # Which database: an oTree study's, or some unrelated sqlite file?
            # Both are hazards in an image; only one of them is participants.
            try:
                with open(path, 'rb') as fh:
                    body = fh.read(8 * 1024 * 1024)
                if any(m in body for m in OTREE_TABLE_MARKERS):
                    detail = ' (holds oTree participant tables)'
            except OSError:
                pass
        found.append((rel, label, detail))
    return found


# ---------------------------------------------------------------------------
# WHAT THE APP RENDERS FROM — derived, never retyped
# ---------------------------------------------------------------------------
# DECLARED HERE ON PURPOSE, AND NEVER READ FROM .dockerignore. These directory
# names hold nothing the served application renders from: version control, a
# host-built virtualenv, agent working notes, regenerable preview output,
# byte-code caches, and the two directories the study's own data lands in
# (`data/` from the container's database volume, `exports/` from
# scripts/export_data.py). Deriving this from the ignore rules instead would
# make every widening self-approving: exclude `_templates/` and the requirement
# that `_templates/` survive disappears with it.
SOURCE_PRUNE = {
    '.git', '.venv', '.venv-linux', '.venv-run', '_ai', 'previews',
    '__pycache__', 'data', 'exports', 'node_modules', '.pytest_cache',
}


def walk_source(root, suffix=None, under=None):
    """Every file in the source tree, pruned by SOURCE_PRUNE."""
    base = os.path.join(root, under) if under else root
    out = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SOURCE_PRUNE]
        for name in filenames:
            if suffix and not name.endswith(suffix):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            out.append(rel.replace(os.sep, '/'))
    return sorted(out)


def must_survive_html(root):
    """Every template the app can render. `_templates/`, the app packages and
    the shared partials under `_static/global/html/` all hold `.html` the
    server reads at request time, so the category is the file extension rather
    than a list of directories that would go stale the moment one is added."""
    return walk_source(root, suffix='.html')


def must_survive_static(root):
    """Every SERVED file under `_static/`, with `served` decided by the asset
    guard's own constants rather than a second opinion about `.DS_Store`."""
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, '_static')):
        dirnames[:] = [d for d in dirnames if d not in pc.IGNORED_DIRS]
        for name in filenames:
            if name in pc.IGNORED_NAMES:
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            out.append(rel.replace(os.sep, '/'))
    return sorted(out)


def must_survive_python(root):
    """Every `.py` the served app can import. `scripts/` is excluded because it
    is host-side tooling — it ships, but nothing a participant reaches renders
    from it, and the boot path's own scripts are recovered from the Dockerfile
    below instead of being assumed."""
    return [p for p in walk_source(root, suffix='.py')
            if not p.startswith('scripts/')]


DOCKERFILE_PATH_RE = re.compile(r'/app/([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)')


def must_survive_boot(root):
    """The paths the Dockerfile itself names — the boot path, parsed rather
    than remembered. `CMD` runs `python3 /app/scripts/db_state.py`, and a
    `.dockerignore` that dropped it would produce an image that refuses to
    boot at all, which is the loud failure; the quiet one is `requirements.txt`,
    whose `RUN if [ -f ... ]` silently installs nothing when it is missing."""
    src = open(os.path.join(root, 'Dockerfile'), encoding='utf-8').read()
    named = {m for m in DOCKERFILE_PATH_RE.findall(src)}
    # Everything under /app is the context root; a bare `requirements.txt` is
    # referenced relative to WORKDIR.
    if 'requirements.txt' in src and os.path.exists(
            os.path.join(root, 'requirements.txt')):
        named.add('requirements.txt')
    # /app/data/db.sqlite3 is CREATED at boot, not shipped — it is the one
    # /app path in the Dockerfile that must NOT be in the context, and the
    # header comment there says so.
    return sorted(p for p in named
                  if not p.startswith('data/') and p != 'db.sqlite3'
                  and os.path.exists(os.path.join(root, p)))


def missing_from(required, context):
    return [p for p in required if p not in context]


# ---------------------------------------------------------------------------
def main():
    root = REPO_ROOT
    print(f'repo root: {root}')

    # ------------------------------------------------------------------
    section('A. the rules parse, and carry the entries they must')
    patterns = load_patterns(IGNORE_FILE)
    check(bool(patterns), f'.dockerignore parses to {len(patterns)} rule(s)')

    # A negated pattern would make every "excluded" verdict below wrong in a
    # way this matcher cannot see. Fail loudly on the shape it cannot model
    # rather than quietly mis-modelling it (CLAUDE.md: cannot-do and
    # drifted are different answers, and only one of them may be quiet).
    check(not [p for p in patterns if p.startswith('!')],
          'no `!` re-include rules — this matcher does not model them, and a '
          'silent wrong answer here would invalidate every check below')

    REQUIRED_RULES = {
        'data': 'database snapshots and the container volume mount point',
        'exports': 'scripts/export_data.py writes participant CSVs here',
        'db.sqlite3': 'the development database',
        '**/db.sqlite3': 'and any nested copy of it',
        '_ai': 'agent working notes, screenshots and pilot snapshots',
        '.venv': 'a host-built virtualenv, wrong platform and huge',
        'previews': 'regenerable instruction previews',
        '.env': 'secrets',
        '*.log': 'logs',
        '.git': 'the whole history, including anything ever committed',
        '**/__pycache__': 'nested byte-code caches',
    }
    for rule, why in REQUIRED_RULES.items():
        check(rule in patterns, f'{rule!r} is excluded — {why}')

    # The cookie-jar rules are a PATTERN, not a filename: the exp_pilots jar
    # was tracked in git holding a live admin session cookie, and the next one
    # will not be called cookies.txt.
    cookie_rules = [p for p in patterns if 'cookie' in p.lower()]
    check(len(cookie_rules) >= 2,
          f'cookie jars are excluded BY PATTERN, root and nested ({cookie_rules})')

    # Not widened past what the image needs: scripts/ ships (the boot path is
    # in it) and so do the docs a forked study reads.
    for kept in ('scripts', 'docs', '_templates', '_static'):
        check(kept not in patterns,
              f'{kept!r} is deliberately NOT excluded')

    # THE ONE FILE THAT IS GITIGNORED AND MUST NOT BE DOCKERIGNORED. The deploy
    # stamp is gitignored because a commit cannot contain its own SHA, and it is
    # written INTO the build context at deploy time so the image carries it. The
    # header of .dockerignore says "when you add a line to .gitignore, add it
    # here too", which is right about every other line and catastrophic about
    # this one — and silently so: the build succeeds, the container boots, every
    # page renders, and every deployed build reports itself unstamped forever.
    # Checked through the MATCHER rather than the pattern list, because a `*.json`
    # or a `BUILD_*` added for some other reason would do it just as well.
    check(not excluded('BUILD_INFO.json', compile_all(patterns)),
          'BUILD_INFO.json is NOT excluded — the deploy stamp has to reach the '
          'image, and dropping it fails nothing and reports unstamped forever')

    # ------------------------------------------------------------------
    section('B. the matcher is Docker\'s matcher — semantics, self-tested')
    # Every verdict in this file rests on these being right. They are the
    # semantics that actually bite, and they read like bugs if you assume the
    # friendlier .gitignore reading.
    CASES = [
        # (patterns, path, excluded?, why)
        (['__pycache__'], '__pycache__/x.pyc', True,
         'a no-slash pattern matches at the CONTEXT ROOT'),
        (['__pycache__'], 'intro/__pycache__/x.pyc', False,
         '...and NOT nested — the real Docker gotcha, which is why this file '
         'spells the nested cases `**/`'),
        (['**/__pycache__'], 'intro/__pycache__/x.pyc', True,
         '`**/` reaches a nested directory'),
        (['**/db.sqlite3'], 'db.sqlite3', True,
         '`**/` matches ZERO segments too, so it also covers the root'),
        (['*.log'], 'a/b.log', False,
         '`*` does not cross `/`'),
        (['**/*.log'], 'a/b.log', True,
         '...and `**/*.log` does'),
        (['data'], 'data/live/db.sqlite3', True,
         'a directory pattern takes its whole subtree'),
        (['data'], 'database.py', False,
         '...and does not match a longer name that starts the same way'),
        (['.env'], '.envrc', False,
         '`.env` is not a prefix match'),
        (['*.command'], 'GitHub_sync.command', True,
         'the host-side launchers go'),
    ]
    for pats, path, want, why in CASES:
        got = excluded(path, compile_all(pats))
        check(got == want,
              f'{pats} vs {path!r} -> {"excluded" if got else "kept"} — {why}')

    # ------------------------------------------------------------------
    section('F. context size, measured over this tree, right now')
    # NO rules at all is the honest baseline: it is exactly what a study that
    # deleted .dockerignore, or added a directory without thinking, would send.
    bare = build_context(root, [])
    real = build_context(root, patterns)
    b_bytes, r_bytes = sum(bare.values()), sum(real.values())
    print(f'  no rules : {len(bare):>6} files, {human(b_bytes)}')
    print(f'  shipped  : {len(real):>6} files, {human(r_bytes)}')
    print(f'  excluded : {len(bare) - len(real):>6} files, '
          f'{human(b_bytes - r_bytes)} '
          f'({100 * (b_bytes - r_bytes) / max(b_bytes, 1):.0f}% smaller)')
    check(r_bytes < b_bytes,
          f'the rules actually remove something ({human(b_bytes)} -> '
          f'{human(r_bytes)})')

    # ------------------------------------------------------------------
    section('C. WHAT LEFT — by path')
    for prefix, exists_now in (('_ai/', True), ('data/', False),
                               ('exports/', False), ('previews/', True),
                               ('.venv/', True), ('.git/', True)):
        present = [p for p in bare if p.startswith(prefix)]
        leaked = [p for p in real if p.startswith(prefix)]
        if present:
            check(not leaked,
                  f'{prefix} exists here ({len(present)} files) and NONE of it '
                  f'reaches the context ({len(leaked)} leaked)')
        else:
            # A hazard directory that does not exist yet satisfies the
            # requirement more strongly than exclusion does — but only because
            # section A asserted the RULE independently, so the exclusion
            # cannot quietly be dropped on the grounds that the directory
            # happens to be absent today.
            check(not leaked,
                  f'{prefix} does not exist in this checkout — the rule in A is '
                  f'what covers it the day it does')
    for name in ('db.sqlite3', '.DS_Store'):
        check(name in bare and name not in real,
              f'{name} is present in the tree and absent from the context')

    section('C. WHAT LEFT — by CONTENT, which is the claim that matters')
    hazards = scan_for_hazards(root, real)
    check(not hazards,
          f'no file in the build context is a database, a cookie jar or a '
          f'participant data export ({hazards})')

    # ------------------------------------------------------------------
    section('D. WHAT STAYED — everything the app renders from')
    html = must_survive_html(root)
    check(len(html) >= 10,
          f'{len(html)} template(s) found in the source tree — a derivation '
          f'that found nothing would pass vacuously')
    check(not missing_from(html, real),
          f'every .html survives the context '
          f'(missing: {missing_from(html, real)})')
    # The 2026-08-11 failure mode was not "a template is missing", it was "a
    # template DIRECTORY arrived empty", which is a different shape and worth
    # its own assertion.
    empty_dirs = []
    for d in sorted({os.path.dirname(p) for p in html}):
        if not any(p.startswith(d + '/') and p.count('/') == d.count('/') + 1
                   for p in real if p.endswith('.html')):
            empty_dirs.append(d)
    check(not empty_dirs,
          f'no template directory arrives EMPTY — the 2026-08-11 failure mode '
          f'({empty_dirs})')

    static = must_survive_static(root)
    guard_digest, guard_count = pc.hash_static()
    check(len(static) == guard_count,
          f'the served-asset derivation agrees with the asset guard itself '
          f'({len(static)} vs prelaunch_check.hash_static() = {guard_count})')
    check(not missing_from(static, real),
          f'every served file under _static/ survives the context '
          f'(missing: {missing_from(static, real)})')

    mods = must_survive_python(root)
    check(len(mods) >= 5, f'{len(mods)} app module(s) found')
    check(not missing_from(mods, real),
          f'every app python module survives the context '
          f'(missing: {missing_from(mods, real)})')

    boot = must_survive_boot(root)
    check(bool(boot),
          f'the Dockerfile names {len(boot)} runtime path(s): {boot}')
    check(not missing_from(boot, real),
          f'every path the Dockerfile names survives the context '
          f'(missing: {missing_from(boot, real)})')

    # ------------------------------------------------------------------
    section('E. THE GUARD FIRES — each absence above, demonstrated red')
    # E1: with no rules at all, the hazard scan must find the development
    # database. Without this, section C is indistinguishable from a scanner
    # that never returns anything.
    bare_hazards = scan_for_hazards(root, bare)
    check(any(h[1] == 'database' for h in bare_hazards),
          f'with NO ignore rules the content scan finds the database '
          f'({[h[0] for h in bare_hazards if h[1] == "database"]}) — so a clean '
          f'result above is a fact about the rules, not about the scanner')

    # E2: the content detectors, each against a file that is only a hazard by
    # its bytes, and each against a file that must NOT be flagged. Written to a
    # temp directory outside the repo, so the test cannot leave a hazard behind.
    with tempfile.TemporaryDirectory() as tmp:
        fixtures = [
            ('snapshot.bin', SQLITE_MAGIC + b'\x00' * 64, 'database',
             'a database renamed to hide its extension'),
            ('jar', b'# Netscape HTTP Cookie File\n.example\tTRUE\t/\t...',
             'cookie jar', 'a cookie jar with no `cookie` in its name'),
            ('analysis.csv',
             b'participant.code,participant.label,participant.payoff\nabc,P1,5\n',
             'participant data export', 'an export renamed away from exports/'),
            ('welcome.html', b'<html><p>participant.code is just prose</p>',
             None, 'ordinary markup mentioning the same words'),
            ('common.py', b'# otree_participant is named in a comment\n',
             None, 'a module mentioning an oTree table name'),
        ]
        for name, body, want, why in fixtures:
            p = os.path.join(tmp, name)
            with open(p, 'wb') as fh:
                fh.write(body)
            got = classify(p, body[:8192])
            check(got == want,
                  f'detector: {why} -> {got!r} (expected {want!r})')

    # E3: an over-broad rule set must break section D. This is the direction
    # nobody checks — the one that ships an empty _templates and 500s a live
    # page — so it is proved to be catchable rather than assumed.
    for extra, label in ((['_templates'], 'a template directory'),
                         (['**/*.html'], 'every template, nested spelling'),
                         (['_static/global/css'], 'the stylesheets'),
                         (['common.py'], 'one root module'),
                         (['scripts/db_state.py'], 'the boot-path script')):
        broken = build_context(root, patterns + extra)
        still_ok = (not missing_from(html, broken)
                    and not missing_from(static, broken)
                    and not missing_from(mods, broken)
                    and not missing_from(boot, broken))
        check(not still_ok,
              f'excluding {label} ({extra[0]!r}) makes section D FAIL — '
              f'the must-survive list is not derived from the ignore rules')

    # ------------------------------------------------------------------
    print(f'\n{"FAILED: " + str(len(FAILURES)) + " check(s)" if FAILURES else "ALL CHECKS PASSED"}')
    for f in FAILURES:
        print(f'  - {f}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
