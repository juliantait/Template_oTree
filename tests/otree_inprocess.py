"""Boot oTree IN-PROCESS against a throwaway database.

Shared by the tests in this folder that need more than an HTTP client can reach:
the session config as stored in the database (frozen-config simulation), the
model rows behind a page, and the DEBUG/production switch. `http_flow_test.py`,
`gated_flow_test.py` and `device_gate_test.py` drive a server you started
yourself; these drive oTree's own ASGI app inside the test process.

    from otree_inprocess import boot
    ot = boot(production=True)          # DEBUG off = what participants get
    session = ot.create_session('prolific', num_participants=2)

Two traps this exists to get right, both learnt the hard way (see
`skills_claude/writing_tests.md`):

1. **The database.** oTree opens the RELATIVE name `db.sqlite3` in the CURRENT
   DIRECTORY at import time (`otree/database.py`: `DB_FILE`,
   `sqlite_disk_conn = get_disk_conn()`), and IGNORES the path inside a sqlite
   `DATABASE_URL`. Setting the env var alone would run the test against the
   project's own dev database. So `otree.database` is imported while chdir'd
   into a temp directory, and only then does the working directory go back to
   the project root — which it must, because `_static/` and the template roots
   are equally CWD-relative.

2. **DEBUG.** `settings.py` derives `DEBUG = 'OTREE_PRODUCTION' not in
   os.environ` — presence, not value. `OTREE_PRODUCTION=''` therefore means
   PRODUCTION here, while oTree's own default derivation would call it debug.
   Pass `production=` and let this module set or pop the variable.

Everything must happen before `otree_main.setup()` loads the app models, so call
`boot()` before importing any app module.
"""
import os
import sys
import tempfile

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(_TESTS_DIR)


class OTree:
    """Handle on a booted oTree: the app, a client factory and the ORM."""

    def __init__(self, tmpdir, production):
        self.tmpdir = tmpdir
        self.production = production

    def client(self):
        from starlette.testclient import TestClient
        from otree.asgi import app
        # raise_server_exceptions=False so a 500 comes back as a RESPONSE to
        # assert on, exactly as a participant's browser would receive it,
        # instead of exploding the test run.
        return TestClient(app, raise_server_exceptions=False)

    @staticmethod
    def create_session(config_name, num_participants=2, **kwargs):
        from otree.session import create_session as _create
        return _create(config_name, num_participants=num_participants, **kwargs)

    @staticmethod
    def participant_codes(session):
        from otree.database import DBSession
        from otree.models import Participant
        s = DBSession()
        try:
            return [p.code for p in s.query(Participant)
                    .filter_by(_session_code=session.code)
                    .order_by(Participant.id).all()]
        finally:
            s.close()

    @staticmethod
    def participant_vars(code):
        """A plain dict copy of one participant's vars blob."""
        from otree.database import DBSession
        from otree.models import Participant
        s = DBSession()
        try:
            return dict(s.query(Participant).filter_by(code=code).one().vars)
        finally:
            s.close()

    @staticmethod
    def set_label(code, label):
        from otree.database import DBSession
        from otree.models import Participant
        s = DBSession()
        try:
            p = s.query(Participant).filter_by(code=code).one()
            p.label = label
            s.commit()
        finally:
            s.close()

    @staticmethod
    def anon_code(session):
        from otree.database import DBSession
        from otree.models import Session
        s = DBSession()
        try:
            return s.query(Session).filter_by(
                code=session.code).one()._anonymous_code
        finally:
            s.close()

    @staticmethod
    def strip_config_keys(session, keys):
        """Delete keys from a session's STORED config.

        This is how a frozen config is simulated: oTree copies the config onto
        the Session row at creation and never refreshes it, so a parameter added
        to settings.py later is simply absent for a session already running.
        Returns the keys that were actually there to remove.
        """
        from otree.database import DBSession
        from otree.models import Session
        missing = object()
        s = DBSession()
        try:
            row = s.query(Session).filter_by(code=session.code).one()
            cfg = dict(row.config)
            removed = [k for k in keys if cfg.pop(k, missing) is not missing]
            row.config = cfg      # reassign so the pickled column is dirty
            s.commit()
            return removed
        finally:
            s.close()


def boot(production=True):
    """Import oTree against a throwaway sqlite database and return an OTree."""
    tmpdir = tempfile.mkdtemp(prefix='otree_inprocess_')
    os.environ['DATABASE_URL'] = f"sqlite:///{os.path.join(tmpdir, 'db.sqlite3')}"
    os.environ.setdefault('OTREE_SECRET_KEY', 'inprocess-test')
    if production:
        os.environ['OTREE_PRODUCTION'] = '1'
    else:
        os.environ.pop('OTREE_PRODUCTION', None)

    if APP_ROOT not in sys.path:
        sys.path.insert(0, APP_ROOT)
    if _TESTS_DIR not in sys.path:
        sys.path.insert(0, _TESTS_DIR)

    os.chdir(tmpdir)
    import otree.database  # noqa: F401  (binds the connection to the temp file)
    os.chdir(APP_ROOT)

    import otree.main as otree_main
    otree_main.setup()

    from otree.database import engine, AnyModel
    AnyModel.metadata.create_all(engine)

    return OTree(tmpdir, production)


# --------------------------------------------------------------------------
# small shared helpers for walking a participant with the in-process client
# --------------------------------------------------------------------------
def path_of(resp):
    from urllib.parse import urlparse
    return urlparse(str(resp.url)).path


def page_name_of(path):
    """/p/<code>/<app>/<PageName>/<index> -> PageName (None off the flow)."""
    parts = path.strip('/').split('/')
    return parts[3] if len(parts) >= 5 and parts[0] == 'p' else None
