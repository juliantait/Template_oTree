"""BUILD GUARD: oTree's built-in `participation_fee` must be zero.

WHY THIS EXISTS
===============

Same decision as `payoff_guard.py`, one field along: **one payment ledger.**
`participation_fee` is oTree's own second money channel — it is not added to
`participant.payoff`, it is added ON TOP of it wherever oTree reports payment
(`Session._get_payoff_plus_participation_fee`, otree/models/session.py:248; the
admin Payments page; the MTurk payment table; the `payoff_plus_participation_fee`
export column). A non-zero fee therefore splits the amount owed to a participant
across two numbers that live in different places and are computed by different
code — which is the exact condition the single-ledger decision exists to prevent.

This template already pays the base amount THROUGH the ledger: `showup` is a
session-config value that `outro.compute_final_payoff` folds into
`participant.payoff` along with the bonus, so the admin figure equals the amount
actually owed. Setting a `participation_fee` as well would pay part of the base
twice — once inside `earned`, once as oTree's separate addend — or, if the study
moved the base out of `showup`, would leave the ledger under-reporting it. Both
failures look like a working study right up until somebody pays people.

WHY A GUARD AND NOT JUST A ZERO IN settings.py
==============================================

Because a zero in a config is a convention, and **an unenforced convention in a
template drifts the first time somebody copies it.** `participation_fee` is a
standard oTree knob that every oTree tutorial sets; a researcher starting a study
from this template will meet it in oTree's own docs, set it in good faith, and
get a payment split they never intended and no error to tell them so. The
DECISIONS.md entry for the payoff ledger makes the same argument, and this repo
has already had one convention-only rule quietly break (three documents claiming
oTree's `player.payoff` raise was "enforcement" when it was not).

WHAT THIS CATCHES, AND WHAT IT DOES NOT
=======================================

Said plainly, because the gap matters and the honest statement is the point.

CAUGHT — the two places a build can carry a fee:
  * THE RESOLVED CONFIGS. `settings.SESSION_CONFIG_DEFAULTS` and every entry in
    `settings.SESSION_CONFIGS`, read as objects AFTER `resolve_recruitment_
    profile()` has run — i.e. the values oTree will actually use, not a guess at
    them from source. The defaults must carry an explicit `0`; a per-config entry
    may omit the key (it inherits) but must not set it to anything non-zero.
  * ANY SOURCE WRITE in a scanned app package or shared root module:
    `participation_fee = v`, `x.participation_fee = v`,
    `config['participation_fee'] = v`, a `participation_fee=v` keyword in any
    call (`dict(...)`, a config literal), and a `'participation_fee': v` dict
    entry. This is the half that catches a study that builds a config at runtime
    rather than declaring it.

NOT CAUGHT — and this one is REAL, not theoretical:
  * **THE ADMIN UI.** oTree ships `SessionEditPropertiesForm`
    (otree/views/admin.py:212) with `participation_fee` as an editable
    `DecimalField`, so an experimenter can set a fee on a LIVE SESSION from the
    browser, after boot, on a build this guard passed. No boot check can see
    that, and there is no hook to refuse it. The mitigation is that the session
    config view then disagrees with the shipped config, and `frozen_config_test`
    lists `participation_fee` among the keys it audits — but nothing prevents it.
    A study that pays out from the admin Payments page after somebody edited the
    fee will overpay. Say so in the handover; do not pretend the guard covers it.
  * Indirection a source scan is structurally blind to — a computed attribute
    name, a value assembled by `exec`, a fee injected by a library.

WHY THIS IS A BOOT CHECK AND NEVER A RUNTIME RAISE
==================================================

The `payoff_guard.py` precedent, and it is not negotiable in this codebase: a
check that fires inside a participant's request converts a bookkeeping problem
into a DEAD PAGE for whoever is mid-study when a build lands, and oTree has no
migrations, so an upgrade under live sessions is the normal way every study built
from this template is deployed. This raises at boot, before anybody is served,
where the operator sees it while the old build is still running.

THE KNOWN COST, ACCEPTED WITH EYES OPEN (Julian, 2026-08-14)
============================================================

**A study copied from this template that already sets a `participation_fee` will
refuse to boot** until the fee is moved into the ledger (put it in `showup`, or
add it wherever `outro.compute_final_payoff` computes `earned`). That is a real
cost, paid by a real person, and it is the point: the alternative is that the
study runs and the payment record is wrong in a way nobody notices until payout.
A refusal at boot is loud, immediate, and fixable in one line; a split ledger is
discovered by a participant who was underpaid.
"""
import ast
import os

import payoff_guard

_ROOT = os.path.dirname(os.path.abspath(__file__))

_KEY = 'participation_fee'


def _is_zero_value(value) -> bool:
    """Is this RESOLVED config value provably zero?

    Deliberately conservative, exactly as `payoff_guard._denotes_participant`
    is: anything that cannot be positively shown to be zero is treated as a fee.
    A false alarm costs a reviewer two minutes at deploy time; a miss costs a
    participant the difference between two payment figures.
    """
    if isinstance(value, bool):
        return False
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def _ast_is_zero(node) -> bool:
    """Is this AST value node a literal zero?

    `0`, `0.0`, `0.00` are zero. `cu(0)`, `Decimal('0')` or a name are NOT
    provably zero from source and are reported — the same conservative bias as
    above. If a study legitimately needs a computed zero, the resolved-config
    half is where it should be proven, not here.
    """
    return (isinstance(node, ast.Constant)
            and not isinstance(node.value, bool)
            and isinstance(node.value, (int, float))
            and node.value == 0)


def _target_names_fee(node) -> bool:
    """Does this assignment target write the participation_fee key/attribute?"""
    if isinstance(node, ast.Name):
        return node.id == _KEY
    if isinstance(node, ast.Attribute):
        return node.attr == _KEY
    if isinstance(node, ast.Subscript):
        # `session.config['participation_fee'] = …`
        index = node.slice
        return isinstance(index, ast.Constant) and index.value == _KEY
    return False


def _scan_tree(tree, rel):
    """Every non-zero `participation_fee` write in one parsed module."""
    found = []

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            elements = (list(target.elts)
                        if isinstance(target, (ast.Tuple, ast.List))
                        else [target])
            for element in elements:
                if _target_names_fee(element) and not _ast_is_zero(
                        getattr(node, 'value', None)):
                    found.append((rel, element.lineno,
                                  f'{ast.unparse(element)} = '
                                  f'{ast.unparse(node.value)}'))

        # `dict(participation_fee=5)` / `SessionConfig(participation_fee=5)` —
        # how a session config is actually written in settings.py.
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == _KEY and not _ast_is_zero(kw.value):
                    found.append((rel, kw.value.lineno,
                                  f'{_KEY}={ast.unparse(kw.value)}'))

        # `{'participation_fee': 5}`
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value == _KEY
                        and not _ast_is_zero(value)):
                    found.append((rel, key.lineno,
                                  f'{_KEY!r}: {ast.unparse(value)}'))
    return found


def find_fee_writes(root=None):
    """Return (writes, unreadable) — the two answers, kept apart on purpose.

    Same split, and the same reason, as
    `payoff_guard.find_player_payoff_writes`: "this file sets a fee" and "this
    guard could not answer for this file" are different facts about a build.

    The file LIST comes from `payoff_guard.files_to_scan`, not from a second
    copy of the rule. What counts as a scanned app package is one concept, and
    this codebase has been bitten repeatedly by one concept with two
    implementations — if the two guards ever disagreed about which directories
    are apps, one of them would be silently exempting code from its check.
    """
    root = root or _ROOT
    writes, unreadable = [], []
    for path in payoff_guard.files_to_scan(root):
        rel = os.path.relpath(path, root).replace(os.sep, '/')
        try:
            with open(path, encoding='utf-8') as fh:
                source = fh.read()
            tree = ast.parse(source, filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as exc:
            unreadable.append((rel, f'{type(exc).__name__}: {exc}'))
            continue
        writes.extend(_scan_tree(tree, rel))
    return writes, unreadable


def find_nonzero_fee_configs(defaults=None, configs=None):
    """Non-zero fees in the RESOLVED session configs — the authoritative half.

    Reads the settings module's own objects rather than its source, because a
    profile resolves into explicit config keys AT IMPORT
    (`resolve_recruitment_profile`), so the source and the resolved value are
    not the same thing. Returns a list of (where, value) problems.
    """
    if defaults is None or configs is None:
        import settings as project_settings
        if defaults is None:
            defaults = getattr(project_settings, 'SESSION_CONFIG_DEFAULTS', None)
        if configs is None:
            configs = getattr(project_settings, 'SESSION_CONFIGS', None)

    problems = []
    if not isinstance(defaults, dict):
        problems.append(('SESSION_CONFIG_DEFAULTS', 'missing or not a dict'))
        return problems

    # The defaults must carry the key EXPLICITLY. oTree requires it at session
    # creation (otree/session.py:79 required_keys), and the template's own rule
    # is that a config resolves to explicit values rather than implied ones.
    if _KEY not in defaults:
        problems.append(('SESSION_CONFIG_DEFAULTS',
                         f'{_KEY} is absent; it must be present and 0'))
    elif not _is_zero_value(defaults[_KEY]):
        problems.append(('SESSION_CONFIG_DEFAULTS', repr(defaults[_KEY])))

    for cfg in (configs or []):
        if not isinstance(cfg, dict) or _KEY not in cfg:
            continue  # omitting the key is fine: it inherits the zero default
        if not _is_zero_value(cfg[_KEY]):
            problems.append((f"SESSION_CONFIGS[{cfg.get('name', '?')!r}]",
                             repr(cfg[_KEY])))
    return problems


def assert_participation_fee_is_zero(root=None, defaults=None, configs=None):
    """THE SINGLE PLACE A NON-ZERO participation_fee IS A FAILURE. Raises at boot.

    Called from `before/__init__.py` beside
    `payoff_guard.assert_no_player_payoff_writes()`, for the same reason and with
    the same trade: fail the BOOT, never a participant's page.

    Returns the number of files scanned, so a caller can tell "clean" from
    "scanned nothing".
    """
    root = root or _ROOT

    problems = find_nonzero_fee_configs(defaults=defaults, configs=configs)
    if problems:
        listing = '\n'.join(f'    {where}: {value}' for where, value in problems)
        raise RuntimeError(
            "fee_guard.assert_participation_fee_is_zero: this build sets "
            "oTree's built-in participation_fee to something other than 0, and "
            "the boot is being refused.\n"
            f"{listing}\n"
            "participation_fee is a SECOND payment channel: oTree adds it on "
            "top of participant.payoff wherever it reports what is owed (the "
            "admin Payments page, payoff_plus_participation_fee, the export "
            "column). This template keeps ONE ledger — the base is paid through "
            "`showup`, which outro.compute_final_payoff folds into "
            "participant.payoff with the bonus — so a fee here splits the "
            "amount owed across two numbers and somebody gets paid the wrong "
            "one.\n"
            "If this is a study copied from the template that already had a "
            "fee: move it into the ledger (add it to `showup`, or into the "
            "`earned` computation in outro) and set participation_fee back to "
            "0. See DECISIONS.md, 'participation_fee ships 0, and a boot guard "
            "holds it there'.")

    writes, unreadable = find_fee_writes(root)
    if writes:
        listing = '\n'.join(f'    {rel}:{line}  {text}'
                            for rel, line, text in writes)
        raise RuntimeError(
            "fee_guard.assert_participation_fee_is_zero: this build assigns "
            "oTree's participation_fee somewhere other than a literal 0, and "
            "the boot is being refused rather than letting a second payment "
            "channel open quietly.\n"
            f"{listing}\n"
            "One payment ledger: the base belongs in `showup` and the total in "
            "participant.payoff. If the value really is zero but computed, make "
            "it a literal 0 here and compute elsewhere. See DECISIONS.md, "
            "'participation_fee ships 0, and a boot guard holds it there'.")

    if unreadable:
        listing = '\n'.join(f'    {rel}  {reason}' for rel, reason in unreadable)
        raise RuntimeError(
            "fee_guard.assert_participation_fee_is_zero: could not read or "
            "parse part of this build, so it CANNOT SAY whether anything sets "
            "a participation_fee. This is not a fee finding — it is a broken "
            "source tree.\n"
            f"{listing}")

    return len(payoff_guard.files_to_scan(root))
