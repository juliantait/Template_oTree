"""WHICH BUILD OF THIS STUDY IS RUNNING — read here, stamped at deploy.

WHY THIS FILE EXISTS
--------------------
"What code did this participant actually run?" has to be answerable from the
DATA, months later, without a running container and without trusting anybody's
memory of which deploy was live on which day.

A commit cannot contain its own SHA — the SHA is computed over the commit's
content, so writing it into a tracked file changes the content and changes the
SHA. Commit time and BUILD time are different moments, though, and at build time
the SHA is known. So the stamp is written at DEPLOY into ``BUILD_INFO.json`` at
the app root (gitignored, never committed; the Dockerfile's ``COPY . .`` carries
it into the image), by ``scripts/write_build_info.py`` — the ONE writer. This
module is the ONE reader.

*** PROVENANCE IS DOCUMENTATION, NEVER A GATE (Julian, 2026-08-23). ***
Nothing here may fail, refuse, warn-as-error or change any behaviour because a
stamp is missing, absent or wrong. An unstamped build is a perfectly valid
build: it is the normal state of local development and of every test run. The
one sanctioned exception is `scripts/verify_deploy.py`, a command a human runs
BY HAND after a deploy, which is not in the application path and cannot take a
study down. See DECISIONS.md.

THE THREE PLACES THE BUILD IS RECORDED, AND WHY THEY ARE THREE
--------------------------------------------------------------
They exist so that their DISAGREEMENT is the signal. None is redundant, and
none is trusted alone:

  1. ``participant.build_sha`` / ``participant.build_number`` — THE EVIDENCE,
     and the only one of the three that is authoritative about a participant.
     Stamped ON ARRIVAL from the RUNTIME build, at the same point the treatment
     cell is taken (``before/treatment_assignment.assign_on_arrival``, reached
     from ``intro.instructing.get``). It says what THIS participant's browser
     was actually served. A participant field, so it lives in the ``_vars``
     blob: no column, no migration, and it reaches the participant-level export.

     NOT stamped at session creation, and that is the point: a room session
     deliberately outlives redeploys, so a creation-time stamp would claim every
     participant ran the creation-time build — false for everybody who arrived
     after the next deploy. This template already made exactly that argument for
     `treatment_group` (assigned on arrival, not at creation — DECISIONS.md,
     2026-08-18); this is the same argument about a different field, which is
     why the two are stamped at the same call.

  2. ``session.config['build_at_creation']`` — NOT truth, one half of a
     comparison. Frozen at creation like every config value, so it answers
     exactly one question: "what was current when this session was made?". Its
     NAME carries that; it is deliberately not called ``build``.

     **READ IT RAW** — via ``common.build_at_creation``, the one reader, and
     NEVER through ``common.cfg``. See that function for the trap.

     It is a DICT, not a string, deliberately: oTree turns every
     bool/int/float/str config value into an editable text box on the
     create-session screen (``otree/session.py: custom_editable_fields``), and
     provenance an operator can retype is not provenance.

  3. The session config's ``doc`` string — built at import (``doc_html``) and
     rendered read-only by oTree on the create-session screen, so an operator
     sees which build they are about to create a session ON, before clicking.
     It always reflects the RUNNING build; the copy frozen into a created
     session is inert prose and means nothing afterwards.

DIVERGENCE IS INFORMATION, NOT AN ERROR. A session created on one build and
serving another is the NORMAL case for any session that outlives a redeploy, and
participants spanning two builds is simply what a mid-study deploy looks like
from the data. Nothing in this module or its readers styles that as a problem.

DEGRADATION — THE DEFAULT STATE HERE IS "NO FILE"
-------------------------------------------------
``BUILD_INFO.json`` is ABSENT in local dev and in every test run that does not
create one, and it can be truncated or corrupt on a half-finished deploy.
NOTHING in this module raises for any of that. Absent, unreadable, non-JSON,
non-object, or carrying an implausible SHA all degrade to the same honest
"unstamped" answer, carrying a ``problem`` string saying which. A participant
page must never 500 over provenance.

READING IT
----------
    import buildinfo
    buildinfo.BUILD_INFO          # the running build, loaded ONCE at import
    buildinfo.label()             # 'build 214 · a1b2c3d'  |  'unstamped build'

``BUILD_INFO`` is loaded at import and never refreshed, deliberately: the build
a process is running cannot change while it runs, so a per-request re-read would
only add a stat() per participant page and a way for the answer to change
mid-session. ``load()`` takes an explicit path so a test can exercise a
malformed file without a redeploy.
"""
import json
import logging
import os
from html import escape

logger = logging.getLogger(__name__)

# The app root — resolved from THIS FILE, never the working directory. Tests run
# from a throwaway temp directory (scripts/tests/otree_inprocess.py chdirs), and
# a CWD-relative path would read a different file in each. This is the same
# reasoning as scripts/tests/_repo.py's marker walk: never encode "where the
# caller happens to be standing".
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

BUILD_INFO_FILENAME = 'BUILD_INFO.json'

# The keys scripts/write_build_info.py writes. Stated here as the READER's own
# expectation rather than imported from the writer: a writer and a reader that
# share one list cannot notice a key being dropped from both.
BUILD_INFO_KEYS = ('commit', 'commit_short', 'commit_date', 'subject',
                   'build_number', 'built_at', 'tree_clean')

# What a participant's `build_sha` says when they arrived on a build carrying no
# stamp (local dev, a test, a hand-built image). A WORD, never a fake SHA: it
# must be impossible to mistake for one, and it must be distinguishable from the
# BLANK that means "this participant never arrived at all". Those are two
# different situations and collapsing them would lose the only fact the column
# exists to record.
UNSTAMPED_SHA = 'unstamped'

_SHA_HEX = set('0123456789abcdef')


def build_info_path() -> str:
    """Where the stamp is read from.

    ``BUILD_INFO_PATH`` in the environment overrides it. That is for TESTS
    (which need a stamped, and a deliberately corrupt, file without a redeploy)
    and for a build that stages the file elsewhere. The DEPLOY path is the app
    root, which is where the Dockerfile's ``COPY . .`` puts it.
    """
    return os.environ.get('BUILD_INFO_PATH') or os.path.join(
        APP_ROOT, BUILD_INFO_FILENAME)


def is_real_sha(value) -> bool:
    """True only for a full 40-character hex commit SHA.

    THE ONE PREDICATE, used by the reader, the writer and anything comparing
    two stamps — so the writer cannot produce what the reader would reject.
    Case is normalised first: git prints lowercase, a hand-written stamp may
    not.
    """
    return (isinstance(value, str) and len(value) == 40
            and set(value.lower()) <= _SHA_HEX)


def _unstamped(problem, path, raw=None) -> dict:
    """The honest answer for every failure mode: absent, unreadable, not JSON,
    not an object, or carrying no real SHA.

    SAME SHAPE as a good read, so no caller needs a branch and no caller can
    forget one. ``stamped`` is the only key anything should branch on.
    """
    return dict(stamped=False, commit=None, commit_short='', commit_date='',
                subject='', build_number=None, built_at='', tree_clean=None,
                problem=str(problem), path=path, raw=raw)


def load(path=None) -> dict:
    """Read the build stamp. NEVER raises; returns a normalised dict.

    Keys: ``stamped`` (bool — the only thing callers should branch on),
    ``commit`` (40-char SHA or None), ``commit_short``, ``commit_date``,
    ``subject``, ``build_number`` (int or None), ``built_at``, ``tree_clean``,
    ``problem`` (None when stamped and complete, else what is wrong), ``path``,
    ``raw`` (the parsed file when it parsed at all, for diagnosis).

    A file that parses but carries no real SHA is UNSTAMPED, not "partly
    stamped": the SHA is the identity and everything else is decoration.
    """
    path = path or build_info_path()
    try:
        if not os.path.exists(path):
            return _unstamped(
                f'no {BUILD_INFO_FILENAME} at {path} — this build was not '
                f'stamped at deploy (normal in local development)', path)
        with open(path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        return _unstamped(f'{BUILD_INFO_FILENAME} is not valid JSON ({exc})',
                          path)
    except Exception as exc:                                   # noqa: BLE001
        # Unreadable for any other reason (permissions, a directory in its
        # place, a bad encoding, a truncated read). Never fatal here.
        return _unstamped(f'{BUILD_INFO_FILENAME} could not be read '
                          f'({type(exc).__name__}: {exc})', path)

    if not isinstance(raw, dict):
        return _unstamped(f'{BUILD_INFO_FILENAME} is {type(raw).__name__}, not '
                          f'a JSON object', path,
                          raw=raw if isinstance(raw, (list, str, int)) else None)

    commit = raw.get('commit')
    if not is_real_sha(commit):
        return _unstamped(f'{BUILD_INFO_FILENAME} carries commit={commit!r}, '
                          f'which is not a 40-character hex SHA', path, raw=raw)
    commit = commit.lower()

    # Everything below is DECORATION: a missing or odd value degrades to a
    # sensible substitute rather than invalidating a real SHA.
    short = raw.get('commit_short')
    if not (isinstance(short, str) and short
            and set(short.lower()) <= _SHA_HEX
            and commit.startswith(short.lower())):
        short = commit[:7]
    try:
        build_number = int(raw.get('build_number'))
    except (TypeError, ValueError):
        build_number = None
    missing = [k for k in BUILD_INFO_KEYS if k not in raw]
    return dict(
        stamped=True,
        commit=commit,
        commit_short=short.lower(),
        commit_date=str(raw.get('commit_date') or ''),
        subject=str(raw.get('subject') or ''),
        build_number=build_number,
        built_at=str(raw.get('built_at') or ''),
        tree_clean=raw.get('tree_clean'),
        # A real SHA with a key missing is still a usable stamp, so it stays
        # STAMPED — but the gap is recorded rather than silently tolerated.
        # Nothing fails on it; `problem` is for a human reading /health or the
        # boot banner.
        problem=(f'{BUILD_INFO_FILENAME} is missing {missing}' if missing
                 else None),
        path=path,
        raw=raw,
    )


# THE RUNNING BUILD, resolved ONCE at import. See the module docstring for why
# this is not re-read per request.
BUILD_INFO = load()


def current() -> dict:
    """The running build (the import-time read). A function as well as the
    module constant, so a caller reads it the same way whether or not this is
    ever made refreshable."""
    return BUILD_INFO


def label(info=None) -> str:
    """The human line: ``build 214 · a1b2c3d``, or ``unstamped build``.

    The build NUMBER leads because it is the half people say out loud (nobody
    reads a SHA aloud in a meeting), and the SHA follows because it is the half
    that is unambiguous. Degrades to a plain, honest phrase — never a fake SHA,
    and never an empty string, which would read as a rendering bug.
    """
    info = info or BUILD_INFO
    if not info['stamped']:
        return 'unstamped build'
    n, short = info['build_number'], info['commit_short']
    return f'build {n} · {short}' if n is not None else f'build {short}'


def doc_html(base_doc='', info=None) -> str:
    """The session-config ``doc``: whatever the config already said, plus ONE
    line naming the build this server is running.

    *** THIS STRING IS RENDERED UNESCAPED. ***
    oTree's ``includes/SessionInfo.html`` prints it as ``{{ config.doc|safe }}``,
    so whatever is returned here is live HTML on an admin page. Everything
    interpolated below therefore goes through ``escape()``, and the COMMIT
    SUBJECT is what makes that mandatory rather than tidy: it is free text
    somebody typed into a commit message, and it travels here from a file
    written OUTSIDE this repo, at deploy, by whoever ran the deploy. This
    template has already shipped one reflected XSS through an unescaped value
    (CLAUDE.md), and `scripts/tests/xss_escaping_test.py` pins this one.

    ``base_doc`` is NOT escaped: it is the config's own description, written by
    whoever edits settings.py, and escaping it would break deliberate markup a
    study puts in its own doc. That asymmetry is the point — repo-authored prose
    and a value from outside the repo are different things, and the difference
    is exactly what decides whether it is escaped.

    The flip side of |safe is that light markup is available deliberately:
    ``<b>`` for the key, ``<code>`` for the identifiers, ``<br>`` between the
    lines, so the create-session screen reads as a labelled fact rather than one
    flat run-on sentence.

    WHERE IT SHOWS. That include is pulled into exactly two admin pages — the
    CREATE SESSION form (the point: it names the build BEFORE a session exists)
    and a created session's own description page. It is NOT on the sessions
    list, and it is guarded by ``{% if config.doc %}``, so this function never
    returns ''.

    WHY ``doc`` IS THE RIGHT HOME. It is in oTree's ``NON_EDITABLE_FIELDS``
    (``otree/session.py``): it is never rendered as a form input, AND the REST
    API REJECTS an attempt to modify it. Enforced-uneditable, not uneditable by
    convention — the right property for something an operator reads as a fact.
    Everything else on that screen is an operator-editable input, so the screen
    is reassurance, never evidence; the evidence is on the participants.
    """
    info = info or BUILD_INFO
    if info['stamped']:
        bits = [f'<b>Running build:</b> {escape(label(info))}']
        if info['commit_date']:
            bits.append(escape(info['commit_date']))
        if info['subject']:
            bits.append(f'&ldquo;{escape(info["subject"])}&rdquo;')
        line = ' &middot; '.join(bits)
        line += ('<br>This is the build the SERVER is running now; creating a '
                 'session freezes it as <code>build_at_creation</code>. What '
                 'participants actually ran is stamped on each of them '
                 '(<code>participant.build_sha</code>) when they arrive, so '
                 'the three can differ — which is information, not an error.')
    else:
        line = ('<b>Running build:</b> unstamped &mdash; this server has no '
                f'{escape(BUILD_INFO_FILENAME)}, so it is a local or '
                'hand-built run rather than a stamped deploy. This is NORMAL '
                'in development and blocks nothing: build provenance is '
                'documentation, never a gate.')
    base = str(base_doc or '').strip()
    return f'{base}<br>{line}' if base else line


# ---------------------------------------------------------------------------
# 2. THE FROZEN HALF — what the session was CREATED on
# ---------------------------------------------------------------------------

def config_stamp() -> dict:
    """The value frozen into a new session's config as ``build_at_creation``.

    A DICT on purpose (see the module docstring): oTree makes every
    bool/int/float/str config value an editable text box on the create-session
    screen, and provenance an operator can retype is not provenance.

    Always present and always the same shape, so "created on an unstamped
    build" is a VALUE — absence is reserved for the different fact "this
    session was created before build stamping existed at all". Reading it back
    is ``common.build_at_creation``, which is where that distinction is kept.
    """
    info = BUILD_INFO
    return dict(commit=info['commit'], commit_short=info['commit_short'],
                build_number=info['build_number'], built_at=info['built_at'],
                stamped=info['stamped'])


def normalise_config_stamp(raw):
    """Normalise whatever a frozen session config holds under
    ``build_at_creation`` into the ``config_stamp()`` shape, or None.

    Separate from the READ (``common.build_at_creation``) because they answer
    different questions: this one is "what shape is this value", which belongs
    with the stamp; the read is "how do I get a value off a session config
    safely", which belongs with `common.cfg` / `common.flag`. One
    implementation each, and the read calls this.

    A frozen value is whatever an OLDER build wrote, so this accepts a bare SHA
    string as well as the current dict rather than discarding a stamp it can
    still make sense of. Never raises.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        commit = raw.get('commit')
        real = is_real_sha(commit)
        return dict(
            commit=commit.lower() if real else None,
            commit_short=str(raw.get('commit_short')
                             or (commit[:7].lower() if real else '')),
            build_number=raw.get('build_number'),
            built_at=str(raw.get('built_at') or ''),
            stamped=bool(raw.get('stamped')),
        )
    # An older or hand-edited shape (a bare SHA string, say). Take what it says
    # rather than throwing away a usable fact.
    commit = raw.lower() if is_real_sha(raw) else None
    return dict(commit=commit, commit_short=(commit[:7] if commit else ''),
                build_number=None, built_at='', stamped=bool(commit))


# ---------------------------------------------------------------------------
# 1. THE EVIDENCE — what each participant actually ran
# ---------------------------------------------------------------------------

SHA_FIELD = 'build_sha'
NUMBER_FIELD = 'build_number'
PARTICIPANT_FIELDS = (SHA_FIELD, NUMBER_FIELD)


def init_participant_fields(participant) -> None:
    """Seed both stamp fields at session creation, so the export columns always
    exist and a bare read can never KeyError.

    Seeded BLANK, never with the current build — writing today's SHA here is
    precisely the lie this design exists to avoid, because a row created now may
    not be arrived at until three deploys later. Blank therefore means "never
    arrived"; ``UNSTAMPED_SHA`` means "arrived, on a build with no stamp". This
    is the same choice `treatment_group` makes with '' (DECISIONS.md,
    2026-08-18), and for the same reason.
    """
    participant.build_sha = ''
    participant.build_number = None


def stamp_participant(participant) -> str:
    """Stamp the RUNNING build onto this participant, ONCE, on arrival.

    Called from ``before.treatment_assignment.assign_on_arrival`` — the same
    point the treatment cell is taken, which is the first moment a participant
    is really in the study.

    WRITE-ONCE. Someone who reloads the instructions after a redeploy keeps the
    build they FIRST arrived on; re-stamping would quietly rewrite history to
    the newest deploy and destroy the very divergence this exists to record.

    NEVER RAISES, and that is a DELIBERATE ASYMMETRY with the treatment
    assignment it sits next to: treatment is core experimental assignment and
    must fail loudly, while provenance is instrumentation and must never cost a
    participant a page (CLAUDE.md). Returns whatever the participant now holds,
    or '' if it could not be written.
    """
    try:
        held = participant.vars.get(SHA_FIELD)   # .vars.get, never getattr
        if held:
            return held
        info = BUILD_INFO
        sha = info['commit'] if info['stamped'] else UNSTAMPED_SHA
        participant.build_sha = sha
        participant.build_number = info['build_number']
        return sha
    except Exception:                                          # noqa: BLE001
        logger.exception('[buildinfo] could not stamp the build onto a '
                         'participant; the study continues unstamped')
        return ''
