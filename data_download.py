"""THE DASHBOARD'S "DOWNLOAD DATA" BUTTON: plain CSV files from one press.

Import as ``import data_download``. Stays at the project root, like
``experimenter_dashboard``, which puts the button on its page. Importing this
file pulls in the standard library only: oTree is imported inside the functions
that need it, so nothing here can take a boot down. See DECISIONS.md, 2026-11-05.

WHAT ONE PRESS MAKES (always every session in the database)
-----------------------------------------------------------
With no helper set, one file: SENSITIVE, oTree's wide export, byte for byte what
/ExportWide serves. The template's helper makes three:
  SENSITIVE  as above.
  ANONYMOUS  the same without the personal columns. Only if there is something to
             remove: otherwise it would be a raw copy that looks anonymised.
  PAYMENTS   as many of the payment columns as exist.

A study decides all of this in code, in `data_columns.py`: the switch
`DOWNLOAD_DATA_BUTTON` and the function `download_files`, whose docstring says what it
can do. This file only reads the export, checks what the function returned (see
`decide_files`), writes the files and answers the page. It assumes no file names:
a study's own kinds take the same path.

Named ``EXP_<lab session>_<DD-MM-YYYY><ending>[_2].csv``. No pandas: this runs on a
plain oTree install.

WHERE THEY GO: AN ENVIRONMENT VARIABLE, NEVER THE REQUEST
---------------------------------------------------------
``OTREE_DATA_FOLDER`` set: the server writes into ``<folder>/SENSITIVE`` and so
on. The base folder must already exist, so a typo gives an error naming it
rather than a new folder somewhere else; the subfolders are made when missing and
reused when present.

Not set (a hosted server): the one POST returns all the files and the page hands
them to the browser as separate downloads, so they come from one read of the
database and the server keeps no copy. The heading says "Data sent to the
browser" and no more, because the server cannot know whether they arrived.

THE RULES
---------
1. **The dashboard's two rules hold.** Nothing here writes to the database, which
   takes real care because the commit middleware commits on every request and a
   plain export dirties every row (see `_read_export`). A bug here breaks the button,
   never a participant page.
2. **LOGIN WHATEVER AUTH_LEVEL SAYS, AND CSRF WHATEVER THE ENVIRONMENT SAYS.** The
   dashboard opens up with AUTH_LEVEL unset, and oTree's AdminView skips CSRF
   under OTREE_SKIP_CSRF. Neither applies: these files hold bank details, so both
   checks are done here and an error in either answers 403.
3. **NEVER OVERWRITE.** See `write_set`.
4. **NEVER SILENT.** Every outcome is shown on the screen, file by file, and the
   heading claims only what was checked (see `file_state`, `result_heading`).
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


def file_name(stem, ending, number=1) -> str:
    """A set's numbers go at the very end, so a sorted folder keeps each kind
    together: EXP_217_05-11-2026_SENSITIVE_2.csv."""
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


def next_number(folder, stem, files) -> int:
    """The first number at which NONE of this set's names exists yet. A number is
    skipped if any one of them is taken, so a set stays together under one number
    even when an earlier press only wrote part of its set."""
    for number in range(1, MAX_SET_NUMBER + 1):
        if not any(os.path.lexists(os.path.join(
                folder, f['kind'], file_name(stem, f['ending'], number)))
                   for f in files):
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

    `built` holds one dict per file: `kind`, `ending`, `rows`, `note`,
    `note_columns`, and `data` (bytes), or `why` and `skipped` when there is no file
    (see `decide_files`).

    THE SAME ALGORITHM ON EVERY OPERATING SYSTEM, deliberately: this runs on the
    lab's Windows machines and is tested on Linux, so a branch per platform would
    mean the branch that matters was never run.

      1. Every file is written in full to a temp name. This is where most
         failures happen, before any final name exists.
      2. A number is chosen with no name taken, then each final name is taken
         with O_CREAT | O_EXCL, a real create-only that no other press can win
         too. Losing it means a concurrent press got there first: let go of what
         this attempt holds and try the next number, so the set stays together.
      3. Each temp is moved onto its own placeholder. A reader can see an empty
         file for an instant, never half a file, and a failed move removes the
         placeholder.

    A FILE THAT CANNOT BE WRITTEN DOES NOT STOP THE OTHERS. Export is the rescue
    path: with one subfolder broken, the ones that can be saved are saved, and the
    screen says which is missing and why. A retry gets a new number.
    """
    results = {}
    ready = []
    endings = {item['kind']: item['ending'] for item in built}
    for item in built:
        kind = item['kind']
        results[kind] = dict(kind=kind, rows=item.get('rows', 0), written=False,
                             path=None, name=file_name(stem, item['ending']),
                             why=item.get('why'),
                             skipped=item.get('skipped', False),
                             note=item.get('note'),
                             note_columns=item.get('note_columns'))
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
            number = next_number(folder, stem, built)
        while ready:
            taken = []
            lost_the_race = False
            for entry in list(ready):
                kind, sub, temp = entry
                final = os.path.join(sub, file_name(stem, endings[kind], number))
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
                number = next_number(folder, stem, built)
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

    # One consistent set on the screen: a file that failed writing is listed under
    # the name it would have had, with the number the others got. A file that was
    # never going to exist has no path to show.
    for item in built:
        kind = item['kind']
        result = results[kind]
        result['name'] = file_name(stem, item['ending'], number)
        result['path'] = (None if item.get('data') is None
                          else os.path.join(folder, kind, result['name']))
    return [results[item['kind']] for item in built]


# =============================================================================
# THE FILES, FROM oTREE'S OWN WIDE EXPORT
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


def _read_export() -> list:
    """Every session's wide rows, and the files a study makes of them. Runs in a
    worker thread, under oTree's lock.

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

    THE STUDY'S HELPER RUNS HERE TOO, not with the disk work after the lock. It may
    read the database (a chat log in `session._vars`), which must see committed data
    and is not safe once the lock has gone; and this guard covers anything it marks
    as changed, whatever its author wrote. The price is that a slow helper holds up
    participant pages, which its docstring says.
    """
    from otree.database import db
    reader = _checked_export()
    session = db._db
    try:
        with session.no_autoflush:
            return decide_files(check_rows(reader(None)))
    finally:
        session.rollback()


def _csv_bytes(rows) -> bytes:
    """The same writer oTree's export uses: `csv.writer` with its defaults, CRLF
    line ends, UTF-8 without a BOM. The tests compare this byte for byte against
    /ExportWide. newline='' keeps Windows from turning CRLF into CRCRLF."""
    buffer = io.StringIO(newline='')
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode('utf-8')


def encode_files(parts) -> list:
    """`decide_files`' answer as dicts for `write_set` or the browser. A table that
    cannot become a CSV is that file's failure, and the others still come."""
    built = []
    for part in parts:
        item = {name: part[name] for name in (
            'kind', 'ending', 'rows', 'why', 'skipped', 'note', 'note_columns')}
        item['data'] = None
        if part['table'] is not None:
            try:
                item['data'] = _csv_bytes(part['table'])
            except Exception as exc:                           # noqa: BLE001
                _log_failure(f'the {part["kind"]} file', exc)
                item['why'] = f'could not be turned into a CSV ({type(exc).__name__})'
        built.append(item)
    return built


def build_files(rows) -> list:
    return encode_files(decide_files(rows))


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
# WHAT THE SCREEN CLAIMS
# =============================================================================

def file_state(skipped, done) -> str:
    """One file's outcome: 'done', 'skipped' or 'failed'.

    A SKIP AND A FAILURE BOTH MEAN "NO FILE", AND BOTH GET A RED X, because Julian
    asked to see at a glance that a file is not there. They stay two states all the
    way to the screen (CLAUDE.md, the collapsed-distinction rule). A skip is the rule
    working: this data has nothing to anonymise, the heading stays "Data saved", and
    there is nothing to do. A failure means a file somebody needs is missing, and
    they have to act. Collapsed, a study with a renamed `outro` would read "Data
    saved" with no anonymous file, and nobody would add the column to the list; or
    every plain study would read as broken, and people would learn to ignore the
    red. So the page styles them differently and only a failure changes the heading.
    """
    if skipped:
        return 'skipped'
    return 'done' if done else 'failed'


def result_heading(mode, files) -> str:
    """The heading of the result, from the states of the files. It claims only what
    was checked. In a folder the server wrote the files, so "saved" is true. In the
    browser it handed them over and cannot see them land, so it never says "saved".
    """
    states = [f['state'] for f in files]
    verb = 'saved' if mode == 'folder' else 'sent'
    if 'done' not in states:
        return f'Nothing was {verb}'
    if 'failed' in states:
        return f'Some files were not {verb}'
    return 'Data saved' if mode == 'folder' else 'Data sent to the browser'


# =============================================================================
# WHAT A STUDY'S HELPER DECIDES (data_columns.download_files)
# =============================================================================

_HELPER_KEYS = {'kind', 'ending', 'table', 'skipped', 'why', 'note', 'note_columns'}
_SAFE_KIND = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
_SAFE_ENDING = re.compile(r'^[A-Za-z0-9_-]*$')
# Not a real kind (it has a space, which a helper's kind cannot), so no subfolder.
_HELPER_FAILED_KIND = 'OTHER FILES'


def problem_with_files(files):
    """What is wrong with a helper's answer, in plain words, or None. Names files by
    position and kind and tables by position, never by what a cell holds."""
    if not isinstance(files, (list, tuple)):
        return f'it returned {type(files).__name__}, not a list of files'
    if not files:
        return 'it returned an empty list, so no files'
    kinds, endings = set(), set()
    for number, file in enumerate(files, 1):
        where = f'file {number}'
        if not isinstance(file, dict):
            return f'{where} is {type(file).__name__}, not a dict'
        unknown = sorted(str(key) for key in set(file) - _HELPER_KEYS)
        if unknown:
            return (f'{where} has {", ".join(unknown)}, which the button does not '
                    f'know. It knows {", ".join(sorted(_HELPER_KEYS))}')
        kind = file.get('kind')
        if not isinstance(kind, str) or not _SAFE_KIND.match(kind):
            return (f'{where} needs a kind made of letters, digits, _ and -, because '
                    f'it names a folder (it has {str(kind)[:40]!r})')
        where = f'{where} ({kind})'
        if kind in kinds:
            return f'{where} has the same kind as an earlier file'
        kinds.add(kind)
        ending = file.get('ending', f'_{kind}')
        if not isinstance(ending, str) or not _SAFE_ENDING.match(ending):
            return f'{where} needs an ending made of letters, digits, _ and -'
        if ending in endings:
            return f'{where} has the same file name ending as an earlier file'
        endings.add(ending)
        for key in ('why', 'note', 'note_columns'):
            if file.get(key) is not None and not isinstance(file[key], str):
                return f'{where} needs its {key} to be text'
        table = file.get('table')
        if table is None:
            if not file.get('why'):
                return f'{where} has no table, and no why saying there is no file'
            continue
        if file.get('why') or file.get('skipped'):
            return f'{where} has a table, and also says there is no file'
        if not isinstance(table, (list, tuple)) or not table:
            return f'{where} needs its table to be a list of rows, header first'
        header = table[0]
        if (not isinstance(header, (list, tuple)) or not header
                or not all(isinstance(name, str) for name in header)):
            return f'{where} needs the first row of its table to be a header of text'
        for at, row in enumerate(table, 1):
            if not isinstance(row, (list, tuple)):
                return f'{where}: row {at} of its table is not a list'
            if len(row) != len(header):
                return (f'{where}: row {at} of its table has {len(row)} cells and '
                        f'the header has {len(header)}')
    return None


def _file_part(kind, ending, table=None, skipped=False, why=None, note=None,
               note_columns=None) -> dict:
    return dict(kind=kind, ending=ending, table=table, skipped=bool(skipped), why=why,
                note=note, note_columns=note_columns,
                rows=0 if table is None else len(table) - 1)


def decide_files(rows) -> list:
    """The files of one press, from the study's helper, every one in one shape.

    NO HELPER (None, or the line deleted): the raw wide export and nothing else, with
    no row for a file nobody asked for. So a study with no setup still gets its data.

    A HELPER THAT FAILS DOES NOT COST THE RAW FILE. It is written outside the helper's
    reach (the helper gets a copy of the rows, so it cannot have changed them), and
    the failure gets its own row, so the heading says it: raises and bad answers alike.
    Its answer is used whole or not at all, because half of a study's files with no
    word about the rest is how a missing file goes unnoticed. The text on the screen
    is the type only: `_failure_message` says why.
    """
    raw = _file_part('SENSITIVE', '_SENSITIVE', table=rows)
    helper = getattr(data_columns, 'DOWNLOAD_HELPER', None)
    if helper is None:
        return [raw]
    try:
        files = helper([list(row) for row in rows])
    except Exception as exc:                                   # noqa: BLE001
        _log_failure('the download helper', exc)
        return [raw, _file_part(_HELPER_FAILED_KIND, '', why=(
            f'the helper in data_columns.py raised {type(exc).__name__} (the details '
            f'are in the server log), so only the raw SENSITIVE file is made'))]
    problem = problem_with_files(files)
    if problem:
        return [raw, _file_part(_HELPER_FAILED_KIND, '', why=(
            f'the helper in data_columns.py cannot be used: {problem}. So only the '
            f'raw SENSITIVE file is made'))]
    return [_file_part(**dict(file, ending=file.get('ending', f'_{file["kind"]}')))
            for file in files]


# =============================================================================
# THE SWITCH
# =============================================================================

def button_is_on() -> bool:
    """data_columns.DOWNLOAD_DATA_BUTTON. Read at every use, and on unless a study
    says otherwise: with no setup at all it writes the raw file, which does no harm."""
    return bool(getattr(data_columns, 'DOWNLOAD_DATA_BUTTON', True))


# =============================================================================
# THE TWO ANSWERS
# =============================================================================

def build_plan(facts, parts) -> dict:
    """What a press would do right now, for the confirmation step: the same rules
    on the same export, so what it says about each file is what a press will do.
    Writes nothing and touches no folder but to look. Runs after the lock has been
    released. `parts` is None when there are no participants."""
    plan = dict(ok=True, mode='browser', folder=None, warnings=[], files=[],
                sessions=facts['sessions'], participants=facts['participants'],
                session_participants=facts['session_participants'],
                lab_session=facts['lab_session'])
    if parts is None:
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
        number = next_number(folder, facts['stem'], parts)

    for part in parts:
        kind = part['kind']
        name = file_name(facts['stem'], part['ending'], number)
        entry = dict(kind=kind, name=name, rows=part['rows'], path=None,
                     why=part['why'], skipped=part['skipped'], note=part['note'],
                     note_columns=part['note_columns'])
        if folder is not None and part['table'] is not None:
            sub = os.path.join(folder, kind)
            entry['path'] = os.path.join(sub, name)
            if os.path.exists(sub) and not os.path.isdir(sub):
                entry['why'] = 'a file is in the way of that folder'
        # 'planned', not 'done': nothing has happened yet.
        entry['state'] = ('skipped' if entry['skipped']
                          else 'failed' if entry['why'] else 'planned')
        plan['files'].append(entry)
    return plan


def run_download(parts, stem) -> dict:
    """Encode the files and send them where the setting says. Runs after the
    lock has been released, and re-reads the setting at this moment."""
    folder, problem = folder_setting()
    if folder is not None:
        problem = problem or folder_problem(folder)
        if problem:
            return dict(ok=False, mode='folder', folder=folder, problem='folder',
                        message=problem, files=[])

    built = encode_files(parts)
    if folder is None:
        files = [dict(kind=item['kind'], rows=item['rows'], why=item['why'],
                      skipped=item['skipped'], note=item['note'],
                      note_columns=item['note_columns'],
                      name=file_name(stem, item['ending']),
                      state=file_state(item['skipped'], item['data'] is not None),
                      text=(item['data'].decode('utf-8')
                            if item['data'] is not None else None))
                 for item in built]
        return dict(ok=all(f['state'] != 'failed' for f in files), mode='browser',
                    heading=result_heading('browser', files), folder=None, files=files)

    files = write_set(folder, stem, built)
    for f in files:
        f['state'] = file_state(f['skipped'], f['written'])
    return dict(ok=all(f['state'] != 'failed' for f in files), mode='folder',
                heading=result_heading('folder', files), folder=folder, files=files)


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
            # Switched off in code while this route exists: refuse, plainly.
            if not button_is_on():
                return refusal(404, 'off', 'The Download data button is switched '
                               "off in this study's code (data_columns.py).")
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
                parts = await run_in_threadpool(_read_export)
            except NoData:
                parts = None

            def work():
                return dict(build_plan(facts, parts), csrf_name=csrf_name, csrf=token)
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
                parts = await run_in_threadpool(_read_export)
            except NoData:
                return JSONResponse(
                    dict(ok=False, problem='no_data', message=NO_DATA_MESSAGE,
                         files=[]), headers=NO_STORE)
            return in_the_stream(lambda: run_download(parts, facts['stem']),
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
    said out loud here too, so it is seen at launch, not at the end of a session.
    Switched off in code: nothing is installed and nothing is said."""
    if not button_is_on():
        return 'off'
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
    """(label, current, must_be) for scripts/prelaunch_check.py. Never raises. A
    button switched off in code has nothing to report."""
    if not button_is_on():
        return []
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
# THE PAGE: PUT IN THE DASHBOARD'S PAGE BY experimenter_dashboard.py
# =============================================================================

PAGE_BUTTON = """<button class="dl-open" id="dl-open" type="button"
            title="Save this database's data as CSV files. You confirm first.">Download data</button>"""

# Empty until the button is pressed. Its script is a separate block, so a mistake in
# it cannot stop the poll that paints the table.
PAGE_OVERLAY = '<div class="qm-overlay" id="dl-overlay" aria-hidden="true"></div>'


def page_parts() -> dict:
    """What the dashboard's page carries of this button: all of it, or with the
    switch off none of it."""
    if not button_is_on():
        return dict(button='', overlay='', css='', js='')
    return dict(button=PAGE_BUTTON, overlay=PAGE_OVERLAY, css=PAGE_CSS, js=PAGE_JS)


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
/* INTENTION: one row per file, scannable at a glance, the same on the confirm step
   and on both results: a mark in a fixed left column, the name, then the small
   print. The state classes come from data_download.file_state.
     planned  a grey tick: nothing has happened yet, so nothing looks done
     done     a green tick
     skipped  a red X on a plain row: no file, as expected. Nothing to do.
     failed   a white X on a red disc, on a tinted row, in red words: a file somebody
              needs is missing. Must never look the same as skipped (see file_state).
              The tint is .qm-err's. */
.dl-files { list-style: none; margin: 0; padding: 0; }
.dl-files li { display: grid; grid-template-columns: 22px minmax(0, 1fr);
  column-gap: 10px; border: 1px solid var(--line); border-radius: var(--r-sm);
  padding: 9px 13px; margin-bottom: 8px; font-size: .92rem; }
.dl-mark { display: flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%; font-size: 1.05rem;
  font-weight: 800; line-height: 1; }
.dl-files li.planned .dl-mark { color: var(--ink-mute); }
.dl-files li.done .dl-mark { color: var(--ok); }
.dl-files li.skipped .dl-mark { color: var(--danger); }
.dl-files li.failed { border-color: var(--danger); background: #fdeaec; }
.dl-files li.failed .dl-mark { background: var(--danger); color: #fff;
  font-size: .85rem; }
.dl-words { align-self: center; min-width: 0; }
.dl-kind { font-weight: 700; color: var(--ink); }
.dl-rows, .dl-reason { color: var(--ink-soft); }
.dl-files li.failed .dl-kind, .dl-files li.failed .dl-reason {
  color: var(--danger); font-weight: 650; overflow-wrap: anywhere; }
.dl-path { display: block; margin-top: 2px; color: var(--ink-soft);
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
               "Liberation Mono", monospace;
  font-size: .76rem; overflow-wrap: anywhere; }
a.dl-path { color: var(--accent); }
/* INTENTION: something to know about a file that is there. The yellow and the amber
   are the timing pill's (.spill-stall), wrapping because a list can be long. */
.dl-warn { display: block; margin-top: 6px; padding: 3px 9px; background: #fff3c9;
  border: 1px solid #eab308; border-radius: var(--r-sm); color: var(--dash-amber);
  font-size: .84rem; font-weight: 650; }
.dl-actions { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.dl-primary { font: inherit; font-size: 1rem; font-weight: 700; cursor: pointer;
  border: none; background: var(--accent); color: #fff;
  border-radius: var(--r-sm); padding: 10px 22px; }
.dl-primary:hover { background: var(--accent-hover); }
.dl-primary:disabled { background: var(--line-strong); cursor: default; }
/* The result's heading: the panel's own title, in the colour of what happened. */
.qm-head h2.dl-verdict { margin: 0; font-size: 1.25rem; font-weight: 700; }
.qm-head h2.dl-verdict.good { color: var(--ok); }
.qm-head h2.dl-verdict.bad { color: var(--danger); }
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
  function show(title, fill, titleClass) {
    var panel = el('div', 'qm-panel dl-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', title);
    var head = el('div', 'qm-head');
    var words = el('div');
    words.appendChild(el('h2', titleClass || '', title));
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
    show(title, function (body) {
      body.appendChild(el('div', 'qm-err', message));
      actions(body, null, null, 'Close');
    });
  }
  function showLogin(message) {
    show('Log in first', function (body) {
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
  function howMany(n) {
    return n === 1 ? 'the file' : 'the ' + n + ' files';
  }
  function rowsText(n) { return n + (n === 1 ? ' row' : ' rows'); }
  // The mark and the name of one file, the same on every screen. `f.state` comes
  // from the server, and a skip and a failure stay apart here too: see file_state
  // in data_download.py for why, and the INTENTION comment above .dl-files.
  var MARKS = {
    planned: ['✓', 'Will be made'],
    done: ['✓', 'Done'],
    skipped: ['✗', 'No file, as expected for this data'],
    failed: ['✗', 'Failed: a file is missing']
  };
  function fileRow(f, notMade, where) {
    var item = el('li', f.state);
    item.setAttribute('data-kind', f.kind);
    var mark = el('span', 'dl-mark', MARKS[f.state][0]);
    mark.title = MARKS[f.state][1];
    mark.setAttribute('role', 'img');
    mark.setAttribute('aria-label', MARKS[f.state][1]);
    item.appendChild(mark);
    var words = el('div', 'dl-words');
    if (f.state === 'skipped') {
      words.appendChild(el('span', 'dl-kind', f.kind + ': '));
      words.appendChild(el('span', 'dl-reason', f.why));
    } else if (f.state === 'failed') {
      words.appendChild(el('span', 'dl-kind', f.kind + ' ' + notMade + ': '));
      words.appendChild(el('span', 'dl-reason', f.why || 'unknown reason'));
    } else {
      words.appendChild(el('span', 'dl-kind', f.kind));
      words.appendChild(el('span', 'dl-rows', ' (' + rowsText(f.rows) + ')'));
    }
    if (where) words.appendChild(where);
    if (f.note && f.state !== 'failed') {
      var warn = el('span', 'dl-warn', f.note);
      if (f.note_columns) warn.title = f.note_columns;
      words.appendChild(warn);
    }
    item.appendChild(words);
    return item;
  }
  function pathOf(text) { return text ? el('span', 'dl-path', text) : null; }
  function scope(plan) {
    return 'All sessions in this database: ' + plan.sessions + ' session' +
      (plan.sessions === 1 ? '' : 's') + ', ' + plan.participants +
      ' participant' + (plan.participants === 1 ? '' : 's') +
      ', not only the session on this screen.';
  }
  function showConfirm(plan) {
    var inFolder = plan.mode === 'folder';
    var count = plan.files.filter(function (f) { return f.state === 'planned'; }).length;
    show('Download data', function (body) {
      if (inFolder) {
        var lead = el('p', 'dl-lead', 'Saves on the server, in ');
        lead.appendChild(el('span', 'dl-folder', plan.folder));
        body.appendChild(lead);
      } else {
        body.appendChild(el('p', 'dl-lead',
          'Sends to this browser, one download per file.'));
      }
      var list = el('ul', 'dl-files');
      plan.files.forEach(function (f) {
        list.appendChild(fileRow(f, inFolder ? 'will not be saved' : 'will not be sent',
          pathOf(f.path || (f.state === 'planned' ? f.name : null))));
      });
      body.appendChild(list);
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
      actions(body, count ? (inFolder ? 'Save ' : 'Download ') + howMany(count) : null,
        function () { start(plan); }, 'Cancel');
    });
  }
  function start(plan) {
    busy = true;
    var waiting = plan.mode === 'folder' ? 'Saving the files\u2026' : 'Preparing the files\u2026';
    show('Download data', function (body) {
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
  function showProblem(answer, plan) {
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
      : plan && plan.mode === 'browser' ? 'Nothing was sent' : 'Nothing was saved';
    showError(title, answer.message || 'Something went wrong. Please try again.');
  }
  function showAnswer(plan, answer) {
    if (!answer.files || !answer.files.length) { showProblem(answer, plan); return; }
    if (answer.mode === 'folder') showWritten(answer);
    else showSent(answer);
  }
  function verdictClass(answer) { return 'dl-verdict ' + (answer.ok ? 'good' : 'bad'); }
  function showWritten(answer) {
    show(answer.heading, function (body) {
      var list = el('ul', 'dl-files');
      answer.files.forEach(function (f) {
        list.appendChild(fileRow(f, 'not saved', pathOf(f.path)));
      });
      body.appendChild(list);
      actions(body, null, null, 'Close');
    }, verdictClass(answer));
  }
  function showSent(answer) {
    releaseBlobs();
    var ready = [];
    show(answer.heading, function (body) {
      body.appendChild(el('p', 'dl-note',
        'The server cannot see whether they arrived, and it keeps no copy. If one is missing from your downloads, your browser may have blocked it: click its link here. These links stop working when you close this box.'));
      var list = el('ul', 'dl-files');
      answer.files.forEach(function (f) {
        var link = null;
        if (f.state === 'done') {
          var url = URL.createObjectURL(new Blob([f.text], { type: 'text/csv;charset=utf-8' }));
          blobUrls.push(url);
          link = el('a', 'dl-path', f.name);
          link.href = url;
          link.download = f.name;
          link.setAttribute('data-kind', f.kind);
          ready.push(link);
        }
        list.appendChild(fileRow(f, 'not sent', link));
      });
      body.appendChild(list);
      actions(body, null, null, 'Close');
    }, verdictClass(answer));
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
    show('Download data', function (body) {
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
