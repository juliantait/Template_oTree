#!/usr/bin/env python3
"""Machine-checked PRE-LAUNCH guard, as a standalone command (exit code aware).

`settings.py` prints the same banner on every server start, but that is
advisory. Run THIS in CI or a launcher to get a non-zero exit when anything is
still a testing/placeholder value, so a bad launch can be blocked automatically.

Run it in the SAME environment you will launch in (it reads OTREE_PRODUCTION,
etc.):

    OTREE_PRODUCTION=1 python scripts/prelaunch_check.py

It also enforces the ASSET-VERSION BUMP (see below):

    python scripts/prelaunch_check.py --stamp-assets   # after changing _static/

NOTHING HERE RUNS AT BOOT. The asset hashing lives in this script alone, never
in `settings._prelaunch_problems()` — that function IS called at import, and
hashing every file under `_static/` on every server start would be a real cost
for a check that belongs to a deploy, not to a page render. The stored manifest
is inert data: no app code reads it, no participant-facing behaviour depends on
it, and deleting it changes nothing except that this check starts failing.
"""
import hashlib
import json
import os
import sys

# Make the project root importable when run from anywhere.
# The repo root comes from the ONE marker-walking helper, never a level
# count (see scripts/tests/_repo.py for what that cost on 2026-08-16).
# `tests` is a CHILD of this directory, so this reference says nothing
# about how deep scripts/ itself sits.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
from _repo import REPO_ROOT  # noqa: E402

_ROOT = REPO_ROOT
sys.path.insert(0, _ROOT)

import settings  # noqa: E402  (importing prints the banner)

STATIC_DIR = os.path.join(_ROOT, '_static')
MANIFEST = os.path.join(_ROOT, 'scripts', 'asset_manifest.json')

# Files under _static/ that are not served to a participant and must not make
# the hash churn. Everything else counts — CSS, JS, HTML partials AND images:
# an image swapped without a version bump is served stale from cache exactly
# like a stylesheet.
IGNORED_NAMES = {'.DS_Store', 'Thumbs.db'}
IGNORED_DIRS = {'__pycache__'}


def hash_static():
    """One sha256 over every served file under _static/, path-sensitive.

    The path goes into the digest as well as the bytes, so a RENAME (which
    changes what a template must link to) is a change even when the content is
    identical. Sorted, so the digest does not depend on filesystem order.
    """
    digest = hashlib.sha256()
    files = []
    for dirpath, dirnames, filenames in os.walk(STATIC_DIR):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            if name in IGNORED_NAMES:
                continue
            files.append(os.path.join(dirpath, name))
    for path in sorted(files):
        rel = os.path.relpath(path, _ROOT).replace(os.sep, '/')
        digest.update(rel.encode('utf-8'))
        digest.update(b'\0')
        with open(path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(65536), b''):
                digest.update(chunk)
    return digest.hexdigest(), len(files)


def read_manifest():
    try:
        with open(MANIFEST) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def stamp_assets():
    """Record the current asset hash against the current STATIC_VERSION."""
    digest, count = hash_static()
    payload = {
        '_comment': (
            'Written by scripts/prelaunch_check.py --stamp-assets. It records '
            'the sha256 of everything under _static/ against the '
            'settings.STATIC_VERSION that was current when the assets last '
            'changed, so the pre-launch check can fail when the files change '
            'and the cache-buster does not. Inert data: nothing at runtime '
            'reads it.'),
        'static_version': str(settings.STATIC_VERSION),
        'static_sha256': digest,
        'file_count': count,
    }
    with open(MANIFEST, 'w') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write('\n')
    print(f"stamped {os.path.relpath(MANIFEST, _ROOT)}: "
          f"STATIC_VERSION={payload['static_version']} "
          f"sha256={digest[:16]}… ({count} files)")
    return 0


def asset_problems():
    """(label, current, must_be) for a stale cache-buster. Same shape as settings'.

    THE RULE. `STATIC_VERSION` is appended to every CSS/JS URL, so a redeploy
    whose assets changed but whose version did not is served to participants
    out of cache — the change simply does not appear, and there is no error
    anywhere to notice. This turns "remember to bump N" into something a gate
    enforces:

      * files identical to the stamp  -> OK, whatever the version says;
      * files changed, version NOT bumped -> FAIL (the actual bug);
      * files changed, version bumped but not re-stamped -> FAIL, because
        leaving a stale manifest silently disables this check for the NEXT
        change. The fix is one command, and it is named in the message.
    """
    version = str(settings.STATIC_VERSION)
    stored = read_manifest()
    if stored is None:
        return [('asset manifest (scripts/asset_manifest.json)', 'missing',
                 'created by running: python scripts/prelaunch_check.py '
                 '--stamp-assets')]
    digest, _ = hash_static()
    if digest == stored.get('static_sha256'):
        return []
    if version == str(stored.get('static_version')):
        return [(f"settings.STATIC_VERSION (files under _static/ changed)",
                 version,
                 'bumped, then recorded with: python scripts/prelaunch_check.py '
                 '--stamp-assets  (a redeploy on the same version serves the '
                 'OLD css/js from cache)')]
    return [('asset manifest (STATIC_VERSION was bumped, hash not re-recorded)',
             f"{stored.get('static_version')} -> {version}",
             're-recorded with: python scripts/prelaunch_check.py '
             '--stamp-assets')]


def lab_module_problems():
    """(label, current, must_be) for an integrity module turned on in a lab config.

    THE INTEGRITY MODULES ARE NOT SUPPORTED IN A LAB SESSION (Julian,
    2026-08-12). The reason is conceptual: in the lab a participant who does not
    consent, or does not pass the comprehension check, simply cannot do the
    study — and that essentially never happens, because people know what they
    signed up for when they come to the lab. Disqualification has nothing to
    accomplish that the experimenter in the room does not already handle; the
    lab's comprehension rule is the re-read pass plus the "raise your hand"
    notice (see `comprehension_max_failures` in settings.py).

    This is a FAILURE rather than a comment because of the mechanical
    consequence: a disqualified participant is not a completer
    (`outro.is_completer`), so they skip Demographics — which collects the lab's
    IBAN/BIC — and the payment summary, and land on an ending page with no
    redirect, since a lab session has no completion codes. Catching that here
    means catching it before launch instead of when someone is stranded at a
    machine with no record of where to send their fee.

    Deliberately in this script and not in `settings._prelaunch_problems()`:
    the banner there is advisory and prints on every dev boot, and a lab config
    that deliberately exercises a module while it is being worked on should not
    scream at every start — but it must never reach a launch.
    """
    problems = []
    for cfg in settings.SESSION_CONFIGS:
        # The EFFECTIVE config: profiles are resolved at import, but a module
        # flag can also come from SESSION_CONFIG_DEFAULTS.
        eff = {**settings.SESSION_CONFIG_DEFAULTS, **cfg}
        if eff.get('recruitment') != 'lab':
            continue
        for flag in ('comprehension_dq', 'tab_monitor'):
            if eff.get(flag):
                problems.append(
                    (f"config {cfg['name']!r} {flag} (lab session)", True,
                     'False — the integrity modules are not supported in the '
                     'lab: a disqualified participant skips bank details and '
                     'the payment summary and is stranded at the machine'))
    return problems


def auth_level_problems():
    """(label, current, must_be) when the admin is not locked down.

    `OTREE_AUTH_LEVEL` decides whether oTree's admin needs a login at all:
    unset means NO LOGIN on anything under the admin, which is the right default
    for local development and completely wrong for a launch. oTree reads it from
    the environment at import (`otree/settings.py`: `AUTH_LEVEL =
    os.environ.get('OTREE_AUTH_LEVEL')`), so this script has to read the
    environment too — run it in the one you will launch in, like the rest of
    these checks.

    WHY THIS IS A LAUNCH BLOCKER AND NOT A COMMENT. The admin is not just the
    session-creation screen: the data exports are there, oTree's own monitor is
    there, and since 2026-08-12 so is the experimenter dashboard
    (`experimenter_dashboard.py`), which puts every participant's earnings and
    conduct — screen-outs, comprehension failures, tab-monitor disqualifications
    — on one page. That page reuses oTree's login rather than inventing its own,
    which is the right design and also means its security is EXACTLY this
    environment variable. Unset it and the page is open to anyone who can reach
    the port. It belongs in the same guard as the placeholder completion codes
    for the same reason: it is a one-line configuration mistake that nothing at
    run time will complain about.

    'STUDY' rather than 'DEMO': DEMO leaves oTree's own SessionMonitor open.
    """
    level = os.environ.get('OTREE_AUTH_LEVEL')
    if level == 'STUDY':
        return []
    return [('OTREE_AUTH_LEVEL (admin login, and with it the data exports and '
             'the experimenter dashboard)',
             level if level is not None else 'unset — NO LOGIN REQUIRED',
             "'STUDY', set in the launch environment: without it the admin, "
             'the exports and the experimenter dashboard (earnings and '
             'per-participant conduct) are open to anyone who can reach the '
             'port')]


def dashboard_problems():
    """(label, current, must_be) for a broken experimenter dashboard.

    THE LAUNCH HALF OF THE 2026-08-17 FIX (the runtime half is the widened
    `except` in outro.vars_for_admin_report; see DECISIONS.md). The empirical
    blast-radius study (`_ai/dashboard_blast_radius.md`) found a drift that
    BOOTS CLEAN and then 500s oTree's own admin Report tab the first time an
    operator clicks it mid-session: URL_BASE renamed consistently INSIDE
    experimenter_dashboard.py while the cross-file read in
    outro.vars_for_admin_report is missed. A boot-time banner cannot catch it
    because the boot succeeds; only a click three hours into a session does.
    This guard turns that click into a launch-blocking failure, while somebody
    can still fix the rename.

    FOUR CHECKS, each REPORTED as a normal prelaunch problem (never raised, the
    idiom of every function above): the module imports; URL_BASE exists and is
    a path (the drift's root cause — catches the rename even though the runtime
    fix now falls back rather than 500ing); vars_for_admin_report returns a
    plausible URL without raising (oTree calls it UNGUARDED); and the routes
    actually install. Importing `outro` here runs the same boot-time install a
    real server would, so the route check sees the real outcome.

    Deliberately in THIS script, not in settings._prelaunch_problems(): that
    banner is advisory and prints on every dev boot, and importing the app to
    build the route table is a deploy-time cost, not a per-render one — the
    same reasoning that keeps the asset hashing here.
    """
    import types
    LABEL = 'experimenter dashboard'
    problems = []

    try:
        import experimenter_dashboard as ed
    except Exception as exc:
        # The module both the standalone dashboard and the Report tab read is
        # broken at import — nothing else here can be checked.
        return [(f'{LABEL} (import experimenter_dashboard)',
                 f'{type(exc).__name__}: {exc}',
                 'importable — the dashboard module fails at import, which '
                 'takes the whole boot down (it is imported unguarded at the '
                 'end of outro/__init__.py)')]

    base = getattr(ed, 'URL_BASE', None)
    if not (isinstance(base, str) and base.startswith('/')):
        problems.append(
            (f'{LABEL} (experimenter_dashboard.URL_BASE)', repr(base),
             "a URL path like '/experimenter_dashboard' — the Report tab and "
             'the routes both read this constant, so a rename that misses a '
             'cross-file reader boots clean and then 500s the admin Report tab '
             'mid-session (blast-radius scenario 4)'))

    try:
        import outro
        probe = types.SimpleNamespace(
            session=types.SimpleNamespace(code='PRELAUNCH_PROBE'))
        url = outro.vars_for_admin_report(probe).get('dashboard_url')
        if not (isinstance(url, str) and url.startswith('/')
                and 'PRELAUNCH_PROBE' in url):
            problems.append(
                (f'{LABEL} (outro.vars_for_admin_report dashboard_url)',
                 repr(url),
                 'a URL path ending in the session code — the admin Report tab '
                 'embeds this value; a blank or malformed one leaves the tab '
                 'with no working dashboard link'))
    except Exception as exc:
        problems.append(
            (f'{LABEL} (outro.vars_for_admin_report raised)',
             f'{type(exc).__name__}: {exc}',
             'a dict without raising — oTree calls it UNGUARDED, so any raise '
             "500s the admin Report tab an operator may click mid-session"))

    try:
        outcome = ed.install_dashboard_route()
        if not ed.dashboard_is_installed():
            problems.append(
                (f'{LABEL} (routes in otree.urls.routes)',
                 f'not installed (install_dashboard_route returned {outcome!r})',
                 'installed — the /experimenter_dashboard routes are absent, so '
                 'the operator dashboard 404s'))
    except Exception as exc:
        problems.append(
            (f'{LABEL} (install_dashboard_route)', f'{type(exc).__name__}: {exc}',
             'a clean install — the route builder raised (version drift), so '
             'the dashboard will not be reachable'))

    return problems


def main(argv):
    if '--stamp-assets' in argv:
        return stamp_assets()

    problems = (settings._prelaunch_problems() + lab_module_problems()
                + asset_problems() + auth_level_problems()
                + dashboard_problems())
    if not problems:
        print("PRE-LAUNCH OK — no testing/placeholder values detected, "
              "and the asset version matches the files under _static/.")
        return 0
    print("PRE-LAUNCH FAILED — fix these before launching:")
    for label, current, must_be in problems:
        print(f"  {label}: currently {current!r}, MUST BE {must_be}")
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
