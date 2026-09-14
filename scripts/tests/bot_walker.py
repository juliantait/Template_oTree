"""Shared bot-gate helpers for the HTTP/in-process walkers.

Since the `prolific` profile ships the ACTIVE bot-detection ejectors ARMED (the
welcome decoy honeypot and the DOT-BI visual gate), any walker that means to
COMPLETE a Prolific session now has to get past them. Two things are needed, and
they belong in ONE place so every walker treats the gates identically rather than
each re-deriving it (the one-implementation rule):

  * THE WELCOME DECOY needs nothing — a human never touches it, and a walker that
    leaves the checkbox unticked (as build_payload does: it skips checkboxes)
    passes automatically. `decoy_is_untouched` documents that and lets a test
    assert it explicitly.

  * THE DOT-BI GATE needs the RIGHT answer under a "JS ran" flag. The answer
    never reaches the client, so a walker computes it the way the server does —
    from dot_bi.py (imported by PATH, so the test process never configures oTree)
    and the participant code in the page URL. `dotbi_payload` returns the fields
    to inject. A real bot has neither the repo module nor the participant code
    from the admin side, which is the whole point of the gate; the test's ability
    to solve it is a property of the test harness, not a leak.

END_MARKERS_BOT adds the shared neutral-return ending's wording so a walker
recognises it as an ending (a -5/-6 return) instead of over-submitting past it.
"""
import importlib.util
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _repo import REPO_ROOT  # noqa: E402


def _load_dot_bi():
    """Load dot_bi.py by PATH (like quiz_answers loads the quiz items), so the
    test process never has to import the oTree-configured package. dot_bi is a
    pure module (hashlib only), so this is safe and cannot come from the server
    under test."""
    path = os.path.join(REPO_ROOT, 'dot_bi.py')
    spec = importlib.util.spec_from_file_location('dot_bi_forwalker', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DOT_BI = _load_dot_bi()

# The shared neutral-return ending's recognisable wording (outro/neutral_return.html).
END_MARKERS_BOT = ('Return to Prolific', 'can’t continue with this study')


def participant_code_from_url(url):
    """/p/<code>/... -> the participant code (the DOT-BI variant seed)."""
    m = re.search(r'/p/([^/]+)/', str(url))
    return m.group(1) if m else None


def form_has_dotbi(input_names) -> bool:
    return 'bot_dotbi_answer' in set(input_names)


def dotbi_from_variant(variant, correct=True, js=True):
    """The fields to PASS (or fail) the DOT-BI gate, computed from the OPAQUE
    variant id the form exposes (already visible in the image src). This is what
    the shared build_payload uses, so every walker solves the gate with no
    per-caller wiring. The answer comes from dot_bi's server-side map — a real
    bot, lacking that map, cannot do this."""
    answer = DOT_BI.answer_for(variant)
    if answer is None:
        return {}
    typed = str(answer if correct else (answer + 7))
    payload = {'bot_dotbi_answer': typed, 'bot_dotbi_ms': '6000'}
    if js:
        payload['bot_dotbi_js'] = '1'
    return payload


def dotbi_payload(participant_code, correct=True, js=True):
    """The fields to inject on the DOT-BI page to PASS (or deliberately FAIL) it.

    correct=True  -> the right number for this participant's variant.
    correct=False -> a deliberately wrong number (a definite ejection when armed).
    js=True       -> mark that JS ran (so the server grades the answer rather than
                     taking the no-JavaScript path). js=False leaves the flag empty,
                     which the server reads as no-JS -> the -6 gentle return.
    """
    answer = DOT_BI.answer_for(DOT_BI.choose_variant(participant_code))
    typed = str(answer if correct else (answer + 7))
    payload = {'bot_dotbi_answer': typed, 'bot_dotbi_ms': '6000'}
    if js:
        payload['bot_dotbi_js'] = '1'
    return payload
