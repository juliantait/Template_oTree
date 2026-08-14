"""BUILD GUARD: no app module may write oTree's per-round `player.payoff`.

WHY THIS EXISTS — AND WHY THE RAISE IT REPLACES IS NOT A SAFETY FEATURE
=======================================================================

Reported by the exp_pilots bossman (2026-08-14), verified against the installed
oTree before acting on it. The one-payment-ledger decision sets
`settings.AUTO_TABULATE_PAYOFFS = False`, and that flag makes oTree's OWN
`player.payoff` SETTER raise — otree/models/player.py:41-46 in the installed
6.0.15:

    @payoff.setter
    def payoff(self, value):
        if not settings.AUTO_TABULATE_PAYOFFS:
            raise Exception(
                "Don't set player.payoff; modify participant.payoff directly.")

Three documents in this repo used to present that raise as the enforcement —
"the old habit is now IMPOSSIBLE rather than discouraged". It is not
enforcement. It is oTree's code, we cannot remove it, and **it fires inside a
participant's request**: on a page, mid-round, at the moment somebody submits.

oTree has no migrations, so the realistic failure is an UPGRADE UNDER LIVE
SESSIONS — the way every study built from this template is actually deployed. A
new build introduces a `player.payoff` write; the first person mid-round to
reach that code path does not get a bookkeeping error, they get a DEAD PAGE. So
the flag alone converts a CONDITIONAL data problem (one ledger quietly drifting
into two) into a CERTAIN outage for whoever happens to be mid-study when the
build lands. Trading a maybe-wrong number for a definitely-broken page is a bad
trade, and it slipped through because a raise reads as the strict, careful
option.

This repo has already refused exactly this trade twice, both recorded in
DECISIONS.md:

  * `identity.install_duplicate_label_guard` must fail QUIETLY at its early
    install point (cannot-import-yet is not drift); and
  * `identity.assert_duplicate_label_guard` is deliberately NOT on the
    participant entry path — "a missing guard is a CONDITIONAL risk; raising on
    the entry path would turn it into a CERTAIN outage for every participant".

The answer there is the answer here: **catch it EARLIER, at boot, where loud is
what loud should mean for a server.** A build containing a `player.payoff` write
refuses to start. The operator sees it at deploy time, while the old build is
still serving; a participant never sees it at all. oTree's raise stays where it
is as the last-ditch backstop for a path this scan cannot see — it is the floor,
not the guard.

WHAT THIS CATCHES, AND WHAT IT DOES NOT
=======================================

Said plainly, because the gap is the entire reason there is a SECOND check.

CAUGHT — every syntactic write, in every scanned file, whether or not any test
ever walks that line: `x.payoff = v`, `x.payoff += v`, `x.payoff: T = v`, and
`setattr(x, 'payoff', v)` with a literal name.

NOT CAUGHT — indirection, which is what a source scan is structurally blind to:
`setattr(obj, name, v)` with a computed name, a write inside a library, a write
built by `exec`. Those are covered from the other side by
`tests/payoff_ledger_test.py` §7, which walks a real journey and then asserts
the underlying `_payoff` column is still untouched on every round row. That test
is blind to code no walk reaches; this scan is blind to indirection. Their blind
spots are disjoint, which is why BOTH exist and neither replaces the other.

WHY AST, NOT A REGEX (this one is not a style preference)
=========================================================

The string `player.payoff` appears all over this codebase IN COMMENTS AND
DOCSTRINGS — main/__init__.py, outro/__init__.py, settings.py, this very file —
because the decision is documented where it is enforced. A regex scan would
refuse to boot over prose. `ast.parse` sees code and nothing else. Parsing is
also SIDE-EFFECT FREE, which matters: `intro/generate_instructions_preview.py`
sits inside an app package and imports a browser driver at module level, so a
scan that imported what it checked would be a far more fragile thing to run at
boot than one that reads text.

`participant.payoff` AND `player.payoff` ARE TWO FIELDS SHARING A NAME
=====================================================================

The collapsed-distinction rule, right at the centre of this check.
`p.participant.payoff = cu(target)` in `outro.compute_final_payoff` is THE ONE
LEGITIMATE WRITE in the whole template — it is the single-ledger decision
itself. A check keyed on the attribute name alone would refuse to boot over the
line the decision exists to protect. So the base expression is tested
explicitly (`_denotes_participant`) and the two are kept apart. Do not
"simplify" that away.
"""
import ast
import os

_ROOT = os.path.dirname(os.path.abspath(__file__))

# WHAT IS SCANNED: every oTree app package (a directory holding `__init__.py`)
# plus the shared root-level modules those apps import. An app not currently in
# any `app_sequence` is scanned too — it is one config edit away from being
# live, and this is a build check, not a coverage check.
#
# WHAT IS NOT, AND WHY EXACTLY THESE THREE. `tests/` and `scripts/` have no
# `__init__.py` today, so the package rule already skips them — but
# `tests/payoff_ledger_test.py` DELIBERATELY writes `pl.payoff = 5` to prove
# oTree's setter still raises. If somebody ever adds `tests/__init__.py` the
# rule would silently pull that line in and refuse the boot over the test that
# proves the guard works, so it is named here rather than left to luck.
#
# THE LIST IS SHORT ON PURPOSE. `prolific/`, `previews/`, `ideas/`, `_ai/`,
# `_static/`, `skills_claude/` are NOT listed even though nothing in them
# should ever be scanned: they are not packages, so they are skipped anyway,
# and naming them would create a real hazard — an app later called `prolific`
# would be silently exempted from the guard, which is the failure mode this
# module exists to prevent. Exclude by what a directory IS, not by what it is
# called.
_EXCLUDED_DIRS = {'tests', 'scripts', '__pycache__'}

_ATTR = 'payoff'


def _denotes_participant(node) -> bool:
    """Does this expression denote a PARTICIPANT rather than a player row?

    `participant.payoff` is oTree's cross-round ledger and the one field this
    template writes on purpose; `player.payoff` is the per-round field whose
    setter raises. Same attribute name, two different fields — see the module
    docstring. Deliberately conservative: anything this cannot positively
    identify as a participant is treated as a player row and reported, because
    a false alarm costs a reviewer two minutes at deploy time and a miss costs a
    participant their page.
    """
    if isinstance(node, ast.Name):
        return node.id == 'participant'
    if isinstance(node, ast.Attribute):
        # `p.participant`, `player.participant`, `self.participant`, …
        return node.attr == 'participant'
    return False


def _write_target(node):
    """If `node` is an assignment target writing `.payoff`, return its base."""
    if isinstance(node, ast.Attribute) and node.attr == _ATTR:
        return node
    return None


def _scan_tree(tree, rel):
    """Every `.payoff` write in one parsed module, as (line, source-ish) pairs."""
    found = []

    def report(lineno, text):
        found.append((rel, lineno, text))

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.For):
            # `for x.payoff in …` is legal Python and is a write.
            targets = [node.target]
        for target in targets:
            # A tuple/list target unpacks into several writes: `a.payoff, b = …`
            elements = (list(target.elts)
                        if isinstance(target, (ast.Tuple, ast.List))
                        else [target])
            for element in elements:
                attr = _write_target(element)
                if attr is not None and not _denotes_participant(attr.value):
                    report(attr.lineno,
                           f'{ast.unparse(attr)} = …')

        # `setattr(x, 'payoff', v)` — the indirection this CAN see. A computed
        # name (`setattr(x, name, v)`) is the half it cannot; that half belongs
        # to tests/payoff_ledger_test.py §7.
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'setattr'
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == _ATTR
                and not _denotes_participant(node.args[0])):
            report(node.lineno, f'setattr({ast.unparse(node.args[0])}, '
                                f'{_ATTR!r}, …)')
    return found


def files_to_scan(root=None):
    """The app-package and shared-module sources this guard reads."""
    root = root or _ROOT
    paths = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isfile(full) and name.endswith('.py'):
            paths.append(full)
        elif (os.path.isdir(full) and name not in _EXCLUDED_DIRS
              and os.path.isfile(os.path.join(full, '__init__.py'))):
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = sorted(d for d in dirnames
                                     if d not in _EXCLUDED_DIRS)
                paths.extend(os.path.join(dirpath, f)
                             for f in sorted(filenames) if f.endswith('.py'))
    return sorted(paths)


def find_player_payoff_writes(root=None):
    """Return (writes, unreadable) — the two answers, kept apart on purpose.

    `writes`      — [(relative path, line, rendered expression)] for every
                    `.payoff` write whose base is not a participant.
    `unreadable`  — [(relative path, reason)] for a file that could not be READ
                    or PARSED, which is NOT the same finding and must not be
                    reported as one (the cannot-import-yet vs symbol-drifted
                    split, in its third incarnation here). "This file contains a
                    forbidden write" and "this guard could not answer for this
                    file" are different facts about a build, and collapsing them
                    would let a syntax error read as a clean scan or a clean
                    scan read as a payoff bug.
    """
    root = root or _ROOT
    writes, unreadable = [], []
    for path in files_to_scan(root):
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


def assert_no_player_payoff_writes(root=None):
    """THE SINGLE PLACE A `player.payoff` WRITE IS A FAILURE. Raises at boot.

    WHERE THIS IS CALLED, AND WHY THERE. From `before/__init__.py`, beside
    `identity.assert_duplicate_label_guard()` and for the same reason: it fails
    the BOOT, before a single participant is served. `before` is first in every
    `app_sequence`, so this runs before any other app module is imported — and
    because the check reads SOURCE rather than imported modules, import order
    cannot make it miss anything.

    Deliberately NOT at request time. Request time is where oTree's own raise
    already lands, and that is precisely the problem this is here to move.

    Returns the number of files scanned, so a caller can tell "clean" from
    "scanned nothing" — a guard that silently checks zero files is a guard
    reporting success for no work.
    """
    root = root or _ROOT
    writes, unreadable = find_player_payoff_writes(root)
    if writes:
        listing = '\n'.join(f'    {rel}:{line}  {text}'
                            for rel, line, text in writes)
        raise RuntimeError(
            "payoff_guard.assert_no_player_payoff_writes: this build writes "
            "oTree's per-round player.payoff, and the boot is being refused "
            "rather than letting that reach a participant.\n"
            f"{listing}\n"
            "settings.AUTO_TABULATE_PAYOFFS is False (the one-payment-ledger "
            "decision), so oTree's own setter raises on every one of those "
            "lines — INSIDE THE REQUEST, on the page, mid-round. Shipping this "
            "over live sessions would be a dead page for whoever reached it, "
            "not a data error.\n"
            "Record the round's value in the game's own field "
            "(main.Player.round_payoff) and let outro.compute_final_payoff "
            "write participant.payoff once. See DECISIONS.md, 'One payment "
            "ledger'.")
    if unreadable:
        listing = '\n'.join(f'    {rel}  {reason}' for rel, reason in unreadable)
        raise RuntimeError(
            "payoff_guard.assert_no_player_payoff_writes: could not read or "
            "parse part of this build, so it CANNOT SAY whether anything "
            "writes player.payoff. This is not a payoff finding — it is a "
            "broken source tree, and a file that does not parse would fail on "
            "import anyway.\n"
            f"{listing}")
    return len(files_to_scan(root))
