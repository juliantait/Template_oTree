#!/usr/bin/env python
"""BUILD PROVENANCE — it records what ran, and it can never break anything.

    python scripts/tests/build_provenance_test.py

WHAT THIS PINS
--------------
Build provenance is DOCUMENTATION, NEVER A GATE (DECISIONS.md, 2026-08-23). Two
claims follow from that, and each needs its own evidence:

  A. **A build with no stamp behaves EXACTLY like one with a stamp**, except in
     what it records. No raise, no 5xx, no refusal, no changed page — this is
     the state of every local run and every other test in this folder, so if it
     were broken the whole suite would be measuring a study nobody can run.
  B. **A stamped build actually records the stamp**, in the three places, with
     the right values. A degradation path that always degrades is a feature
     that never works, and it would look identical from inside claim A. This is
     the "wiring can be verified, a silent refusal to run cannot" rule from
     CLAUDE.md applied to provenance: the only proof is a record ARRIVING.

WHY IT RUNS ITSELF THREE TIMES
------------------------------
`buildinfo.BUILD_INFO` is read ONCE at import, and `settings.py` bakes the
config stamp and the `doc` line at import too. Which build a process thinks it
is running is therefore fixed before the first test line executes, and no
monkeypatch can honestly simulate the other case — patching the module constant
after import would leave `SESSION_CONFIG_DEFAULTS['build_at_creation']` and
every config `doc` still holding the first answer, i.e. it would test a state no
real deployment can be in. So this file re-execs ITSELF as two subprocesses,
each booting oTree for real:

    (parent)              pure functions: load / label / doc_html / the writer
    --inprocess-stamped   BUILD_INFO_PATH -> a fixture stamp, then boot
    --inprocess-unstamped BUILD_INFO_PATH -> a path with no file, then boot

Both children walk a real participant over the in-process HTTP client, because
the stamp is taken on a real page GET (`intro.instructing`) and calling the
function directly would prove only that the function works.

NOTE the fresh client per arrival (see treatment_assignment_test.py): oTree's
room pins one browser to one participant with a cookie, so a shared client
re-enters the same participant.
"""
import json
import os
import subprocess
import sys
import tempfile

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _TESTS_DIR)

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# A stamp that is obviously synthetic but structurally real: a 40-char hex SHA,
# a build number, and a commit subject carrying an XSS payload, because the
# subject is free text somebody typed into a commit message OUTSIDE this repo
# and it reaches an admin page through an UNESCAPED `doc`.
FIXTURE_SHA = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
FIXTURE_NUMBER = 214
HOSTILE_SUBJECT = 'fix <script>alert(1)</script> & "quotes"'


def write_fixture(path, **overrides):
    """Write a stamp through the REAL writer, so the test cannot pass against a
    hand-rolled file the writer would never produce."""
    sys.path.insert(0, os.path.dirname(_TESTS_DIR))     # scripts/
    from write_build_info import write_build_info
    values = dict(commit=FIXTURE_SHA, commit_date='2026-08-23T10:00:00+00:00',
                  subject=HOSTILE_SUBJECT, build_number=FIXTURE_NUMBER,
                  built_at='2026-08-23T10:05:00+00:00', tree_clean=True)
    values.update(overrides)
    return write_build_info(path, **values)


# ===========================================================================
# THE PURE LEG — the reader, the writer, and the doc string
# ===========================================================================

def pure_leg(tmp):
    sys.path.insert(0, os.path.dirname(_TESTS_DIR))     # scripts/
    from _repo import REPO_ROOT                          # noqa: F401
    import buildinfo
    import write_build_info as writer

    section('The reader degrades to UNSTAMPED for every failure mode, and '
            'NEVER raises')
    # Each of these is a real state a half-finished or hand-built deploy
    # reaches. The assertion is a PAIR every time: unstamped AND a problem
    # string that names which failure it was — "unstamped" alone would pass
    # against a reader that always says unstamped, which is the failure this
    # whole file exists to distinguish from working degradation.
    cases = []
    missing = os.path.join(tmp, 'nothing-here.json')
    cases.append(('absent', missing, 'no BUILD_INFO.json'))
    for name, body, expect in [
        ('not JSON', '{ this is not json', 'not valid JSON'),
        ('a JSON list', '[1, 2, 3]', 'not a JSON object'),
        ('a JSON string', '"a1b2c3"', 'not a JSON object'),
        ('no commit key', '{"build_number": 3}', 'is not a 40-character'),
        ('a SHORT sha', '{"commit": "a1b2c3d"}', 'is not a 40-character'),
        ('a non-hex sha', '{"commit": "' + 'z' * 40 + '"}',
         'is not a 40-character'),
        ('an empty file', '', 'not valid JSON'),
    ]:
        p = os.path.join(tmp, f'stamp-{abs(hash(name))}.json')
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(body)
        cases.append((name, p, expect))
    for name, path, expect in cases:
        try:
            info = buildinfo.load(path)
            raised = None
        except Exception as exc:                              # noqa: BLE001
            info, raised = None, exc
        if not check(raised is None,
                     f'{name}: load() did not raise (got {raised!r})'):
            continue
        check(info['stamped'] is False, f'{name}: reports stamped=False')
        check(expect in (info['problem'] or ''),
              f'{name}: the problem NAMES the failure '
              f'({(info["problem"] or "")[:70]!r})')
        check(info['commit'] is None and info['build_number'] is None,
              f'{name}: carries no commit and no build number')
        check(buildinfo.label(info) == 'unstamped build',
              f'{name}: label() is the honest phrase, not a fake SHA')

    section('A REAL stamp reads back exactly, through the real writer')
    good = os.path.join(tmp, 'BUILD_INFO.json')
    written = write_fixture(good)
    check(written['commit_short'] == FIXTURE_SHA[:7],
          f'the writer derives the short SHA ({written["commit_short"]})')
    info = buildinfo.load(good)
    check(info['stamped'] is True, 'the reader says stamped=True')
    check(info['commit'] == FIXTURE_SHA,
          f'the full SHA round-trips ({info["commit"][:12]}…)')
    check(info['build_number'] == FIXTURE_NUMBER,
          f'the build number round-trips ({info["build_number"]})')
    check(info['problem'] is None,
          f'a complete stamp reports no problem (got {info["problem"]!r})')
    check(buildinfo.label(info) == f'build {FIXTURE_NUMBER} · {FIXTURE_SHA[:7]}',
          f'label() leads with the number a human says out loud '
          f'({buildinfo.label(info)!r})')
    check(os.path.exists(good) and not os.path.exists(good + '.tmp'),
          'the write was atomic: no .tmp left behind')

    section('An INCOMPLETE stamp is still stamped — the SHA is the identity')
    partial = os.path.join(tmp, 'partial.json')
    with open(partial, 'w', encoding='utf-8') as fh:
        json.dump({'commit': FIXTURE_SHA}, fh)
    info = buildinfo.load(partial)
    check(info['stamped'] is True,
          'a bare SHA with every decoration missing is still a usable stamp')
    check('missing' in (info['problem'] or ''),
          f'and the gap is RECORDED rather than silently tolerated '
          f'({(info["problem"] or "")[:60]!r})')
    check(info['commit_short'] == FIXTURE_SHA[:7],
          'the short SHA is derived when the file does not carry one')

    section('The writer REFUSES a stamp that is not a real SHA')
    bad = os.path.join(tmp, 'never-written.json')
    rc = writer.main(['--commit', 'not-a-sha', '--build-number', '1',
                      '--out', bad])
    check(rc == 2, f'a bogus commit exits 2 (got {rc})')
    check(not os.path.exists(bad),
          'and writes NOTHING — no half-plausible stamp reaches the data')
    rc = writer.main(['--commit', FIXTURE_SHA, '--build-number',
                      str(FIXTURE_NUMBER), '--out', bad])
    check(rc == 0 and os.path.exists(bad),
          f'a real SHA is written and exits 0 (got {rc})')

    section('doc_html: the commit subject is ESCAPED, the markup survives')
    # The subject is the value that makes escaping mandatory rather than tidy —
    # free text from outside this repo, rendered by oTree as {{ config.doc|safe }}.
    doc = buildinfo.doc_html('', info=buildinfo.load(good))
    check('<script>alert(1)</script>' not in doc,
          'the raw <script> payload does not survive into the doc string')
    check('&lt;script&gt;' in doc,
          'it is present as escaped text, so the value is not silently dropped')
    check('&amp;' in doc and '&quot;' in doc,
          'the ampersand and the quotes are escaped too')
    check('<b>Running build:</b>' in doc,
          'the deliberate markup is still live HTML (the point of |safe)')
    check(f'build {FIXTURE_NUMBER}' in doc,
          'and the build a session would be created on is named')
    unstamped_doc = buildinfo.doc_html('', info=buildinfo.load(missing))
    check('unstamped' in unstamped_doc and unstamped_doc.strip() != '',
          'an unstamped build still renders a doc line, never an empty string '
          '(oTree hides an empty doc entirely)')
    check('never a gate' in unstamped_doc or 'blocks nothing' in unstamped_doc,
          'and it SAYS that unstamped blocks nothing, so nobody reads it as a '
          'fault to fix before launching')
    base = buildinfo.doc_html('A study description.', info=info)
    check(base.startswith('A study description.'),
          'a config that has its own doc keeps it — the build line APPENDS')

    section('config_stamp / normalise_config_stamp')
    stamp = buildinfo.config_stamp()
    check(isinstance(stamp, dict),
          'the frozen config value is a DICT — oTree makes every scalar config '
          'value an editable text box, and retypable provenance is not '
          'provenance')
    check(set(stamp) == {'commit', 'commit_short', 'build_number', 'built_at',
                         'stamped'},
          f'and always the same shape, stamped or not ({sorted(stamp)})')
    check(buildinfo.normalise_config_stamp(None) is None,
          'ABSENT normalises to None — "created before stamping existed" is a '
          'different fact from "created on an unstamped build"')
    older = buildinfo.normalise_config_stamp(FIXTURE_SHA)
    check(older and older['commit'] == FIXTURE_SHA,
          'a bare SHA (an older or hand-edited shape) is still read, not thrown '
          'away')
    check(buildinfo.normalise_config_stamp({'commit': 'nope'})['commit'] is None,
          'a dict carrying a non-SHA yields commit=None rather than a value '
          'nothing can resolve')


# ===========================================================================
# THE IN-PROCESS LEGS — a real participant, over real HTTP
# ===========================================================================

def inprocess_leg(stamped):
    """Boot oTree with (or without) a stamp and walk a real arrival."""
    import re
    from otree_inprocess import boot, page_name_of, path_of

    ot = boot(production=True)          # MUST come before any app import
    import buildinfo                    # noqa: E402
    import common                       # noqa: E402
    import settings                     # noqa: E402

    def csrf_of(html):
        m = re.search(r'name="csrftoken"[^>]*value="([^"]+)"', html) \
            or re.search(r'value="([^"]+)"[^>]*name="csrftoken"', html)
        return m.group(1) if m else ''

    def walk(session, target, steps=8):
        cl = ot.client()          # fresh client == fresh browser == new arrival
        r = cl.get(f'/join/{ot.anon_code(session)}', allow_redirects=True)
        statuses = [r.status_code]
        for _ in range(steps):
            if page_name_of(path_of(r)) == target:
                break
            r = cl.post(path_of(r), data=dict(csrftoken=csrf_of(r.text)),
                        allow_redirects=True)
            statuses.append(r.status_code)
        return r, statuses

    def code_of(resp):
        return path_of(resp).split('/')[2]

    word = 'STAMPED' if stamped else 'UNSTAMPED'
    section(f'{word}: what this process thinks it is running')
    check(buildinfo.BUILD_INFO['stamped'] is stamped,
          f'the running build reports stamped={stamped} '
          f'({buildinfo.label()})')
    if stamped:
        check(buildinfo.BUILD_INFO['commit'] == FIXTURE_SHA,
              'and it is the fixture stamp')

    section(f'{word}: the session config freezes build_at_creation')
    session = ot.create_session('lab', num_participants=4)
    frozen = dict(session.config)
    check('build_at_creation' in frozen,
          'a new session carries build_at_creation in its frozen config')
    at_creation = common.build_at_creation(frozen)
    check(at_creation is not None,
          'and common.build_at_creation reads it back')
    if stamped:
        check(at_creation['commit'] == FIXTURE_SHA,
              f'it names the build the session was created on '
              f'({(at_creation or {}).get("commit_short")})')
    else:
        check(at_creation['stamped'] is False and at_creation['commit'] is None,
              'on an unstamped build it is a VALUE saying so, not an absence '
              '— absence is reserved for "created before stamping existed"')

    section(f'{word}: participants are BLANK at creation, never pre-stamped')
    codes = ot.participant_codes(session)
    at_creation_vars = [ot.participant_vars(c) for c in codes]
    check(all(v.get('build_sha') == '' for v in at_creation_vars),
          f'every participant holds build_sha == "" at creation '
          f'(got {sorted({v.get("build_sha") for v in at_creation_vars})!r})')
    check(all(v.get('build_number') is None for v in at_creation_vars),
          'and build_number is None')
    check(all('build_sha' in v for v in at_creation_vars),
          'the field EXISTS on every row, so a bare read can never KeyError '
          'and no export row is missing the column')

    section(f'{word}: the stamp is taken ON ARRIVAL, on a real page GET')
    r, statuses = walk(session, 'instructing')
    check(page_name_of(path_of(r)) == 'instructing',
          f'the arrival reached the instructions page '
          f'(at {page_name_of(path_of(r))})')
    check(all(s < 500 for s in statuses),
          f'no 5xx on the way (max status {max(statuses)}) — provenance can '
          f'never cost a participant a page')
    arrived = ot.participant_vars(code_of(r))
    expected = FIXTURE_SHA if stamped else buildinfo.UNSTAMPED_SHA
    check(arrived.get('build_sha') == expected,
          f'the arrival is stamped {expected[:12]!r} '
          f'(got {str(arrived.get("build_sha"))[:12]!r})')
    if stamped:
        check(arrived.get('build_number') == FIXTURE_NUMBER,
              f'and carries the build number '
              f'({arrived.get("build_number")})')
    else:
        # The PAIRED presence: 'unstamped' is a real answer, not a blank, and it
        # must be distinguishable from the blank that means "never arrived".
        check(arrived.get('build_sha') != '',
              "an unstamped arrival records the WORD 'unstamped', which is a "
              'different fact from the blank of somebody who never arrived')
    check(arrived.get('treatment_group') in settings.TREATMENT_CELLS,
          f'the treatment cell was taken at the same moment '
          f'({arrived.get("treatment_group")!r}) — one arrival, both records')

    section(f'{word}: nobody who did not arrive is stamped')
    unwalked = [ot.participant_vars(c) for c in codes[1:]]
    check(all(v.get('build_sha') == '' for v in unwalked),
          f'the {len(unwalked)} participants who never arrived still hold "" '
          f'(got {sorted({v.get("build_sha") for v in unwalked})!r})')

    section(f'{word}: the stamp is WRITE-ONCE across a re-entry')
    # A participant who comes back after a redeploy must keep the build they
    # FIRST arrived on; re-stamping would rewrite history to the newest deploy
    # and destroy the divergence the field exists to record. Simulated by
    # planting a different SHA and re-entering.
    from otree.database import DBSession
    from otree.models import Participant
    planted = 'f' * 40
    s = DBSession()
    try:
        p = s.query(Participant).filter_by(code=code_of(r)).one()
        p.vars['build_sha'] = planted
        s.commit()
    finally:
        s.close()
    cl = ot.client()
    again = cl.get(f'/InitializeParticipant/{code_of(r)}', allow_redirects=True)
    check(again.status_code < 500,
          f're-entry did not 5xx (status {again.status_code})')
    check(ot.participant_vars(code_of(r)).get('build_sha') == planted,
          'the existing stamp survives a re-entry — write-once, so a refresh '
          'after a redeploy never rewrites which build they arrived on')

    section(f'{word}: the create-session screen names the running build')
    # `doc` is what an operator reads BEFORE creating a session, and oTree
    # renders it UNESCAPED. Assert both halves on the real shipped configs.
    for cfg in settings.SESSION_CONFIGS:
        doc = cfg.get('doc') or ''
        check('Running build:' in doc,
              f'config {cfg["name"]!r} carries the build line in its doc')
        check('<script>alert(1)</script>' not in doc,
              f'config {cfg["name"]!r} carries no unescaped script payload')
        if stamped:
            check(f'build {FIXTURE_NUMBER}' in doc,
                  f'config {cfg["name"]!r} names the running build')


# ===========================================================================

def _summary(title='SUMMARY'):
    section(title)
    if _failures:
        print(f'  {len(_failures)} CHECK(S) FAILED:')
        for f in _failures:
            print(f'    - {f}')
        return 1
    print('  ALL CHECKS PASSED')
    return 0


def main(argv):
    if '--inprocess-stamped' in argv:
        inprocess_leg(stamped=True)
        return _summary()
    if '--inprocess-unstamped' in argv:
        inprocess_leg(stamped=False)
        return _summary()

    tmp = tempfile.mkdtemp(prefix='build_provenance_')
    pure_leg(tmp)
    rc = _summary('SUMMARY (the pure leg — two more follow)')

    # The two in-process legs, each in its own process because the running
    # build is decided at import (see the module docstring).
    stamp_path = os.path.join(tmp, 'BUILD_INFO.json')
    write_fixture(stamp_path)
    for flag, path in (('--inprocess-stamped', stamp_path),
                       ('--inprocess-unstamped',
                        os.path.join(tmp, 'no-such-stamp.json'))):
        print(f'\n\n########## {flag} (BUILD_INFO_PATH={path}) ##########')
        # Flush before handing stdout to a child, or this process's buffered
        # output lands AFTER the child's when the run is piped to a file.
        sys.stdout.flush()
        env = dict(os.environ, BUILD_INFO_PATH=path)
        child = subprocess.run([sys.executable, os.path.abspath(__file__), flag],
                               env=env)
        if child.returncode != 0:
            print(f'  [FAIL] {flag} exited {child.returncode}')
            rc = 1
    print('\n\n########## OVERALL ##########')
    print('  ALL LEGS PASSED' if rc == 0 else '  FAILURES ABOVE')
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
