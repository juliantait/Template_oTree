"""Monitored-by-default page bases — the tab monitor's page wiring, ONCE.

THE INVERSION (Julian, 2026-08-13; whole-app review B1, generalising TaskPage's
J2 reasoning). The monitor used to be OPT-IN per page: `main.TaskPage` carried
the wiring and everything else had none — which is how the instructions and
the quiz spent months documented as monitored while no monitoring existed on
them, with no error anywhere to say so. The model is now INVERTED:

    **Everything after the agreement screen (`before.AISafetyAgree`) is
    monitored BY DEFAULT. A page that must not be monitored has to say so
    EXPLICITLY (`monitored = False`). You can only get an unmonitored page by
    asking for one.**

Forgetting is made impossible twice over:

  * every page class in `intro`, `main` and `outro` subclasses a base here, so
    a new page inherits the wiring by existing;
  * `assert_monitored_page_sequence` runs at IMPORT at the bottom of each of
    those three apps and REFUSES TO BOOT over a page that is neither — failing
    the boot, never a participant's page (the identity.py guard's placement
    reasoning).

The `before` app is deliberately NOT under the rule: its pages sit at or
before the agreement, where there is nothing armed to monitor.

Everything here is inert unless the `tab_monitor` session flag is on — a lab
session (module off) inherits all of this and none of it does anything.

THE FOUR PIECES TRAVEL TOGETHER — the partial wiring that caused the original
gap is the failure mode this file exists to prevent:

  1. `live_method`  — the server-authoritative violation counter
                      (common.focus_live_method / _outro);
  2. `js_vars`      — the client thresholds (common.monitor_js_vars / _outro;
                      {} when the module is off, and the client REQUIRES them
                      — no defaults fallback in the JS);
  3. the script     — ai_safety_monitor.js, shipped to EVERY page through
                      css_bundle.html -> tabmonitor_assets.html (no
                      per-template include to forget), emitted only when the
                      module is on, and inert without (2);
  4. the stylesheet — tabmonitor.css, same route.

TWO PHASES, ONE DELIBERATE ASYMMETRY (same monitor, same counting, different
consequence — the full why is at common._apply_focus_loss):

  MonitoredPage       intro + main: violations EJECT at the threshold.
  OutroMonitoredPage  outro: violations are RECORDED ONLY (their own column,
                      focus_loss_count_outro) and NEVER eject — the task is
                      over and the data collected; disqualifying a completer
                      would cost a real participant for no benefit.

GOTCHAS, inherited from TaskPage's docstring and still true:

  * oTree resolves page attributes at IMPORT — a page cannot unbind by
    omitting; the ONE sanctioned opt-out is `monitored = False`, which unbinds
    live_method AND replaces js_vars in the same stroke (so the four pieces
    cannot be half-disarmed). Do NOT set `js_vars = None` to opt out: oTree
    CALLS js_vars unconditionally at render, so None is a 500, not an unbind.
  * a page that defines its OWN js_vars takes over the whole payload — spread
    `common.monitor_js_vars(player)` (or `_outro`) into it or that page's
    client monitor silently loses its config;
  * a page that defines its OWN live_method takes over the whole channel —
    delegate non-own message types to the monitor's handler, as
    `outro.results_live_method` does.
"""
from otree.api import Page

import common


def unmonitored_js_vars(player):
    """js_vars for an explicitly opted-out page: no monitor config, so the
    (still-shipped) client script refuses to start. A named function rather
    than None because oTree calls js_vars unconditionally at render — None
    would 500 the page, which the old unbind advice ("js_vars = None") never
    noticed because nothing ever rendered an unbound page."""
    return {}


class MonitoredPage(Page):
    """The default base for every page after the agreement screen — the
    EJECTING phase (intro + main). Subclass it and write content; the monitor
    wiring is inherited, and forgetting it is structurally impossible.

    To opt a page out of monitoring, say so explicitly::

        class Recap(MonitoredPage):
            monitored = False   # the ONLY sanctioned opt-out — see the
                                # module docstring for why not js_vars = None

    which unbinds the live handler and empties the client config together.
    """

    # THE EXPLICIT OPT-OUT SWITCH. False disarms the page: __init_subclass__
    # below nulls live_method and swaps js_vars for the empty builder in one
    # stroke, so the four pieces cannot be half-disarmed.
    monitored = True

    live_method = staticmethod(common.focus_live_method)
    js_vars = staticmethod(common.monitor_js_vars)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.monitored:
            # Only fill what the class did not define itself: an opted-out
            # page may legitimately carry its OWN (non-monitor) live feature
            # or js_vars, and those are its business.
            if 'live_method' not in cls.__dict__:
                cls.live_method = None
            if 'js_vars' not in cls.__dict__:
                cls.js_vars = staticmethod(unmonitored_js_vars)


class OutroMonitoredPage(MonitoredPage):
    """The outro's base: monitored, but violations are RECORDED ONLY — never a
    disqualification, never an exit-code write, never a broadcast (Julian,
    2026-08-13). Post-task violations land in `focus_loss_count_outro`, their
    own column, so the export can tell a completed-with-violations participant
    from a nearly-ejected one. The client is told (`ejects: false`) and shows
    no overlay and no warning modal — the modal's threat would be a lie here.
    The full reasoning: common._apply_focus_loss."""

    live_method = staticmethod(common.focus_live_method_outro)
    js_vars = staticmethod(common.monitor_js_vars_outro)


def assert_monitored_page_sequence(app_name, page_sequence):
    """REFUSE TO BOOT over a page that dodged the monitored-by-default rule.

    Called at import from the bottom of `intro`, `main` and `outro` (never
    `before` — its pages precede the arming). A page class that is not a
    MonitoredPage subclass has not asked to be unmonitored — it has silently
    dodged the rule, which is exactly the failure the inversion exists to
    make impossible — so this raises AT BOOT, where the author is looking,
    rather than serving an unwatched page to a participant.
    """
    for page in page_sequence:
        if not (isinstance(page, type) and issubclass(page, MonitoredPage)):
            raise TypeError(
                f"{app_name}.{page.__name__} is in page_sequence but is not a "
                f"participant_tab_monitor.MonitoredPage subclass. Every page "
                f"after the agreement screen is monitored BY DEFAULT: subclass "
                f"MonitoredPage (or OutroMonitoredPage in the outro), or opt "
                f"out EXPLICITLY with `monitored = False` on such a subclass. "
                f"A plain Page here would be silently unwatched, which is the "
                f"failure this check exists to prevent."
            )
