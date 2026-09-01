#!/usr/bin/env python
"""The CREED lab block must be INERT unless the launcher asks for it — proved by
running the SAME settings.py twice, with the block and without it, and requiring
the resolved values to be equal.

WHY THIS EXISTS
---------------
`settings.py` ends with a marked block (`# === CREED lab support ... ===` ..
`# === end CREED lab support ===`) that the CREED Lab Launcher detects by text
match. When the launcher exports `CREED_LABEL_FILE`, the block points the room
at a seat-label file so the admin page shows the per-seat present/absent board.
When it does not, the block must do NOTHING AT ALL — because the same
`settings.py` is what `scripts/set_up_otree.bat` and a bare `otree devserver`
have always run, on lab machines nobody is going to re-test.

That promise cannot be checked by reading the block: it reads inert, and the two
ways it could stop being inert are both silent.

  * `ROOMS` is MUTATED IN PLACE, never reassigned. A reassignment would drop
    `welcome_page` (the styled room gate, DECISIONS.md 2026-08-17) and every
    other key the project set — with no error, no traceback, and a participant
    landing on oTree's bare framework interstitial instead of the study's own
    page. Section 2 pins that nothing assigns or mutates `ROOMS` after the
    block, and section 5 pins that an ACTIVE block adds exactly one key.
  * `ADMIN_USERNAME` is assigned by the block AND, ~150 lines earlier, by the
    template itself — and `scripts/set_up_otree.bat` sets the very environment
    variable both of them read. That is the one name where the block and the
    old lab workflow could possibly disagree, so it is the one the differential
    is aimed at (sections 3, 4 and 6). The duplicate assignment is deliberate:
    see DECISIONS.md, "The CREED lab block is carried in settings.py".

THE METHOD: A DIFFERENTIAL, NOT A REMEMBERED BASELINE
-----------------------------------------------------
A committed "this is what ROOMS looked like on the day" literal answers the
wrong question and goes stale the first time a study edits its room. So instead
each scenario executes `settings.py`'s source text in a CHILD PROCESS, twice,
under a byte-identical environment:

    A. the file as it ships (block present)
    B. the same file with everything from the start marker onward cut away

and requires A == B for `ROOMS`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `DEBUG`,
`DATABASES` and `SECRET_KEY`. B is what this project WAS before the block, so
"behaves exactly as it does today" is measured rather than remembered, and the
test keeps working after the room, the admin defaults or the database branch
change.

A child process, not an import, because `settings.py` is import-once: the
values it resolves are decided by the environment AT IMPORT, and no amount of
`os.environ` fiddling inside one interpreter re-runs it.

WHAT IT COVERS
--------------
1. The block is present, both markers intact (the launcher detects it by text),
   and it is genuinely LAST in the file.
2. Nothing assigns or mutates `ROOMS` after the block — asserted from the AST,
   plus the imported `ROOMS` compared against the `ROOMS = [...]` literal
   evaluated on its own. A later assignment would silently delete the room.
3. INERT with the CREED variables absent: A == B, and the concrete facts a
   participant depends on (the `study` room, its `welcome_page`, no
   `participant_label_file` anywhere, `ADMIN_USERNAME == 'admin'`).
4. INERT under the exact environment `scripts/set_up_otree.bat` exports — read
   OUT OF THE BAT FILE, not retyped here — so the lab's existing workflow is
   what is being measured. This is the backwards-compatibility guarantee.
5. ACTIVE with `CREED_LABEL_FILE` set: the `study` room gains
   `participant_label_file` with that exact path and NOTHING ELSE CHANGES —
   asserted as a key-by-key diff against the inert run, not as a spot check.
6. `CREED_ROOM_NAME` defaults to `study`; pointed at a DIFFERENT room name it
   appends a new room and leaves the `study` room completely alone (a
   mistyped launcher config must not strip the room gate).
7. `ADMIN_USERNAME` resolves identically with and without the block when
   `OTREE_ADMIN_USERNAME` is set — the one place the two assignments could
   disagree.

Run:  python scripts/tests/creed_lab_block_test.py
Exit 0 = the block is inert. Boots no server, touches no database (the child
never gets as far as connecting one), needs no browser.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import REPO_ROOT  # noqa: E402  (also puts REPO_ROOT on sys.path)

SETTINGS = os.path.join(REPO_ROOT, 'settings.py')
BAT = os.path.join(REPO_ROOT, 'scripts', 'set_up_otree.bat')

# The two lines the launcher matches on. Retyped here ON PURPOSE: if somebody
# reflows or "tidies" either marker, the launcher stops finding the block and
# this test says so, which a marker read out of the file itself could not.
START_MARKER = '# === CREED lab support (paste at the END of settings.py) ==='
END_MARKER = '# === end CREED lab support ==='

# Every environment variable this test controls. Anything in this set is
# stripped from the inherited environment before a scenario applies its own, so
# a scenario means exactly what it says however the suite was invoked.
CONTROLLED = ('CREED_LABEL_FILE', 'CREED_ROOM_NAME', 'DATABASE_URL')
CONTROLLED_PREFIXES = ('OTREE_', 'DB_')

_failures = []


def check(cond, msg):
    print(f'  [{"PASS" if cond else "FAIL"}] {msg}')
    if not cond:
        _failures.append(msg)
    return bool(cond)


def section(title):
    print(f'\n=== {title} ===')


# --------------------------------------------------------------------------
# running settings.py in a child, under an environment we fully control
# --------------------------------------------------------------------------

# Executes a settings SOURCE TEXT with `__file__` pointing at the real
# settings.py (the sqlite branch builds its path from it) and CWD at the repo
# root (`buildinfo` and `identity` are imported by name), then dumps the
# resolved values as JSON. `repr(ROOMS)` travels alongside the parsed value so
# an ordering or type difference JSON would flatten still shows up.
_CHILD = r'''
import json, os, sys
repo, src_file, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
os.chdir(repo)
sys.path.insert(0, repo)
with open(src_file, encoding='utf-8') as fh:
    source = fh.read()
settings_path = os.path.join(repo, 'settings.py')
ns = {'__file__': settings_path, '__name__': 'settings_under_test'}
exec(compile(source, settings_path, 'exec'), ns)
missing = object()
def grab(name):
    value = ns.get(name, missing)
    return None if value is missing else value
out = {
    'ROOMS': grab('ROOMS'),
    'ROOMS_repr': repr(grab('ROOMS')),
    'ADMIN_USERNAME': grab('ADMIN_USERNAME'),
    'ADMIN_PASSWORD': grab('ADMIN_PASSWORD'),
    'DEBUG': grab('DEBUG'),
    'DATABASES': grab('DATABASES'),
    'SECRET_KEY': grab('SECRET_KEY'),
    'names_defined': sorted(k for k in ns if not k.startswith('__')),
}
with open(out_path, 'w', encoding='utf-8') as fh:
    json.dump(out, fh, sort_keys=True, default=repr)
'''

# The six names the differential compares. `names_defined` is deliberately NOT
# among them: the block legitimately leaves its own `_os`/`_creed_*` helpers
# behind, and oTree never reads a leading-underscore setting.
COMPARED = ('ROOMS', 'ROOMS_repr', 'ADMIN_USERNAME', 'ADMIN_PASSWORD',
            'DEBUG', 'DATABASES', 'SECRET_KEY')


def scenario_env(overrides):
    """The inherited environment with every variable this test controls removed,
    then `overrides` applied. Removing first is what makes a scenario
    reproducible from a shell that happens to have OTREE_PRODUCTION set."""
    env = {k: v for k, v in os.environ.items()
           if k not in CONTROLLED and not k.startswith(CONTROLLED_PREFIXES)}
    env.update(overrides)
    return env


def resolve(source_path, env, workdir):
    """Run `source_path` as settings.py under `env`; return the resolved values."""
    child = os.path.join(workdir, 'child_runner.py')
    if not os.path.exists(child):
        with open(child, 'w', encoding='utf-8') as fh:
            fh.write(_CHILD)
    out_path = os.path.join(workdir, f'out_{abs(hash((source_path, tuple(sorted(env.items())))))}.json')
    proc = subprocess.run(
        [sys.executable, child, REPO_ROOT, source_path, out_path],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise AssertionError(
            f'settings.py did not execute under this environment '
            f'(rc={proc.returncode}):\n{proc.stdout.decode("utf-8", "replace")[-4000:]}')
    with open(out_path, encoding='utf-8') as fh:
        return json.load(fh)


def differential(label, env, with_block, without_block, workdir):
    """Run both sources under `env` and require every compared value to match."""
    a = resolve(with_block, env, workdir)
    b = resolve(without_block, env, workdir)
    for name in COMPARED:
        check(a[name] == b[name],
              f'{label}: {name} identical with and without the block '
              f'({a[name]!r}{"" if a[name] == b[name] else " != " + repr(b[name])})')
    return a


# --------------------------------------------------------------------------
# helpers over the source text
# --------------------------------------------------------------------------

def study_room(rooms, name='study'):
    for room in rooms or []:
        if room.get('name') == name:
            return room
    return None


def parse_bat_env(text):
    """The variables `scripts/set_up_otree.bat` exports, read out of the bat
    itself so an edit there cannot leave this test measuring a workflow nobody
    runs any more. `%VAR%` references are expanded against the ones already set,
    exactly as cmd.exe does."""
    env = {}
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith('REM ') or not stripped.lower().startswith('set '):
            continue
        assignment = stripped[4:]
        if '=' not in assignment:
            continue
        key, _, value = assignment.partition('=')
        # cmd.exe keeps a trailing space in the VALUE (`set OTREE_PRODUCTION=1 `).
        # Stripped here because it is a typo in the bat, not a setting: every
        # variable below is read for its presence or as a bare token, so the
        # space changes nothing — and leaving it in would make this test about
        # the typo instead of about the block.
        value = re.sub(r'%(\w+)%', lambda m: env.get(m.group(1), m.group(0)), value.strip())
        env[key.strip()] = value
    return env


def rooms_literal(source):
    """Evaluate JUST the `ROOMS = [...]` statement, on its own, in an empty
    namespace. Compared against the imported value this answers "did anything
    between that line and the end of the file change ROOMS?" — including a
    mutation, which an assignment-only AST scan cannot see."""
    tree = ast.parse(source)
    for node in tree.body:
        targets = getattr(node, 'targets', [])
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'ROOMS' for t in targets):
            ns = {'dict': dict}
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<rooms>', 'exec'), ns)
            return ns['ROOMS']
    return None


def rooms_binding_lines(source):
    """Every line number at which the name ROOMS is bound, anywhere in the
    tree — plain assignment, augmented assignment, annotated assignment, `for`
    target, `with ... as`, `import as`. Any of them, placed after the block,
    would replace the room the launcher just configured with no error at all."""
    lines = []

    def note(target, lineno):
        if isinstance(target, ast.Name) and target.id == 'ROOMS':
            lines.append(lineno)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                note(element, lineno)

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                note(target, node.lineno)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            note(node.target, node.lineno)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            note(node.target, getattr(node, 'lineno', 0))
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            note(node.optional_vars, getattr(node.context_expr, 'lineno', 0))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name) == 'ROOMS':
                    lines.append(node.lineno)
    return sorted(lines)


def main():
    with open(SETTINGS, encoding='utf-8') as fh:
        full_source = fh.read()
    full_lines = full_source.splitlines()

    # ------------------------------------------------------------------
    section('1. the block is present, its markers are intact, and it is LAST')

    check(full_source.count(START_MARKER) == 1,
          f'the start marker appears exactly once (found '
          f'{full_source.count(START_MARKER)}) — the launcher detects the block '
          f'by this text')
    check(full_source.count(END_MARKER) == 1,
          f'the end marker appears exactly once (found '
          f'{full_source.count(END_MARKER)})')
    if _failures:
        print('\nthe block is not detectable; nothing below can be trusted')
        return 1

    start_index = next(i for i, line in enumerate(full_lines)
                       if line.strip() == START_MARKER)
    end_index = next(i for i, line in enumerate(full_lines)
                     if line.strip() == END_MARKER)
    check(start_index < end_index,
          f'the start marker (line {start_index + 1}) precedes the end marker '
          f'(line {end_index + 1})')

    trailing = [line for line in full_lines[end_index + 1:] if line.strip()]
    check(trailing == [],
          f'nothing follows the end marker but blank lines '
          f'(found {len(trailing)}: {trailing[:3]})')

    block = '\n'.join(full_lines[start_index:end_index + 1])
    for token in ('CREED_LABEL_FILE', 'CREED_ROOM_NAME', 'participant_label_file',
                  'OTREE_ADMIN_USERNAME'):
        check(token in block, f'the block still reads/writes {token}')
    check('"study"' in block or "'study'" in block,
          'the block still defaults CREED_ROOM_NAME to the room this template '
          'ships (`study`)')

    # The pre-block file, reconstructed by cutting at the start marker. This is
    # the "before" half of every differential below, so prove the cut is clean.
    stripped_source = '\n'.join(full_lines[:start_index]) + '\n'
    # NOT "the word CREED is gone": settings.py has said `the CREED large lab`
    # in the ROOMS comment since long before this block existed, and asserting
    # on the bare word would fail on that. What must be gone is the block's own
    # machinery, named one identifier at a time.
    # `participant_label_file` is matched as the BLOCK'S OWN LINE, not as a bare
    # word: settings.py's INSTITUTION_NAME comment has explained what
    # `has_participant_label_file` does to the room-welcome context since long
    # before this block arrived.
    block_tokens = (START_MARKER, END_MARKER, 'CREED_LABEL_FILE',
                    'CREED_ROOM_NAME', '_creed_',
                    '_room["participant_label_file"]')
    for token in block_tokens:
        check(token not in stripped_source,
              f'the stripped source no longer contains {token!r}')
        check(token in full_source,
              f'…and the shipped source DOES ({token!r}) — the paired presence, '
              f'without which the check above would pass against an empty file')
    check(stripped_source.strip().endswith('_check_prelaunch()'),
          'the stripped source ends where settings.py used to end '
          '(`_check_prelaunch()`) — so the block was appended, not inserted '
          'into the middle of something')

    # ------------------------------------------------------------------
    section('2. nothing assigns or mutates ROOMS after the block')

    binding_lines = rooms_binding_lines(full_source)
    check(binding_lines != [],
          f'ROOMS is bound somewhere in settings.py (lines {binding_lines}) — '
          f'the paired presence for the absence asserted next')
    after_block = [n for n in binding_lines if n > end_index + 1]
    check(after_block == [],
          f'no binding of ROOMS after the end marker (line {end_index + 1}); '
          f'found {after_block or "none"}. One there would replace the room '
          f'dict the block just configured, silently and with no error')
    before_block = [n for n in binding_lines if n < start_index + 1]
    check(len(before_block) == 1,
          f'the template itself binds ROOMS exactly once (line '
          f'{before_block}) — two bindings is the drift this rule is about')

    check(rooms_binding_lines(stripped_source) == before_block,
          'the block adds no ROOMS binding outside itself')

    # ------------------------------------------------------------------
    workdir = tempfile.mkdtemp(prefix='creed_block_')
    with_block = SETTINGS
    without_block = os.path.join(workdir, 'settings_without_block.py')
    with open(without_block, 'w', encoding='utf-8') as fh:
        fh.write(stripped_source)

    section('3. INERT with the CREED variables absent (the differential)')
    bare = scenario_env({})
    for name in ('CREED_LABEL_FILE', 'CREED_ROOM_NAME'):
        check(name not in bare, f'{name} is genuinely absent from this scenario')
    inert = differential('vars absent', bare, with_block, without_block, workdir)

    # The same claim stated as facts about the participant's experience, so a
    # differential that compared two equally-broken runs could not pass.
    room = study_room(inert['ROOMS'])
    check(room is not None,
          f'the `study` room still exists (rooms: '
          f'{[r.get("name") for r in inert["ROOMS"] or []]})')
    check((room or {}).get('welcome_page') == '_templates/room_welcome.html',
          f'the `study` room still carries its styled welcome gate '
          f'(welcome_page={(room or {}).get("welcome_page")!r})')
    check((room or {}).get('display_name') == 'Study Session',
          f'the `study` room still carries its display_name '
          f'({(room or {}).get("display_name")!r})')
    labelled = [r.get('name') for r in (inert['ROOMS'] or [])
                if 'participant_label_file' in r]
    check(labelled == [],
          f'no room has a participant_label_file (rooms carrying one: {labelled})')
    check(inert['ADMIN_USERNAME'] == 'admin',
          f'ADMIN_USERNAME falls back to the shipped default '
          f'({inert["ADMIN_USERNAME"]!r})')
    check(inert['DEBUG'] is True,
          f'DEBUG is on with OTREE_PRODUCTION unset ({inert["DEBUG"]!r})')

    # ROOMS as executed vs the ROOMS literal read on its own: catches a
    # mutation anywhere later in the file, which section 2's scan cannot see.
    check(inert['ROOMS'] == rooms_literal(full_source),
          'the ROOMS that settings.py finishes with is exactly the ROOMS '
          'literal it declares — nothing later in the file touched it')

    # ------------------------------------------------------------------
    section('4. INERT under the environment scripts/set_up_otree.bat exports')

    with open(BAT, encoding='utf-8') as fh:
        bat_env = parse_bat_env(fh.read())
    # The bat is the source of these values, but a bat that stopped setting
    # them would quietly turn this section into a copy of section 3. Require
    # the ones the block could possibly collide with to be there.
    for name in ('DB_NAME', 'DATABASE_URL', 'OTREE_ADMIN_USERNAME',
                 'OTREE_ADMIN_PASSWORD', 'OTREE_PRODUCTION'):
        check(name in bat_env,
              f'scripts/set_up_otree.bat still exports {name} '
              f'(={bat_env.get(name)!r})')
    check(bat_env.get('DATABASE_URL', '').endswith(
              f"{bat_env.get('DB_HOST')}:{bat_env.get('DB_PORT')}/{bat_env.get('DB_NAME')}"),
          f'the bat\'s DATABASE_URL expanded as cmd.exe would '
          f'({bat_env.get("DATABASE_URL")!r})')

    lab = differential('set_up_otree.bat env', scenario_env(bat_env),
                       with_block, without_block, workdir)

    # Absolute assertions on the same run: identical-to-nothing is not a pass.
    check(lab['ADMIN_USERNAME'] == bat_env.get('OTREE_ADMIN_USERNAME'),
          f'ADMIN_USERNAME is the bat\'s value ({lab["ADMIN_USERNAME"]!r}) — '
          f'this is the ONE name the block also assigns, so this is where a '
          f'collision would show')
    check(lab['ADMIN_PASSWORD'] == bat_env.get('OTREE_ADMIN_PASSWORD'),
          f'ADMIN_PASSWORD is the bat\'s value ({lab["ADMIN_PASSWORD"]!r})')
    check(lab['DEBUG'] is False,
          f'DEBUG is off — the bat sets OTREE_PRODUCTION ({lab["DEBUG"]!r})')
    engine = (lab['DATABASES'] or {}).get('default', {}).get('ENGINE', '')
    check('postgresql' in engine,
          f'DATABASES took the postgres branch the bat asks for ({engine!r})')
    check((lab['DATABASES'] or {}).get('default', {}).get('NAME')
          == bat_env.get('DB_NAME'),
          f'DATABASES names the bat\'s database '
          f'({(lab["DATABASES"] or {}).get("default", {}).get("NAME")!r})')
    lab_room = study_room(lab['ROOMS'])
    check((lab_room or {}).get('welcome_page') == '_templates/room_welcome.html',
          'the `study` room keeps its welcome gate under the bat environment')
    check(not any('participant_label_file' in r for r in (lab['ROOMS'] or [])),
          'no room gains a participant_label_file under the bat environment')

    # ------------------------------------------------------------------
    section('5. ACTIVE with CREED_LABEL_FILE: one key added, nothing else moved')

    seat_file = os.path.join(workdir, 'creed seats.txt')   # a space, as a lab path may have
    with open(seat_file, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(['A1', 'A2', 'A3', 'B1', 'B2']) + '\n')

    active = resolve(with_block, scenario_env({'CREED_LABEL_FILE': seat_file}),
                     workdir)
    active_room = study_room(active['ROOMS'])
    check(active_room is not None, 'the `study` room is still the room')
    check(active_room.get('participant_label_file') == seat_file,
          f'the `study` room gained participant_label_file with the EXACT path '
          f'exported ({active_room.get("participant_label_file")!r})')
    check(len(active['ROOMS']) == len(inert['ROOMS']),
          f'no room was added ({len(active["ROOMS"])} vs '
          f'{len(inert["ROOMS"])}) — the block found the existing room')

    base_room = study_room(inert['ROOMS'])
    added = set(active_room) - set(base_room)
    removed = set(base_room) - set(active_room)
    changed = {k for k in base_room if k in active_room
               and base_room[k] != active_room[k]}
    check(added == {'participant_label_file'},
          f'exactly one key was added: {sorted(added)}')
    check(removed == set(), f'no key was removed: {sorted(removed)}')
    check(changed == set(),
          f'no pre-existing key changed value: {sorted(changed)}')
    check(active_room.get('welcome_page') == base_room.get('welcome_page'),
          'welcome_page survives the in-place mutation — named explicitly '
          'because losing it is the failure a reassignment would cause')
    check(active['ADMIN_USERNAME'] == inert['ADMIN_USERNAME'],
          f'ADMIN_USERNAME is untouched by the seat file '
          f'({active["ADMIN_USERNAME"]!r})')

    # ------------------------------------------------------------------
    section('6. CREED_ROOM_NAME: defaults to `study`, and never clobbers it')

    explicit = resolve(with_block, scenario_env(
        {'CREED_LABEL_FILE': seat_file, 'CREED_ROOM_NAME': 'study'}), workdir)
    check(explicit['ROOMS_repr'] == active['ROOMS_repr'],
          'CREED_ROOM_NAME=study gives byte-identical ROOMS to leaving it '
          'unset — the documented default is the default')

    other = resolve(with_block, scenario_env(
        {'CREED_LABEL_FILE': seat_file, 'CREED_ROOM_NAME': 'other_room'}), workdir)
    other_room = study_room(other['ROOMS'], 'other_room')
    check(other_room is not None,
          f'a room name the project does not define is ADDED (rooms: '
          f'{[r.get("name") for r in other["ROOMS"] or []]})')
    check((other_room or {}).get('participant_label_file') == seat_file,
          'the added room carries the seat file')
    untouched = study_room(other['ROOMS'])
    check(untouched == base_room,
          f'the `study` room is left exactly as it ships — a launcher pointed '
          f'at the wrong room name must not strip the room gate '
          f'({untouched!r})')

    # ------------------------------------------------------------------
    section('7. ADMIN_USERNAME with OTREE_ADMIN_USERNAME set both ways')

    for value in ('labadmin', 'admin'):
        result = differential(f'OTREE_ADMIN_USERNAME={value}',
                              scenario_env({'OTREE_ADMIN_USERNAME': value}),
                              with_block, without_block, workdir)
        check(result['ADMIN_USERNAME'] == value,
              f'ADMIN_USERNAME resolves to {value!r} '
              f'({result["ADMIN_USERNAME"]!r})')

    # and with the block ACTIVE as well, since that is the lab's real state
    lab_active = resolve(with_block, scenario_env(
        {'CREED_LABEL_FILE': seat_file, 'OTREE_ADMIN_USERNAME': 'labadmin'}),
        workdir)
    check(lab_active['ADMIN_USERNAME'] == 'labadmin',
          f'…and with the seat file set too ({lab_active["ADMIN_USERNAME"]!r})')

    # ------------------------------------------------------------------
    print('\n' + '=' * 72)
    if _failures:
        print(f'{len(_failures)} CHECK(S) FAILED:')
        for failure in _failures:
            print(f'  - {failure}')
        return 1
    print('ALL CHECKS PASS — the CREED lab block is inert unless asked for.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
