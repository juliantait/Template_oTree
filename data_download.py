"""THE DASHBOARD'S "DOWNLOAD DATA" BUTTON: three plain CSV files from one press.

Import as ``import data_download``. Stays at the project root, like
``experimenter_dashboard``, which puts the button on its page. Importing this
file pulls in the standard library only: oTree is imported inside the functions
that need it, so nothing here can take a boot down. See DECISIONS.md, 2026-11-05.

WHAT ONE PRESS MAKES (always every session in the database)
-----------------------------------------------------------
  SENSITIVE  oTree's wide export, byte for byte what /ExportWide serves. Always.
  ANONYMOUS  the same without the personal columns. Only if there is something to
             remove: otherwise it would be a raw copy that looks anonymised.
  PAYMENTS   as many of the payment columns as exist.

What goes in each is decided in `data_columns.py`, plain and readable on its own;
this file only reads the export, writes the files and answers the page.

Named ``EXP_<lab session>_<DD-MM-YYYY>[_SENSITIVE|_PAYMENTS][_2].csv``. No pandas:
this runs on a plain oTree install.

WHERE THEY GO: AN ENVIRONMENT VARIABLE, NEVER THE REQUEST
---------------------------------------------------------
``OTREE_DATA_FOLDER`` set: the server writes into ``<folder>/SENSITIVE`` and so
on. The base folder must already exist, so a typo gives an error naming it
rather than a new folder somewhere else; the three subfolders are made when
missing and reused when present.

Not set (a hosted server): the one POST returns all three files and the page
hands them to the browser as separate downloads, so the three come from one read
of the database and the server keeps no copy. The screen says "sent to the
browser" and no more, because the server cannot know whether they arrived.

THE RULES
---------
1. **The dashboard's two rules hold.** Nothing here writes to the database, which
   takes real care because the commit middleware commits on every request and a
   plain export dirties every row (see `_read_rows`). A bug here breaks the button,
   never a participant page.
2. **LOGIN WHATEVER AUTH_LEVEL SAYS, AND CSRF WHATEVER THE ENVIRONMENT SAYS.** The
   dashboard opens up with AUTH_LEVEL unset, and oTree's AdminView skips CSRF
   under OTREE_SKIP_CSRF. Neither applies: these files hold bank details, so both
   checks are done here and an error in either answers 403.
3. **NEVER OVERWRITE.** See `write_set`.
4. **NEVER SILENT.** Every outcome is shown on the screen, file by file.
5. **NO DATA IN LOGS OR ERROR TEXT.** An exception's message can quote a row, so
   `_log_failure` records its type and line numbers and the screen gets its type.

HOLDING oTREE'S GLOBAL LOCK FOR THE READ AND NOT FOR THE WRITE
--------------------------------------------------------------
oTree serialises every request behind one lock (CommitTransactionMiddleware).
The read has to be inside it, as oTree's own /ExportWide is, so it sees committed
data. The disk does not: a folder on a network share or in a synced cloud folder
can stall for a long time, and participant pages must not wait for it. The
middleware lets go of the lock when the response STARTS, so these handlers read
inside the handler and do the file work in the body of a StreamingResponse. Were
that ever to change the files would simply be written under the lock: slower for
participants, nothing lost. `download_data_test.py` measures it.

DRIFT
-----
The route table goes through ``otree_routes``. A failed install is logged and
printed and never raises at boot; the button then says the feature is not
available. ``otree.export`` is looked up at press time, so an oTree that moved it
fails on the button with a message naming it. ``launch_problems`` reports both to
``scripts/prelaunch_check.py``, while somebody can still fix them.
"""

import csv
import datetime
import errno
import hmac
import io
import json
import logging
import os
import re
import secrets
import tempfile
import time
import traceback
import unicodedata

import data_columns
import otree_routes

logger = logging.getLogger(__name__)

ENV_VAR = 'OTREE_DATA_FOLDER'

# Route names, for idempotency and for the launch check.
ROUTE_NAMES = ('ExperimenterDashboardDownloadPlan',
               'ExperimenterDashboardDownload')
PLAN_SUFFIX = '/download_plan'
DOWNLOAD_SUFFIX = '/download'

# One press, three files: (kind, ending of the file name, what the screen says).
# The kind is also the name of the subfolder.
FILE_KINDS = (
    ('SENSITIVE', '_SENSITIVE',
     'The raw export: everything, including any bank details and Prolific IDs.'),
    ('ANONYMOUS', '',
     'The same data without bank details, Prolific IDs, labels and the earned total.'),
    ('PAYMENTS', '_PAYMENTS',
     'Who to pay: the columns that exist of participant code, Prolific ID, IBAN, BIC, total earned, '
     'Prolific ID conflict.'),
)
KINDS = tuple(kind for kind, _ending, _what in FILE_KINDS)

MAX_SET_NUMBER = 999
LAB_SESSION_MAX_CHARS = 60

# How long a move onto our own placeholder keeps trying: on Windows a virus
# scanner or an indexer can hold a brand-new file open for a moment.
_REPLACE_TRIES = 6
_REPLACE_WAIT_SECONDS = 0.15

NO_STORE = {'Cache-Control': 'no-store, max-age=0', 'Pragma': 'no-cache',
            'X-Content-Type-Options': 'nosniff'}


class ExportDrift(RuntimeError):
    """oTree's export is no longer what this file was written against."""


class NoData(Exception):
    """There is nothing to export. Not a failure: there are no participants."""


# =============================================================================
# NAMES
# =============================================================================

def safe_lab_session(value) -> str:
    """The lab session as a piece of a file name, on Windows, macOS and Linux.

    Letters (of any alphabet), digits, `_`, `-` and a single `.` stay; anything
    else becomes `-`. So `217 b` is `217-b`, `217/b` is `217-b` and `../../x` is
    `x`: readable, and nothing that can leave the folder. Empty when nothing
    usable is left, which reads the same as no lab session. Two values that come
    out alike are harmless, because a taken name gets a number.

    A Windows device name such as CON cannot be the whole file name, because the
    name always starts with EXP_.
    """
    text = unicodedata.normalize('NFC', str('' if value is None else value))
    text = re.sub(r'[^\w.-]+', '-', text)
    text = re.sub(r'\.{2,}', '-', text)
    text = re.sub(r'-{2,}', '-', text)
    return text[:LAB_SESSION_MAX_CHARS].strip('-._')


def name_stem(lab_session, today=None) -> str:
    """`EXP_217_05-11-2026`, or `EXP_05-11-2026` with no lab session. Today is the
    date on the machine running the server."""
    today = today or datetime.date.today()
    safe = safe_lab_session(lab_session)
    middle = f'{safe}_' if safe else ''
    return f'EXP_{middle}{today:%d-%m-%Y}'


def file_name(stem, kind, number=1) -> str:
    """A set's numbers go at the very end, so a sorted folder keeps each kind
    together: EXP_217_05-11-2026_SENSITIVE_2.csv."""
    ending = dict((k, e) for k, e, _what in FILE_KINDS)[kind]
    tail = f'_{number}' if number > 1 else ''
    return f'{stem}{ending}{tail}.csv'


# =============================================================================
# THE FOLDER
# =============================================================================

def clean_folder_setting(raw, path=os.path):
    """(folder, problem) from the raw setting. Both None: browser mode.

    `path` is `os.path`; the tests pass `ntpath` to check Windows spellings on
    this machine. Quotes are removed because Windows' "Copy as path" adds them and
    `set X="C:\\data"` in a batch file keeps them.

    A relative path is refused, not resolved: it would mean "relative to wherever
    the server was started", which is how a file lands in a surprising place.
    """
    text = str(raw or '').strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        text = text[1:-1].strip()
    if not text:
        return None, None
    text = path.expanduser(text)
    if not path.isabs(text):
        return text, (f'The folder set in {ENV_VAR} is not a full path: {text}. '
                      f'Set it to a full path, such as C:\\Data or /Users/you/data.')
    return path.normpath(text), None


def folder_setting():
    """Read from the server's environment, at every press, and from nowhere
    else: no value in a request can ever choose where a file goes."""
    return clean_folder_setting(os.environ.get(ENV_VAR))


def folder_problem(folder):
    """Why this base folder cannot be used, or None. It is never created."""
    if not os.path.exists(folder):
        return (f'The folder set in {ENV_VAR} does not exist: {folder}. '
                f'Check it for a typo, or create the folder, then press again. '
                f'No files were written.')
    if not os.path.isdir(folder):
        return (f'{ENV_VAR} points at a file, not a folder: {folder}. '
                f'No files were written.')
    return None


def _why(exc) -> str:
    """An OSError in plain words. Its filename is one we chose and its strerror
    is the operating system's; neither holds participant data."""
    known = {
        errno.EACCES: 'no permission to write there',
        errno.EPERM: 'no permission to write there',
        errno.EROFS: 'that disk is read-only',
        errno.ENOSPC: 'the disk is full',
        errno.ENOENT: 'the folder disappeared while writing',
        errno.ENOTDIR: 'a file is in the way of that folder',
        errno.EEXIST: 'a file is in the way of that folder',
    }
    return known.get(getattr(exc, 'errno', None)) or (
        getattr(exc, 'strerror', None) or type(exc).__name__)


def _make_subfolder(folder, kind) -> str:
    """Create or reuse one subfolder. `mkdir`, not `makedirs`: the base folder
    was checked, and if it vanished since then this must fail, not rebuild it."""
    sub = os.path.join(folder, kind)
    try:
        os.mkdir(sub)
    except FileExistsError:
        if not os.path.isdir(sub):
            raise
    return sub


def next_number(folder, stem) -> int:
    """The first number at which NONE of the three names exists yet. A number is
    skipped if any one of them is taken, so a set stays together under one number
    even when an earlier press only wrote part of its set."""
    for number in range(1, MAX_SET_NUMBER + 1):
        if not any(os.path.lexists(os.path.join(folder, kind,
                                                file_name(stem, kind, number)))
                   for kind in KINDS):
            return number
    raise OSError(0, f'more than {MAX_SET_NUMBER} sets for one day')


# =============================================================================
# WRITING WITHOUT EVER OVERWRITING
# =============================================================================

def _write_temp(sub, data) -> str:
    """The whole file, flushed, under a hidden temp name in its own subfolder, so
    the later move is a rename on one disk. mkstemp gives owner-only permissions
    and creates exclusively."""
    fd, temp = tempfile.mkstemp(prefix='.export-', suffix='.tmp', dir=sub)
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        _remove_quietly(temp)
        raise
    return temp


def _remove_quietly(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _reserve(path):
    """Take the final name, or raise FileExistsError if anybody has it. This is
    the exclusive step, safe against a double click, two tabs or a second server."""
    os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))


def _move_onto_placeholder(temp, final):
    """Replace our own empty placeholder with the finished file, atomically."""
    for attempt in range(_REPLACE_TRIES):
        try:
            os.replace(temp, final)
            return
        except PermissionError:
            if attempt == _REPLACE_TRIES - 1:
                raise
            time.sleep(_REPLACE_WAIT_SECONDS)


def write_set(folder, stem, built) -> list:
    """Write one set, returning one result per file. Never overwrites.

    `built` holds one dict per kind: `kind`, `rows`, `note`, and `data` (bytes), or
    `why` and `skipped` when there is no file (see data_columns.split_export).

    THE SAME ALGORITHM ON EVERY OPERATING SYSTEM, deliberately: this runs on the
    lab's Windows machines and is tested on Linux, so a branch per platform would
    mean the branch that matters was never run.

      1. Every file is written in full to a temp name. This is where most
         failures happen, before any final name exists.
      2. A number is chosen with no name taken, then each final name is taken
         with O_CREAT | O_EXCL, a real create-only that no other press can win
         too. Losing it means a concurrent press got there first: let go of what
         this attempt holds and try the next number, so all three stay together.
      3. Each temp is moved onto its own placeholder. A reader can see an empty
         file for an instant, never half a file, and a failed move removes the
         placeholder.

    A FILE THAT CANNOT BE WRITTEN DOES NOT STOP THE OTHERS. Export is the rescue
    path: with one subfolder broken, the two that can be saved are saved, and the
    screen says which is missing and why. A retry gets a new number.
    """
    results = {}
    ready = []
    for item in built:
        kind = item['kind']
        results[kind] = dict(kind=kind, rows=item.get('rows', 0), written=False,
                             path=os.path.join(folder, kind, file_name(stem, kind)),
                             name=file_name(stem, kind), why=item.get('why'),
                             skipped=item.get('skipped', False),
                             note=item.get('note'))
        if item.get('data') is None:
            continue
        try:
            sub = _make_subfolder(folder, kind)
            ready.append((kind, sub, _write_temp(sub, item['data'])))
        except OSError as exc:
            results[kind]['why'] = _why(exc)

    number = 1
    try:
        if ready:
            number = next_number(folder, stem)
        while ready:
            taken = []
            lost_the_race = False
            for entry in list(ready):
                kind, sub, temp = entry
                final = os.path.join(sub, file_name(stem, kind, number))
                try:
                    _reserve(final)
                    taken.append((entry, final))
                except FileExistsError:
                    lost_the_race = True
                    break
                except OSError as exc:
                    results[kind]['why'] = _why(exc)
                    ready.remove(entry)
                    _remove_quietly(temp)
            if lost_the_race:
                for _entry, final in taken:
                    _remove_quietly(final)
                number = next_number(folder, stem)
                continue
            for entry, final in taken:
                kind, _sub, temp = entry
                try:
                    _move_onto_placeholder(temp, final)
                    results[kind].update(written=True, why=None)
                except OSError as exc:
                    results[kind]['why'] = _why(exc)
                    _remove_quietly(final)
                    _remove_quietly(temp)
                ready.remove(entry)
    except OSError as exc:
        for kind, _sub, _temp in ready:
            results[kind]['why'] = _why(exc)
    finally:
        for _kind, _sub, temp in ready:
            _remove_quietly(temp)

    # One consistent set on the screen: a file that failed is listed under the
    # name it would have had, with the number the others got.
    for kind, result in results.items():
        result['name'] = file_name(stem, kind, number)
        result['path'] = (None if result['skipped']
                          else os.path.join(folder, kind, result['name']))
    return [results[item['kind']] for item in built]


# =============================================================================
# THE THREE FILES, FROM oTREE'S OWN WIDE EXPORT
# =============================================================================

def _checked_export():
    """oTree's wide export, or a drift raise naming what moved. Looked up at press
    time, so an oTree that changed it fails on the button, not at server start."""
    try:
        from otree import export
    except ImportError as exc:
        raise ExportDrift(
            f'otree.export cannot be imported ({type(exc).__name__}).') from exc
    reader = getattr(export, 'get_rows_for_wide_csv', None)
    if not callable(reader):
        raise ExportDrift(
            'otree.export.get_rows_for_wide_csv is gone or no longer a function '
            '(this was written against oTree 6.0.15).')
    return reader


def check_rows(rows) -> list:
    """The export's rows, or NoData when there are no participants, or a drift
    raise if the shape is not the one this file reads. oTree answers [[]] when
    there are no participants at all."""
    if rows == [[]] or rows == []:
        raise NoData()
    good = (isinstance(rows, list) and rows and isinstance(rows[0], list)
            and all(isinstance(name, str) for name in rows[0])
            and 'participant.code' in rows[0])
    if not good:
        raise ExportDrift(
            "oTree's wide export no longer starts with a header row holding "
            'participant.code (this was written against oTree 6.0.15).')
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ExportDrift(
            "oTree's wide export has rows of a different length than its header "
            '(this was written against oTree 6.0.15).')
    return rows


def _read_rows() -> list:
    """Every session's wide rows. Runs in a worker thread, under oTree's lock.

    THE EXPORT MUST NOT WRITE, AND LEFT TO ITSELF IT DOES. oTree's `.vars` property
    calls `self._vars.changed()` on every READ (otree/database.py, verified on
    6.0.15), so `get_rows_for_wide_csv` marks every participant and session as
    changed. Its next query then autoflushes an UPDATE of each `_vars` blob, and
    the commit middleware commits them, for every row in the database, in the
    middle of a running session. oTree's own /ExportWide does exactly that.

    So: no autoflush, which stops the UPDATEs being sent at all, and a rollback,
    which forgets the changed-marks before the middleware commits. Nothing else
    uses this database session: the request is under the lock and the rows are
    plain values by now. `download_data_test.py` counts the SQL statements.
    """
    from otree.database import db
    reader = _checked_export()
    session = db._db
    try:
        with session.no_autoflush:
            rows = reader(None)
    finally:
        session.rollback()
    return check_rows(rows)


def _csv_bytes(rows) -> bytes:
    """The same writer oTree's export uses: `csv.writer` with its defaults, CRLF
    line ends, UTF-8 without a BOM. The tests compare this byte for byte against
    /ExportWide. newline='' keeps Windows from turning CRLF into CRCRLF."""
    buffer = io.StringIO(newline='')
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode('utf-8')


def build_files(rows) -> list:
    """The three files from one read, as dicts for `write_set` or the browser. The
    decisions are data_columns.split_export's; this only encodes the tables."""
    return [dict(kind=part['kind'], rows=part['count'], why=part['why'],
                 skipped=part['skipped'], note=part['note'],
                 data=None if part['table'] is None else _csv_bytes(part['table']))
            for part in data_columns.split_export(rows)]


# =============================================================================
# FAILING IN THE OPEN, WITHOUT DATA
# =============================================================================

def _log_failure(where, exc):
    """Type and line numbers only. An exception's message can quote a row, and a
    traceback's text is built from it, so `logger.exception` is not used here."""
    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    place = ' < '.join(f'{os.path.basename(f.filename)}:{f.lineno}'
                       for f in reversed(frames))
    logger.error('[download] %s failed: %s at %s',
                 where, type(exc).__name__, place)


def _failure_message(exc) -> str:
    """What the screen says when the read or the build fails. The class name is
    enough to search the log for; `str(exc)` might hold a participant's data. An
    ExportDrift's text is written in this file, so it can be shown."""
    if isinstance(exc, ExportDrift):
        return (f'This server\'s oTree does not match this template: {exc} '
                f'The study itself is not affected. No files were written.')
    return ('The export failed, so no files were written '
            f'({type(exc).__name__}; the details are in the server log). '
            'The study itself is not affected. Press again to retry.')


NO_DATA_MESSAGE = ('There is no participant data in this database yet, so there '
                   'is nothing to download. No files were written.')


# =============================================================================
# THE TWO ANSWERS
# =============================================================================

def build_plan(facts, rows) -> dict:
    """What a press would do right now, for the confirmation step: the same rules
    on the same export, so what it says about each file is what a press will do.
    Writes nothing and touches no folder but to look. Runs after the lock has been
    released. `rows` is None when there are no participants."""
    plan = dict(ok=True, mode='browser', folder=None, warnings=[], files=[],
                sessions=facts['sessions'], participants=facts['participants'],
                session_participants=facts['session_participants'],
                lab_session=facts['lab_session'])
    if rows is None:
        return dict(plan, ok=False, problem='no_data', message=NO_DATA_MESSAGE)

    if not facts['session_participants']:
        plan['warnings'].append(
            'This session has no participants. The files still cover the '
            'participants in the other sessions.')

    folder, problem = folder_setting()
    number = 1
    if folder is not None:
        problem = problem or folder_problem(folder)
        plan.update(mode='folder', folder=folder)
        if problem:
            return dict(plan, ok=False, problem='folder', message=problem)
        number = next_number(folder, facts['stem'])

    parts = {part['kind']: part for part in data_columns.split_export(rows)}
    for kind, _ending, what in FILE_KINDS:
        part = parts[kind]
        name = file_name(facts['stem'], kind, number)
        entry = dict(kind=kind, name=name, what=what, path=None, why=part['why'],
                     skipped=part['skipped'], note=part['note'])
        if folder is not None and part['table'] is not None:
            sub = os.path.join(folder, kind)
            entry['path'] = os.path.join(sub, name)
            if os.path.exists(sub) and not os.path.isdir(sub):
                plan['warnings'].append(
                    f'A file called {kind} is in the way of the folder {sub}, '
                    f'so the {kind} file cannot be written.')
        plan['files'].append(entry)
    return plan


def run_download(rows, stem) -> dict:
    """Build the three files and send them where the setting says. Runs after the
    lock has been released, and re-reads the setting at this moment."""
    folder, problem = folder_setting()
    if folder is not None:
        problem = problem or folder_problem(folder)
        if problem:
            return dict(ok=False, mode='folder', folder=folder, problem='folder',
                        message=problem, files=[])

    built = build_files(rows)
    if folder is None:
        files = [dict(kind=item['kind'], rows=item['rows'], why=item['why'],
                      skipped=item['skipped'], note=item['note'],
                      name=file_name(stem, item['kind']),
                      text=(item['data'].decode('utf-8')
                            if item['data'] is not None else None))
                 for item in built]
        return dict(ok=all(f['text'] is not None or f['skipped'] for f in files),
                    mode='browser', folder=None, files=files)

    files = write_set(folder, stem, built)
    return dict(ok=all(f['written'] or f['skipped'] for f in files), mode='folder',
                folder=folder, files=files)


# =============================================================================
# ROUTES
# =============================================================================

def _checked_login_machinery():
    """The dashboard's own check that AdminView still carries its login, plus the
    CSRF token's name in oTree. Without either the routes are not installed: the
    button then reports it, and nothing is open."""
    import experimenter_dashboard as ed
    admin_view = ed._checked_admin_view()
    from otree.common import CSRF_TOKEN_NAME
    return admin_view, ed.URL_BASE, CSRF_TOKEN_NAME


def _build_routes():
    from starlette.concurrency import run_in_threadpool
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route

    admin_view, url_base, csrf_name = _checked_login_machinery()

    def refusal(status, problem, message):
        return JSONResponse(dict(ok=False, problem=problem, message=message),
                            status_code=status, headers=NO_STORE)

    def in_the_stream(work, where):
        """A response whose body does `work` in a thread, after the middleware
        has let go of oTree's lock (see the module docstring). A failure becomes
        an answer on the screen, not a broken stream."""
        async def body():
            try:
                answer = await run_in_threadpool(work)
            except Exception as exc:                           # noqa: BLE001
                _log_failure(where, exc)
                answer = dict(ok=False, problem='failed',
                              message=_failure_message(exc), files=[])
            yield json.dumps(answer).encode('utf-8')
        return StreamingResponse(body(), media_type='application/json',
                                 headers=NO_STORE)

    def session_facts(code):
        """What the plan and the file names need. Reads only; under the lock."""
        from otree.database import db
        from otree.models import Participant, Session
        session = db.query(Session).filter_by(code=code).one_or_none()
        if session is None:
            return None
        lab_session = session.config.get('lab_session')
        return dict(
            lab_session=str('' if lab_session is None else lab_session),
            stem=name_stem(lab_session),
            sessions=db.query(Session).count(),
            participants=db.query(Participant).count(),
            session_participants=db.query(Participant).filter(
                Participant.session_id == session.id).count())

    class _Base(admin_view):
        """Replaces AdminView's dispatch outright, so its AUTH_LEVEL switch
        (`_requires_login`) and its OTREE_SKIP_CSRF escape are never reached.
        `_is_logged_in` is the one thing reused: it is oTree's own cookie check."""
        _requires_login = True

        async def dispatch(self):
            self.request = request = Request(self.scope, receive=self.receive)
            try:
                response = await self.guarded(request)
            except Exception as exc:                           # noqa: BLE001
                _log_failure(type(self).__name__, exc)
                response = JSONResponse(
                    dict(ok=False, problem='failed',
                         message=_failure_message(exc), files=[]),
                    headers=NO_STORE)
            await response(self.scope, self.receive, self.send)

        async def guarded(self, request):
            # FAIL CLOSED: if deciding "is this an operator?" breaks, deny.
            try:
                logged_in = self._is_logged_in()
            except Exception as exc:                           # noqa: BLE001
                _log_failure('login check', exc)
                logged_in = False
            if not logged_in:
                return refusal(403, 'login', 'Please log in to the oTree admin '
                               'first. Downloading data always needs the login.')
            return await self.answer(request, request.path_params['code'])

    class ExperimenterDashboardDownloadPlan(_Base):
        url_pattern = url_base + '/{code}' + PLAN_SUFFIX

        async def answer(self, request, code):
            if request.method.lower() != 'get':
                return refusal(405, 'method', 'Use GET.')
            facts = await run_in_threadpool(session_facts, code)
            if facts is None:
                return refusal(404, 'session', 'This session no longer exists.')
            # The token for the POST, handed to the page that asked. oTree keeps
            # it in the login cookie's session; a page on another site cannot
            # read this answer. Minted the way AdminView mints it.
            token = request.session.get(csrf_name)
            if not token:
                token = secrets.token_hex(16)
                request.session[csrf_name] = token
            # A real read, because what can be said about each file depends on the
            # export: the confirm step says it before anything is written. No more
            # costly than the press itself, and only an operator's click pays it.
            try:
                rows = await run_in_threadpool(_read_rows)
            except NoData:
                rows = None

            def work():
                return dict(build_plan(facts, rows), csrf_name=csrf_name, csrf=token)
            return in_the_stream(work, 'plan')

    class ExperimenterDashboardDownload(_Base):
        url_pattern = url_base + '/{code}' + DOWNLOAD_SUFFIX

        async def answer(self, request, code):
            if request.method.lower() != 'post':
                return refusal(405, 'method', 'Use POST.')
            # CSRF: oTree's token, whatever OTREE_SKIP_CSRF says. Fail closed.
            try:
                form = await request.form()
                sent = form.get(csrf_name)
                expected = request.session.get(csrf_name)
                good = (isinstance(sent, str) and isinstance(expected, str)
                        and bool(expected)
                        and hmac.compare_digest(sent.encode(), expected.encode()))
            except Exception as exc:                           # noqa: BLE001
                _log_failure('csrf check', exc)
                good = False
            if not good:
                return refusal(403, 'csrf', 'This page is out of date. Reload it '
                               'and press the button again.')

            facts = await run_in_threadpool(session_facts, code)
            if facts is None:
                return refusal(404, 'session', 'This session no longer exists.')
            try:
                rows = await run_in_threadpool(_read_rows)
            except NoData:
                return JSONResponse(
                    dict(ok=False, problem='no_data', message=NO_DATA_MESSAGE,
                         files=[]), headers=NO_STORE)
            return in_the_stream(lambda: run_download(rows, facts['stem']),
                                 'download')

    return [
        Route(ExperimenterDashboardDownloadPlan.url_pattern,
              ExperimenterDashboardDownloadPlan,
              name='ExperimenterDashboardDownloadPlan'),
        Route(ExperimenterDashboardDownload.url_pattern,
              ExperimenterDashboardDownload,
              name='ExperimenterDashboardDownload'),
    ]


def install_download_route():
    """INSTALLED / ALREADY / NOT_IMPORTABLE; raises only on version drift."""
    return otree_routes.install(ROUTE_NAMES, _build_routes,
                                'data_download.install_download_route')


def download_is_installed() -> bool:
    return otree_routes.is_installed(ROUTE_NAMES)


def install_download_route_or_note():
    """THE BOOT CALL (end of outro/__init__.py). Never raises: a participant must
    not lose a boot over an operator's button. Drift is logged and printed, and
    the button itself says the feature is not available. A bad folder setting is
    said out loud here too, so it is seen at launch, not at the end of a session."""
    try:
        outcome = install_download_route()
    except Exception as exc:                                   # noqa: BLE001
        message = (f'[download] DOWNLOAD DATA NOT INSTALLED (version drift): '
                   f'{exc}\nParticipants are unaffected; the button will say it '
                   f'is not available.')
        logger.error(message)
        print(message, flush=True)
        return 'drift'
    if outcome == otree_routes.NOT_IMPORTABLE:
        message = ('[download] DOWNLOAD DATA NOT INSTALLED: otree.urls was not '
                   'importable at the install point. Participants are unaffected.')
        logger.error(message)
        print(message, flush=True)
    problem = folder_setting_problem()
    if problem:
        message = f'[download] DOWNLOAD DATA WARNING: {problem}'
        logger.warning(message)
        print(message, flush=True)
    return outcome


def folder_setting_problem():
    """The folder setting's problem as text, or None. Never raises."""
    try:
        folder, problem = folder_setting()
        if folder is None:
            return None
        return problem or folder_problem(folder)
    except Exception as exc:                                   # noqa: BLE001
        return f'{ENV_VAR} could not be checked ({type(exc).__name__}).'


def launch_problems() -> list:
    """(label, current, must_be) for scripts/prelaunch_check.py. Never raises."""
    label = 'Download data button'
    problems = []
    try:
        outcome = install_download_route()
        if not download_is_installed():
            problems.append(
                (f'{label} (routes in otree.urls.routes)',
                 f'not installed (install returned {outcome!r})',
                 'installed: the button on the dashboard cannot work'))
    except Exception as exc:                                   # noqa: BLE001
        problems.append(
            (f'{label} (install)', f'{type(exc).__name__}: {exc}',
             'a clean install: the route builder raised (version drift)'))
    try:
        _checked_export()
    except ExportDrift as exc:
        problems.append((f'{label} (oTree export)', str(exc),
                         'callable otree.export.get_rows_for_wide_csv'))
    problem = folder_setting_problem()
    if problem:
        problems.append((f'{label} ({ENV_VAR})', problem,
                         'an existing folder, given as a full path, or unset'))
    return problems


# =============================================================================
# THE PAGE: CSS AND JS, PUT IN THE DASHBOARD'S PAGE BY experimenter_dashboard.py
# =============================================================================

# Reuses the panel the quiz-mistakes overlay already has (.qm-overlay, .qm-panel,
# .qm-head, .qm-body, .qm-err, .qm-btn). The dashboard has one colour theme, set
# by base.css, so there is one here; every colour is one of its tokens.
PAGE_CSS = r"""
/* DOWNLOAD DATA (data_download.py). The button sits at the far right of the
   header row. The panel's main action and its result are the loudest things in
   it, on purpose: they say what is about to happen and what did. */
.dl-open { font: inherit; font-size: .85rem; font-weight: 650; cursor: pointer;
  border: 1px solid var(--accent); background: var(--card-bg);
  color: var(--accent); border-radius: var(--r-sm); padding: 5px 13px;
  white-space: nowrap; }
.dl-open:hover { background: var(--accent-soft); }
.dl-panel { max-width: 860px; }
.dl-lead { margin: 0 0 12px; font-size: 1.02rem; color: var(--ink); }
.dl-note { margin: 10px 0 12px; font-size: .86rem; color: var(--ink-soft); }
.dl-folder { font-weight: 650; color: var(--ink); overflow-wrap: anywhere; }
.dl-files { list-style: none; margin: 0; padding: 0; }
.dl-files li { border: 1px solid var(--line); border-radius: var(--r-sm);
  padding: 9px 13px; margin-bottom: 8px; font-size: .88rem; }
.dl-files li.good { border-left: 4px solid var(--ok); }
.dl-files li.bad { border-left: 4px solid var(--danger); }
.dl-files li.none { border-left: 4px solid var(--line-strong); }
.dl-kind { font-weight: 700; color: var(--ink); margin-right: 8px; }
.dl-what { color: var(--ink-soft); }
.dl-path { display: block; margin-top: 3px; color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
               "Liberation Mono", monospace;
  font-size: .8rem; overflow-wrap: anywhere; }
.dl-why { display: block; margin-top: 3px; color: var(--danger);
  font-weight: 650; }
.dl-said { display: block; margin-top: 3px; color: var(--ink); font-weight: 650; }
.dl-actions { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.dl-primary { font: inherit; font-size: 1rem; font-weight: 700; cursor: pointer;
  border: none; background: var(--accent); color: #fff;
  border-radius: var(--r-sm); padding: 10px 22px; }
.dl-primary:hover { background: var(--accent-hover); }
.dl-primary:disabled { background: var(--line-strong); cursor: default; }
.dl-verdict { margin: 0 0 12px; font-size: 1.15rem; font-weight: 700; }
.dl-verdict.good { color: var(--ok); }
.dl-verdict.bad { color: var(--danger); }
"""

# In its OWN <script> block, after the dashboard's: a mistake here cannot stop the
# poll that paints the table. Every value reaches the page through textContent,
# so a folder name or a lab session cannot inject anything. The CSV text lives in
# Blobs only while the panel is open and is released when it closes.
PAGE_JS = r"""
(function () {
  'use strict';
  var opener = document.getElementById('dl-open');
  var overlay = document.getElementById('dl-overlay');
  if (!opener || !overlay) return;
  var base = (typeof DATA_URL === 'string' ? DATA_URL : location.pathname + '/data')
    .replace(/\/data$/, '');
  var TIMEOUT_MS = 180000;
  var busy = false;
  var blobUrls = [];

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function releaseBlobs() {
    blobUrls.forEach(function (u) { URL.revokeObjectURL(u); });
    blobUrls = [];
  }
  function close() {
    if (busy) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    overlay.textContent = '';
    releaseBlobs();
    opener.focus();
  }
  function show(title, sub, fill) {
    var panel = el('div', 'qm-panel dl-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', title);
    var head = el('div', 'qm-head');
    var words = el('div');
    words.appendChild(el('h2', '', title));
    if (sub) words.appendChild(el('div', 'pop', sub));
    head.appendChild(words);
    head.appendChild(el('span', 'spacer'));
    if (!busy) {
      var x = el('button', 'qm-close', '\u00d7');
      x.type = 'button';
      x.title = 'Close';
      x.id = 'dl-x';
      x.addEventListener('click', close);
      head.appendChild(x);
    }
    panel.appendChild(head);
    var body = el('div', 'qm-body');
    fill(body);
    panel.appendChild(body);
    overlay.textContent = '';
    overlay.appendChild(panel);
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
  }
  function actions(body, primaryText, onPrimary, closeText) {
    var row = el('div', 'dl-actions');
    var primary = null;
    if (primaryText) {
      primary = el('button', 'dl-primary', primaryText);
      primary.type = 'button';
      primary.id = 'dl-confirm';
      primary.addEventListener('click', onPrimary);
      row.appendChild(primary);
    }
    var other = el('button', 'qm-btn', closeText);
    other.type = 'button';
    other.id = 'dl-cancel';
    other.addEventListener('click', close);
    row.appendChild(other);
    body.appendChild(row);
    (primary || other).focus();
  }
  function showError(title, message) {
    show(title, '', function (body) {
      body.appendChild(el('div', 'qm-err', message));
      actions(body, null, null, 'Close');
    });
  }
  function showLogin(message) {
    show('Log in first', '', function (body) {
      body.appendChild(el('p', 'dl-lead', message));
      var row = el('p', 'dl-note');
      var link = el('a', '', 'Open the oTree login page');
      link.href = '/login';
      link.target = '_blank';
      link.rel = 'noopener';
      row.appendChild(link);
      body.appendChild(row);
      actions(body, null, null, 'Close');
    });
  }
  function ask(url, options) {
    var abort = new AbortController();
    var timer = setTimeout(function () { abort.abort(); }, TIMEOUT_MS);
    options = options || {};
    options.credentials = 'same-origin';
    options.cache = 'no-store';
    options.signal = abort.signal;
    return fetch(url, options).then(function (resp) {
      // Our own refusals are JSON. A page that is not JSON is somebody else's:
      // a 404 means the routes were never installed.
      return resp.json().catch(function () {
        return { ok: false, problem: resp.status === 404 ? 'not_available' : 'unreadable' };
      });
    }).finally(function () { clearTimeout(timer); });
  }
  function hasFile(f) { return !f.skipped && !f.why; }
  function howMany(n) {
    return n === 1 ? 'the file' : n === 2 ? 'the 2 files' : 'the ' + n + ' files';
  }
  function listPlanned(plan, body) {
    var list = el('ul', 'dl-files');
    plan.files.forEach(function (f) {
      var item = el('li', f.skipped ? 'none' : f.why ? 'bad' : '');
      item.appendChild(el('span', 'dl-kind', f.kind));
      if (f.skipped) {
        item.appendChild(el('span', 'dl-said', f.why));
      } else if (f.why) {
        item.appendChild(el('span', 'dl-why', f.why));
      } else {
        item.appendChild(el('span', 'dl-what', f.what));
        item.appendChild(el('span', 'dl-path', f.path || f.name));
        if (f.note) item.appendChild(el('span', 'dl-said', f.note));
      }
      list.appendChild(item);
    });
    body.appendChild(list);
  }
  function scope(plan) {
    return 'All sessions in this database: ' + plan.sessions + ' session' +
      (plan.sessions === 1 ? '' : 's') + ', ' + plan.participants +
      ' participant' + (plan.participants === 1 ? '' : 's') +
      ', not only the session on this screen.';
  }
  function showConfirm(plan) {
    var inFolder = plan.mode === 'folder';
    var count = plan.files.filter(hasFile).length;
    var words = count === 1 ? 'one file' : count === 2 ? 'two files' : 'three files';
    show('Download data', 'Plain CSV files, not a zip.', function (body) {
      if (inFolder) {
        var lead = el('p', 'dl-lead', 'This will write ' + words + ' on the server, into ');
        lead.appendChild(el('span', 'dl-folder', plan.folder));
        body.appendChild(lead);
      } else {
        body.appendChild(el('p', 'dl-lead',
          'This will send ' + words + ' to this browser, one download per file.'));
      }
      listPlanned(plan, body);
      body.appendChild(el('p', 'dl-note', scope(plan)));
      (plan.warnings || []).forEach(function (w) {
        body.appendChild(el('div', 'qm-err', w));
      });
      if (inFolder) {
        body.appendChild(el('p', 'dl-note',
          'Nothing already in that folder is changed. If a name is taken, this set gets a number.'));
      } else {
        body.appendChild(el('p', 'dl-note',
          'Your browser may ask whether to allow multiple downloads. Please allow it.'));
      }
      actions(body, (inFolder ? 'Write ' : 'Download ') + howMany(count),
        function () { start(plan); }, 'Cancel');
    });
  }
  function start(plan) {
    busy = true;
    var waiting = plan.mode === 'folder' ? 'Writing the files\u2026' : 'Preparing the files\u2026';
    show('Download data', '', function (body) {
      body.appendChild(el('p', 'dl-lead', waiting));
    });
    var form = new URLSearchParams();
    form.append(plan.csrf_name, plan.csrf);
    ask(base + '/download', { method: 'POST', body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
      .then(function (answer) { busy = false; showAnswer(plan, answer); })
      .catch(function (err) {
        busy = false;
        showError('No answer from the server',
          'The server did not answer. It may still have written some files, so please check before relying on them. Pressing again is safe: nothing is ever overwritten. (' +
          (err && err.name ? err.name : 'error') + ')');
      });
  }
  function showProblem(answer) {
    if (answer.problem === 'login') { showLogin(answer.message); return; }
    if (answer.problem === 'not_available') {
      showError('Download data is not available',
        'This server did not install the download feature. The study itself is not affected. The reason is at the top of the server log.');
      return;
    }
    if (answer.problem === 'unreadable') {
      showError('The server had a problem',
        'The server gave an answer this page cannot read, so it may or may not have written files. Please check the folder and the server log. Pressing again is safe: nothing is ever overwritten.');
      return;
    }
    var title = answer.problem === 'no_data' ? 'Nothing to download'
      : 'No files were written';
    showError(title, answer.message || 'Something went wrong. Please try again.');
  }
  function showAnswer(plan, answer) {
    if (!answer.files || !answer.files.length) { showProblem(answer); return; }
    if (answer.mode === 'folder') showWritten(answer);
    else showSent(answer);
  }
  function rowsText(n) { return n + (n === 1 ? ' row' : ' rows'); }
  function verdictText(done, expected, verb) {
    if (done === expected) {
      return expected === 3 ? 'All 3 files ' + verb + '.'
        : expected === 2 ? 'Both files ' + verb + '.' : 'The file ' + verb + '.';
    }
    return done === 0 ? 'No files ' + verb + '.'
      : 'Only ' + done + ' of the ' + expected + ' files ' +
        (done === 1 ? verb.replace('were', 'was') : verb) + '.';
  }
  function showWritten(answer) {
    var expected = answer.files.filter(function (f) { return !f.skipped; }).length;
    var written = answer.files.filter(function (f) { return f.written; }).length;
    var all = written === expected;
    show('Download data', '', function (body) {
      body.appendChild(el('p', 'dl-verdict ' + (all ? 'good' : 'bad'),
        verdictText(written, expected, 'were written')));
      var list = el('ul', 'dl-files');
      answer.files.forEach(function (f) {
        var item = el('li', f.skipped ? 'none' : f.written ? 'good' : 'bad');
        item.appendChild(el('span', 'dl-kind', f.kind));
        if (f.skipped) {
          item.appendChild(el('span', 'dl-said', f.why));
        } else {
          item.appendChild(el('span', 'dl-what',
            f.written ? rowsText(f.rows) : 'not written'));
          item.appendChild(el('span', 'dl-path', f.path));
          if (!f.written) item.appendChild(el('span', 'dl-why', f.why || 'unknown reason'));
          else if (f.note) item.appendChild(el('span', 'dl-said', f.note));
        }
        list.appendChild(item);
      });
      body.appendChild(list);
      actions(body, null, null, 'Close');
    });
  }
  function showSent(answer) {
    releaseBlobs();
    var ready = [];
    show('Download data', '', function (body) {
      var expected = answer.files.filter(function (f) { return !f.skipped; }).length;
      var good = answer.files.filter(function (f) { return f.text !== null; }).length;
      var all = good === expected;
      var verdict = expected === 3 && all ? '3 files sent to the browser.'
        : good + ' of the ' + expected + ' files sent to the browser.';
      if (all && expected !== 3) {
        verdict = good + (good === 1 ? ' file' : ' files') + ' sent to the browser.';
      }
      body.appendChild(el('p', 'dl-verdict ' + (all ? 'good' : 'bad'), verdict));
      body.appendChild(el('p', 'dl-note',
        'The server cannot see whether they arrived, and it keeps no copy. If one is missing from your downloads, your browser may have blocked it: click its link here. These links stop working when you close this box.'));
      var list = el('ul', 'dl-files');
      answer.files.forEach(function (f) {
        var item = el('li', f.skipped ? 'none' : f.text !== null ? 'good' : 'bad');
        item.appendChild(el('span', 'dl-kind', f.kind));
        if (f.skipped) {
          item.appendChild(el('span', 'dl-said', f.why));
        } else if (f.text !== null) {
          item.appendChild(el('span', 'dl-what', rowsText(f.rows)));
          var url = URL.createObjectURL(new Blob([f.text], { type: 'text/csv;charset=utf-8' }));
          blobUrls.push(url);
          var link = el('a', 'dl-path', f.name);
          link.href = url;
          link.download = f.name;
          link.setAttribute('data-kind', f.kind);
          item.appendChild(link);
          if (f.note) item.appendChild(el('span', 'dl-said', f.note));
          ready.push(link);
        } else {
          item.appendChild(el('span', 'dl-what', 'not sent'));
          item.appendChild(el('span', 'dl-path', f.name));
          item.appendChild(el('span', 'dl-why', f.why || 'unknown reason'));
        }
        list.appendChild(item);
      });
      body.appendChild(list);
      actions(body, null, null, 'Close');
    });
    // One press, one click per file, spaced so browsers treat them as separate
    // downloads. Clicking the visible links is what the fallback does too.
    ready.forEach(function (link, i) {
      setTimeout(function () { link.click(); }, 300 + i * 500);
    });
  }
  opener.addEventListener('click', function () {
    // In the admin Report tab this page is an iframe starting below oTree's own
    // chrome, so a panel fixed inside it can end below the fold. Bring it up.
    try {
      if (window.frameElement) window.frameElement.scrollIntoView({ block: 'start' });
    } catch (e) { /* a frame we may not touch: the operator can scroll */ }
    show('Download data', '', function (body) {
      body.appendChild(el('p', 'dl-lead', 'Checking\u2026'));
      actions(body, null, null, 'Close');
    });
    ask(base + '/download_plan').then(function (plan) {
      if (plan.ok) showConfirm(plan);
      else showProblem(plan);
    }).catch(function (err) {
      showError('No answer from the server',
        'The server did not answer. Nothing was written. (' +
        (err && err.name ? err.name : 'error') + ')');
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay.classList.contains('open')) close();
  });
})();
"""
