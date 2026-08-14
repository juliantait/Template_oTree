#!/usr/bin/env python3
"""Report whether the database oTree is configured to use is ALREADY INITIALISED.

This is the boot guard's oracle. The container's CMD must initialise a database
exactly once — on a genuinely empty one — and must NEVER re-initialise a database
that already holds participant data, because `otree resetdb` is destructive:
otree/cli/resetdb.py reflects the target database and calls `drop_all()` on it,
so "initialise" means "drop every table that is there, then create empty ones".

WHAT THIS GUARD IS ACTUALLY FOR (verified against otree 6.0.15)
---------------------------------------------------------------
Not creating tables. oTree creates its own: `otree.main.setup()` calls
`init_orm()`, which ends in `AnyModel.metadata.create_all(engine)`
(otree/database.py:369) on EVERY `prodserver` start, and `create_all` is
checkfirst-by-default — it adds missing tables and never drops or alters an
existing one. So the `needs-init` branch is belt and braces; the server would
have built its own schema anyway.

The guard's whole value is therefore NEGATIVE: it is what stops `resetdb` from
running against a database that has data in it. Read that way, refusing to act
when the answer is unclear is not an inconvenience, it is the entire job.

WHY THIS SCRIPT EXISTS AT ALL (the defect it replaces)
------------------------------------------------------
The guard used to ask `[ ! -f /app/data/db.sqlite3 ]` — "is there a sqlite file?"
— as a proxy for "is this database new?". The proxy only holds when the database
IS that file. Point DATABASE_URL at a managed Postgres and the sqlite file never
exists, so the proxy answers "new" on EVERY boot and every container restart
wipes the Postgres database, silently, with no error in the log. The proxy is not
even reliable for sqlite: importing otree.database opens
`sqlite3.connect('db.sqlite3')` at module scope (otree/database.py, unconditional
— it happens even when DATABASE_URL points at Postgres), which CREATES a
zero-byte file. A zero-byte db.sqlite3 is a file that exists and a database that
was never initialised; file existence cannot tell those apart either.

So this script asks the question the guard actually means: DOES THE DATABASE
oTree WILL CONNECT TO ALREADY CONTAIN OTREE'S TABLES? That question has the same
meaning on sqlite, on Postgres, and on anything else SQLAlchemy can reach.

HOW IT ASKS — BY REUSING OTREE'S OWN ENGINE, NOT BY RESOLVING THE URL AGAIN
---------------------------------------------------------------------------
The engine is `otree.database.engine` itself: the very object the server will
use, already resolved by oTree's own rules —
`os.getenv('DATABASE_URL', 'sqlite:///db.sqlite3')`, and for sqlite a
`creator=lambda: sqlite_disk_conn` that opens the literal RELATIVE name
`db.sqlite3` in the process CWD, ignoring whatever path the URL contains.

Re-deriving that here — reading DATABASE_URL ourselves, re-applying the sqlite
relative-path rule — would be a SECOND implementation of "which database is
this?", and this repo has been bitten by that shape twice already (participant
identity in SQL vs Python; the predeploy check's shell vs helper). The two copies
drift, and here the drift means the probe blesses one database while the server
wipes another. There is no second copy: whatever oTree resolves, this inspects.
The corollary is that this script MUST run with the same CWD as the server
(/app), which is what the Dockerfile CMD does.

The expected table names come from `AnyModel.metadata` — oTree's own declarative
registry — for the same reason: a hardcoded 'otree_participant' would drift the
day oTree renames one.

OUTCOMES — four situations, deliberately kept apart
---------------------------------------------------
  stdout `needs-init`,         exit 0 : the database contains NO tables at all.
                                        Safe to initialise; nothing to destroy.
  stdout `already-initialised`, exit 0: oTree's tables are present. Keep the data.
  exit 3 (refusal)                    : the database has tables, but NONE of them
                                        are oTree's. This is NOT "empty", and it
                                        is NOT an oTree database — it may be
                                        another application's schema, or an oTree
                                        database from a version that named its
                                        tables differently. resetdb here would
                                        drop_all() somebody else's tables. Refuse
                                        and make a human decide (RESET_DB=1).
  exit 2 (cannot determine)           : the question could not be answered — no
                                        driver, database still unreachable after
                                        the wait below, oTree's registry empty
                                        (version drift), an in-memory engine. NOT
                                        the same as "empty", and collapsing the
                                        two is how this class of bug wipes a
                                        database: an unreachable Postgres would
                                        read as "brand new".

WAITING BEFORE REFUSING — a cold start is not a verdict
--------------------------------------------------------
A managed Postgres is very often not accepting connections at the instant the
container starts: the platform starts both at once, the database is still
provisioning, or a pooler is not up yet. Refusing immediately would turn a normal
cold start into a failed deploy, so a database that does not answer is retried
(DB_WAIT_ATTEMPTS x DB_WAIT_SECONDS, default 30 x 2s = one minute) before it is
called unanswerable. Refuse-to-boot stays the right direction; it just has to be
the verdict after waiting, not the first answer.

Only "the database did not answer" is retried. A missing driver, an empty model
registry, an in-memory engine or a foreign schema are all answers already — they
will say exactly the same thing in sixty seconds, so they fail immediately rather
than making an operator watch a pointless minute of retries. (Same distinction as
everywhere else in this codebase: not-yet-available and definitively-wrong are
different states.)

Run it from the app directory. Diagnostics go to stderr; stdout carries the
answer and nothing else. No password is ever printed.
"""
import contextlib
import os
import re
import sys
import time

# A cold-starting managed database is normal; an absent one is not. Overridable
# for a platform that is slower than this, without editing the image.
WAIT_ATTEMPTS = int(os.environ.get('DB_WAIT_ATTEMPTS', '30'))
WAIT_SECONDS = float(os.environ.get('DB_WAIT_SECONDS', '2'))


def _mask(text) -> str:
    """Redact any database password before it can reach a log.

    Two layers, because neither is sufficient alone: the pattern catches
    credentials embedded in URLs that appear inside driver messages, and the
    literal replacement catches a password echoed on its own (some drivers
    include the whole conninfo). `docker logs` is not a secret store.
    """
    s = str(text)
    s = re.sub(r'(://[^:/@\s]+):[^@\s]+@', r'\1:***@', s)
    raw = os.environ.get('DATABASE_URL', '')
    if raw:
        try:
            from sqlalchemy.engine.url import make_url
            pw = make_url(raw).password
            if pw:
                s = s.replace(str(pw), '***')
        except Exception:
            # Never let redaction failure become the visible error — but do not
            # print the message either, since it is what we failed to redact.
            if '://' in raw and '@' in raw:
                return '<message withheld: could not redact the database URL>'
    return s


# stdout is the machine-readable channel — the caller captures it in `$(...)`.
# settings.py prints its prelaunch banner at import, and oTree logs during
# startup, so every import below runs with stdout pointed at stderr. Without
# this, the banner would be captured as part of the answer. The banner is not
# suppressed, just re-routed: it still reaches `docker logs`.
@contextlib.contextmanager
def _stdout_to_stderr():
    saved = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = saved


def _cannot_determine(reason: str):
    sys.stderr.write(
        "\n"
        "########################################################################\n"
        "##  DATABASE STATE UNKNOWN — refusing to initialise.\n"
        f"##  {_mask(reason)}\n"
        "##\n"
        "##  Not initialising, because 'I cannot see the database' and 'the\n"
        "##  database is empty' are different things, and `otree resetdb` drops\n"
        "##  every table it finds. Fix the cause (DATABASE_URL, network, driver,\n"
        "##  credentials). If the database really is empty and you want it built\n"
        "##  from scratch, say so explicitly: RESET_DB=1.\n"
        "########################################################################\n"
    )
    sys.exit(2)


def _table_names(engine):
    """Ask the database for its tables, waiting out a cold start.

    Returns the set of table names, or raises the last error if the database
    never answered.
    """
    import sqlalchemy
    from sqlalchemy import exc as sa_exc

    # "Did not answer" — a connection-level failure, which is what a database
    # that is still starting looks like. A schema or programming error is NOT
    # in here on purpose: those are answers, and repeating them wastes a minute.
    not_answering = (sa_exc.OperationalError, sa_exc.InterfaceError,
                     sa_exc.DBAPIError)

    last = None
    for attempt in range(1, WAIT_ATTEMPTS + 1):
        try:
            with _stdout_to_stderr():
                return set(sqlalchemy.inspect(engine).get_table_names())
        except not_answering as exc:
            last = exc
            if attempt == 1:
                sys.stderr.write(
                    f"[boot] the database is not answering yet "
                    f"({_mask(exc.__class__.__name__)}); waiting up to "
                    f"{int(WAIT_ATTEMPTS * WAIT_SECONDS)}s for it to accept "
                    f"connections before giving up.\n"
                )
            elif attempt % 5 == 0:
                sys.stderr.write(
                    f"[boot] still waiting for the database "
                    f"({attempt}/{WAIT_ATTEMPTS})...\n"
                )
            if attempt < WAIT_ATTEMPTS:
                time.sleep(WAIT_SECONDS)
    raise last


def main() -> None:
    # An in-memory engine is a scratch database that is empty BY CONSTRUCTION;
    # asking it about tables tells you nothing about the real one, and the answer
    # would always be 'needs-init'. oTree sets OTREE_IN_MEMORY for `devserver_inner`
    # and `bots` (otree/main.py); it must never be set for the production boot.
    if os.environ.get('OTREE_IN_MEMORY'):
        _cannot_determine(
            "OTREE_IN_MEMORY is set, so oTree's engine points at a throwaway "
            "in-memory database, not at the one this study runs on."
        )

    try:
        with _stdout_to_stderr():
            from otree.database import engine, AnyModel
            # AnyModel.metadata is EMPTY until the model modules are imported —
            # verified against otree 6.0.15. Importing otree.database alone
            # yields zero known tables, which would read as 'oTree owns nothing
            # here'. This import is what makes the registry authoritative.
            import otree.models  # noqa: F401
    except SystemExit:
        # oTree exits (rather than raising) when it cannot find settings.py or
        # when the database needs attention. Its own message is already on
        # stderr; do not let that exit code masquerade as an answer.
        _cannot_determine(
            "oTree exited while loading. Run this from the app directory "
            "(the one containing settings.py)."
        )
    except Exception as exc:  # driver missing, settings broken, import error
        # The template's own image installs psycopg2-binary, so a missing driver
        # should not happen there — but this script also runs outside that image
        # (a study that edited the Dockerfile, a host-side check), and a
        # ModuleNotFoundError raised from inside SQLAlchemy is not a readable
        # diagnosis. Name the likely cause instead of making someone decode it.
        _cannot_determine(
            f"could not load oTree's database layer: {exc!r}. If DATABASE_URL "
            f"names a backend other than sqlite, check that its driver is "
            f"installed (this template's image ships psycopg2-binary for "
            f"Postgres)."
        )

    # oTree's own names for oTree's own tables. Never hardcode these.
    otree_tables = set(AnyModel.metadata.tables)
    if not otree_tables:
        # Loud on purpose: this is version drift, not an empty database. If oTree
        # ever stops registering its tables here, the intersection below would be
        # empty for EVERY database and this guard would recommend wiping live data.
        _cannot_determine(
            "oTree's model registry reports no tables of its own, so there is "
            "nothing to look for. This is a change in oTree's internals "
            "(AnyModel.metadata), not a state of your database — this script "
            "needs updating for the installed oTree version."
        )

    backend = engine.url.get_backend_name()
    try:
        present = _table_names(engine)
    except Exception as exc:
        _cannot_determine(
            f"the {backend} database at {repr(engine.url)} never answered: "
            f"{exc!r}"
        )

    if otree_tables & present:
        print('already-initialised')
        return

    if present:
        sys.stderr.write(
            "\n"
            "########################################################################\n"
            "##  DATABASE IS NOT EMPTY AND IS NOT AN OTREE DATABASE — refusing.\n"
            f"##  backend: {backend}\n"
            f"##  tables found: {', '.join(sorted(present)[:12])}"
            f"{' ...' if len(present) > 12 else ''}\n"
            "##\n"
            "##  None of oTree's tables are among them. `otree resetdb` reflects\n"
            "##  the database and drop_all()s it, so initialising here would\n"
            "##  destroy tables that belong to something else — or to an oTree\n"
            "##  version that named its tables differently.\n"
            "##\n"
            "##  Point DATABASE_URL at a database of this study's own, or, if\n"
            "##  these tables really are expendable, RESET_DB=1.\n"
            "########################################################################\n"
        )
        sys.exit(3)

    print('needs-init')


if __name__ == '__main__':
    main()
