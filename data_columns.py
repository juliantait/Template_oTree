"""WHAT THE "DOWNLOAD DATA" BUTTON DOWNLOADS, AND THE COLUMN LISTS, in one plain module.

**A study sets this up here, in code, and nowhere else.** The two settings and the
function a study edits come first: `DOWNLOAD_DATA_BUTTON`, `download_files`,
`DOWNLOAD_HELPER`. Below them are the template's own lists and rules.

Import as ``import data_columns``. Standard library only, no oTree, no pandas, no
web code: it takes the rows of oTree's wide export (a header row, then one list per
participant) and decides what goes in each file. So it can be read on its own, and
another study or app can reuse it. Today it has two callers:

  * ``data_download.py``, the dashboard's "Download data" button;
  * ``scripts/format_session_data.py``, which uses the lists only, and so is not
    affected by the two settings or by `download_files`.

Two copies of "what makes a file anonymous" would drift, and the drift would show
up as a bank number in a file somebody shared. See DECISIONS.md, 2026-11-05.

THE TEMPLATE'S RULES (`split_export` is all of them, in this order)
-------------------------------------------------------------------
1. SENSITIVE is always made: the raw wide export, unchanged.

2. ANONYMOUS is made only if there is something to remove.
     * Nothing to remove means none of the personal columns in ANON_DROP_COLUMNS
       is in the export. The file would be a copy of the raw data that looks
       anonymised, which is misleading, so no file, and the screen says why, with
       a red X: expected, and still something Julian wants to see at a glance.
     * Two columns on the list do not count as "something to remove":
       `participant.label`, which every oTree export has, counts only when some row
       has a label; and `outro.1.player.earned`, which identifies nobody.
     * A column that looks personal but is not on the list (`payment.1.player.bank`
       after a study renamed `outro`) refuses the file. That one is a failure, and
       the person who sees it adds the column to the list.

3. PAYMENTS always has a file, with as many of PAYMENT_COLUMNS as exist, in that
   order. The participant code alone still counts as a file. The columns that do not
   exist are named on the screen, as a yellow warning in the PAYMENTS row. A column
   that exists and is empty is normal: a Prolific row has no IBAN, a lab row has no
   Prolific ID.
"""
import re

# ---------------------------------------------------------------------------
# WHAT A STUDY SETS. In code only: no session config key, nothing on any screen.
# ---------------------------------------------------------------------------

# True: the dashboard has the button. False: no button, its routes refuse, and
# nothing warns about OTREE_DATA_FOLDER at boot or in the launch check.
DOWNLOAD_DATA_BUTTON = True


def download_files(rows):
    """WHAT ONE PRESS OF "DOWNLOAD DATA" MAKES. Edit this for the data your study has.

    This is the whole setup. It is here so you can decide, for your study, which CSV
    files one press gives. There is no screen for it, on purpose.

    NO SETUP NEEDED. Set `DOWNLOAD_HELPER` (the line below this function) to None, or
    delete that line, and one press makes exactly one file: SENSITIVE, the raw wide
    export. This template keeps the line because its data has bank, BIC and Prolific
    columns, so its version makes SENSITIVE, ANONYMOUS and PAYMENTS (`split_export`).

    WHAT THE DATA COVERS. `rows` is oTree's wide export, for every session in the
    database: fields on Player, Group and Subsession, plus PARTICIPANT_FIELDS and
    SESSION_FIELDS. Anything else is NOT in it, such as what is kept only in
    `session.vars` or `participant.vars` (a chat log, say), unless you add it here.
    Example 4 does that.

    TAKES `rows`, a list of lists: `rows[0]` is the header and each other row is one
    participant. It is your own copy, so you may change it.

    RETURNS a list with one dict per file:
      kind          required. The subfolder, and the name on the screen. Letters,
                    digits, `_` and `-`.
      table         the rows to write, header first, every row as long as the header.
      ending        the end of the file name. Default `_<kind>`. Each file's must
                    differ. The template's ANONYMOUS uses '', so it has none.
      note          a short yellow warning on the file's row.
      note_columns  hover text for that warning.
    For a file that is deliberately not made, give no table and:
      why           the reason, in a few words.
      skipped       True if that is correct for this data: a calm red X, the heading
                    stays "Data saved". Left out: it is a failure, and the heading
                    says so.

    WHAT THE BUTTON DOES WITH IT. Every file takes the same path: the confirm step
    lists it first, nothing is ever overwritten, one press gets one set number, and
    the screen reports each file. If this function raises, or returns something the
    button cannot use, the raw SENSITIVE file is still made and the screen shows the
    failure, naming the problem. Nothing else in the study is affected.

    KEEP IT QUICK AND READ-ONLY. It runs under oTree's global lock, so participant
    pages wait while it runs, and it runs on every press and every confirm step.
    Anything it changes in the database is thrown away. Read vars as `session._vars`,
    never `session.vars`: oTree's `.vars` marks the row as changed on every read.

    Example 1, a computed total added to PAYMENTS:

        def download_files(rows):
            files = split_export(rows)
            fee = rows[0].index('session.config.participation_fee')
            payoff = rows[0].index('participant.payoff')
            totals = [float(row[fee] or 0) + float(row[payoff] or 0) for row in rows[1:]]
            for file in files:
                if file['kind'] == 'PAYMENTS':
                    table = file['table']
                    file['table'] = [table[0] + ['total_earned']] + [
                        row + [total] for row, total in zip(table[1:], totals)]
            return files

    Example 2, no anonymous file:

        def download_files(rows):
            return [file for file in split_export(rows) if file['kind'] != 'ANONYMOUS']

    Example 3, one more file, with one app's columns:

        def download_files(rows):
            keep = [i for i, name in enumerate(rows[0])
                    if name == 'participant.code' or name.startswith('main.')]
            return split_export(rows) + [
                dict(kind='MAIN', table=[[row[i] for i in keep] for row in rows])]

    Example 4, one more file, from a chat log kept in session.vars:

        def download_files(rows):
            from otree.database import db
            from otree.models import Session
            table = [['session.code', 'sender', 'text']]
            for session in db.query(Session):
                for sender, text in session._vars.get('chat_log', []):
                    table.append([session.code, sender, text])
            return split_export(rows) + [dict(kind='CHAT', table=table)]

    A file you add this way is yours: the check for personal columns in `split_export`
    only covers ANONYMOUS, so do not put anything personal in a file you plan to share.
    """
    return split_export(rows)


# The function the button calls. None, or no such line: one raw SENSITIVE file.
DOWNLOAD_HELPER = download_files

# ---------------------------------------------------------------------------
# THE LISTS
# ---------------------------------------------------------------------------

# Removed from every anonymous file: bank details, the label, the Prolific IDs.
# `participant.code` stays, as the key that links back to the sensitive file.
ANON_DROP_COLUMNS = (
    'outro.1.player.bank',
    'outro.1.player.bank_confirmation',
    'outro.1.player.bic',
    'outro.1.player.earned',
    'participant.label',
    'participant.participant_id_external',
    'before.1.player.participant_label',
    'before.1.player.participant_id_url',
    'before.1.player.participant_id_external',
    'before.1.player.prolific_label_conflict',
)

# Kept as a column with every cell empty. This is the template's free JSON bucket,
# and it can NAME a Prolific ID: a refused claim records the id that was refused and
# a duplicate records the label (identity.py). `format_session_data.py` blanks it in
# all its files too, so the anonymous files of the two tools agree on it. It is the
# only column blanked here: feedback and device details stay, by Julian's decision
# (DECISIONS.md, the Download data entry).
ANON_BLANK_COLUMNS = (
    'participant.participant_extra',
)

# On the drop list but no reason on their own to make an anonymous file (rule 2).
_NOT_A_REASON = ('outro.1.player.earned', 'participant.label')

# Field names that look personal wherever they turn up, beyond those on the drop
# list, in the spellings a study not built from this template might use.
_ALSO_LOOKS_PERSONAL = ('iban', 'iban_confirmation', 'prolific_id', 'prolific_pid')

# The payment file, in this order, with what the screen calls each column.
#   participant.code                     the unique participant id
#   participant.participant_id_external  the Prolific ID as CONFIRMED by the
#                                        participant, "the value payment should use"
#                                        (CODEBOOK). Empty in a lab session.
#   outro.1.player.bank, .bic            IBAN and BIC. Empty on Prolific.
#   outro.1.player.earned                the total: show-up fee + selected rounds +
#                                        quiz bonus. NOT participant.payoff, which
#                                        is earned minus participation_fee.
#   before.1.player.prolific_label_conflict  a triage flag, not a payment detail.
#                                        Empty, normally. If set, this person's
#                                        Prolific ID claim was refused, so the ID on
#                                        their row also belongs to someone else, and
#                                        this cell is the code of that other row.
#                                        Look at both before paying either. Still on
#                                        the drop list above, so never in ANONYMOUS.
PAYMENT_COLUMNS = (
    'participant.code',
    'participant.participant_id_external',
    'outro.1.player.bank',
    'outro.1.player.bic',
    'outro.1.player.earned',
    'before.1.player.prolific_label_conflict',
)
PAYMENT_LABELS = {
    'participant.code': 'participant code',
    'participant.participant_id_external': 'Prolific ID',
    'outro.1.player.bank': 'IBAN',
    'outro.1.player.bic': 'BIC',
    'outro.1.player.earned': 'total earned',
    'before.1.player.prolific_label_conflict': 'Prolific ID conflict',
}

# `format_session_data.py`'s payment file, which also carries the label and keeps
# the order it has always had. The button leaves the label out: it is a seat number
# in the lab, not something a payment needs.
FORMAT_PAYMENT_COLUMNS = (
    'participant.code',
    'participant.label',
    'participant.participant_id_external',
    'outro.1.player.earned',
    'outro.1.player.bank',
    'outro.1.player.bic',
)

NO_ANONYMOUS_FILE = 'no IBAN, BIC or Prolific columns in this data'

# ---------------------------------------------------------------------------
# THE RULES
# ---------------------------------------------------------------------------

_PERSONAL_FIELDS = sorted(
    {name.rsplit('.', 1)[1] for name in ANON_DROP_COLUMNS} - {'earned'}
    | set(_ALSO_LOOKS_PERSONAL))
_PERSONAL_COLUMN = re.compile(
    r'^(?:participant|[^.]+\.\d+\.player)\.(?:%s)$'
    % '|'.join(re.escape(field) for field in _PERSONAL_FIELDS))


def personal_columns_left(header):
    """Columns that look personal, are in `header` and are not on the drop list."""
    return [name for name in header
            if name not in ANON_DROP_COLUMNS and _PERSONAL_COLUMN.match(name)]


def has_something_to_remove(header, data_rows):
    """Rule 2: would an anonymous file differ from the raw data in a way that
    matters? Decided on the columns, and for the label on whether any row has one."""
    if any(name in ANON_DROP_COLUMNS and name not in _NOT_A_REASON for name in header):
        return True
    if 'participant.label' in header:
        where = header.index('participant.label')
        return any(row[where] not in ('', None) for row in data_rows)
    return False


def anonymous_table(rows):
    """The rows without the drop list, with ANON_BLANK_COLUMNS emptied."""
    header = rows[0]
    keep = [i for i, name in enumerate(header) if name not in ANON_DROP_COLUMNS]
    blank = {i for i in keep if header[i] in ANON_BLANK_COLUMNS}
    return ([[header[i] for i in keep]]
            + [['' if i in blank else row[i] for i in keep] for row in rows[1:]])


def payment_columns_present(header):
    return [name for name in PAYMENT_COLUMNS if name in header]


def payment_columns_missing(header):
    return [name for name in PAYMENT_COLUMNS if name not in header]


def payments_table(rows):
    """As many of PAYMENT_COLUMNS as exist, in that order, for every row."""
    where = [rows[0].index(name) for name in payment_columns_present(rows[0])]
    return [[row[i] for i in where] for row in rows]


def split_export(rows):
    """The three files from one export: the rules above, in one place.

    Returns one dict per file, SENSITIVE, ANONYMOUS, PAYMENTS, in the shape
    `download_files` returns:
      kind     the file's name in capitals
      ending   the end of the file's name
      table    the rows to write, or None when there is no file
      skipped  True: no file, and that is correct (rule 2). False with `why` set:
               no file, and that is a failure. Both get a red X on the screen,
               and data_download.file_state keeps them apart.
      why      why there is no file, in plain words
      note     a warning about a file that is written, in the screen's short words
      note_columns  the raw column names behind `note`, for its hover text only
    """
    header, data_rows = rows[0], rows[1:]

    def entry(kind, ending, table=None, skipped=False, why=None, note=None,
              note_columns=None):
        return dict(kind=kind, ending=ending, table=table, skipped=skipped,
                    why=why, note=note, note_columns=note_columns)

    sensitive = entry('SENSITIVE', '_SENSITIVE', table=rows)

    leftover = personal_columns_left(header)
    if leftover:
        anonymous = entry('ANONYMOUS', '', why=(
            'these columns look personal and are not on the list in '
            f'data_columns.py: {", ".join(leftover)}'))
    elif not has_something_to_remove(header, data_rows):
        anonymous = entry('ANONYMOUS', '', skipped=True, why=NO_ANONYMOUS_FILE)
    else:
        anonymous = entry('ANONYMOUS', '', table=anonymous_table(rows))

    missing = payment_columns_missing(header)
    note = note_columns = None
    if missing:
        note = ('Did not exist in this data: '
                + ', '.join(PAYMENT_LABELS[name] for name in missing))
        note_columns = ', '.join(missing)
    payments = entry('PAYMENTS', '_PAYMENTS', table=payments_table(rows), note=note,
                     note_columns=note_columns)
    return [sensitive, anonymous, payments]
