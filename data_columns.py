"""THE COLUMN LISTS AND THE RULES FOR THE THREE DATA FILES, in one plain module.

Import as ``import data_columns``. Standard library only, no oTree, no pandas, no
web code: it takes the rows of oTree's wide export (a header row, then one list per
participant) and decides what goes in each file. So it can be read on its own, and
another study or app can reuse it. Today it has two callers:

  * ``data_download.py``, the dashboard's "Download data" button;
  * ``scripts/format_session_data.py``, which uses the lists only.

Two copies of "what makes a file anonymous" would drift, and the drift would show
up as a bank number in a file somebody shared. See DECISIONS.md, 2026-11-05.

THE RULES (`split_export` is all of them, in this order)
--------------------------------------------------------
1. SENSITIVE is always made: the raw wide export, unchanged.

2. ANONYMOUS is made only if there is something to remove.
     * Nothing to remove means none of the personal columns in ANON_DROP_COLUMNS
       is in the export. The file would be a copy of the raw data that looks
       anonymised, which is misleading, so no file, and the screen says why.
     * Two columns on the list do not count as "something to remove":
       `participant.label`, which every oTree export has, counts only when some row
       has a label; and `outro.1.player.earned`, which identifies nobody.
     * A column that looks personal but is not on the list (`payment.1.player.bank`
       after a study renamed `outro`) refuses the file. That one is a failure, and
       the person who sees it adds the column to the list.

3. PAYMENTS always has a file, with as many of PAYMENT_COLUMNS as exist, in that
   order. The participant code alone still counts as a file. The columns that do not
   exist are named on the screen. A column that exists and is empty is normal: a
   Prolific row has no IBAN, a lab row has no Prolific ID.
"""
import re

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
# all its files too, so the anonymous files of the two tools agree.
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
PAYMENT_COLUMNS = (
    'participant.code',
    'participant.participant_id_external',
    'outro.1.player.bank',
    'outro.1.player.bic',
    'outro.1.player.earned',
)
PAYMENT_LABELS = {
    'participant.code': 'participant code',
    'participant.participant_id_external': 'Prolific ID',
    'outro.1.player.bank': 'IBAN',
    'outro.1.player.bic': 'BIC',
    'outro.1.player.earned': 'total earned',
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

NO_ANONYMOUS_FILE = ('No anonymous file: this study has no IBAN, BIC or Prolific '
                     'columns, so it would only be a copy of the raw data.')

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

    Returns one dict per file, SENSITIVE, ANONYMOUS, PAYMENTS:
      kind     the file's name in capitals
      count    participant rows
      table    the rows to write, or None when there is no file
      skipped  True: no file, and that is correct (rule 2). The screen says why,
               calmly. False with `why` set: no file, and that is a failure.
      why      why there is no file, in plain words
      note     something to say about a file that is written
    """
    header, data_rows = rows[0], rows[1:]
    count = len(data_rows)

    def entry(kind, table=None, skipped=False, why=None, note=None):
        return dict(kind=kind, count=count, table=table, skipped=skipped,
                    why=why, note=note)

    sensitive = entry('SENSITIVE', table=rows)

    leftover = personal_columns_left(header)
    if leftover:
        anonymous = entry('ANONYMOUS', why=(
            'not written, to be safe: these columns look personal and are not on '
            f'the list in data_columns.py: {", ".join(leftover)}'))
    elif not has_something_to_remove(header, data_rows):
        anonymous = entry('ANONYMOUS', skipped=True, why=NO_ANONYMOUS_FILE)
    else:
        anonymous = entry('ANONYMOUS', table=anonymous_table(rows))

    missing = payment_columns_missing(header)
    note = None
    if missing:
        note = ('This study has no column for: '
                + ', '.join(f'{PAYMENT_LABELS[name]} ({name})' for name in missing)
                + '. The file has the columns that exist.')
    payments = entry('PAYMENTS', table=payments_table(rows), note=note)
    return [sensitive, anonymous, payments]
