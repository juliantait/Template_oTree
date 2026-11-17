# Where the bugs are: the collapsed-distinction rule

*Read this when you audit code, review a change, or add a branch, an except, or a second implementation of anything.*

## The collapsed-distinction rule — where the bugs actually are

**When two genuinely different situations reach identical code and become
indistinguishable, that is where the bug lives.** Go looking for it deliberately:
it is the single most productive audit you can run on this codebase, and it does
not show up as a failing test, because both situations behave "correctly" for
whichever meaning the shared code picked.

The four worked examples below were all found on one day (2026-08-12), each by
comparing this template against an independent implementation of the same
feature. The examples are the point — the rule alone reads as a platitude.

- **`unknown` vs `undetermined` device.** A User-Agent that parsed and matched
  nothing is a device type a study may reject. No header, no request, an
  exception or garbage is *not a device type* and must always be allowed. Collapsed,
  a study rejecting `unknown` starts ejecting laptops behind a privacy proxy.
- **Allowed-on-entry vs allowed-to-clear.** Absence of evidence *allows on entry*
  but must never *clear* an existing screen-out, or anyone lifts their own
  screen-out by sending no User-Agent. The clear predicate is exactly the
  entry-allow predicate **minus undetermined**.
- **Cannot-import-yet vs symbol-drifted.** A guard installed before oTree's views
  are importable must fail quietly and retry; the same guard finding the symbol
  changed shape is version drift and must be loud. `except Exception` around both
  makes them identical, and turns a missing guard into something nobody can see.
- **Abandoned vs screened-out.** Exit code `0` means "never reached an ending";
  a screen-out has its own code. Collapsed, you cannot tell someone the gate
  turned away from someone who closed the tab during the task.

The tell is usually a single predicate, a shared `except`, or one value doing two
jobs. When you find one, keep them apart *and say why at the point of the split* —
the next reader will otherwise see redundancy and simplify it back.

### The same rule inverted — one concept, two implementations

**When one concept has two implementations, they will drift, and the drift will
be invisible until the environment changes.** Same defect class, mirrored: not
two situations reaching identical code, but one situation reaching two
implementations that disagree.

Worked example, found the same day. "Is this the same participant id?" was
answered twice: conflict detection compared labels in **Python**
(whitespace-collapsed, case-folded, `identity.rows_with_label`), while the entry
lookup used `pp_set.filter_by(label=…)`, i.e. **SQL**. So a participant
returning as `ABC123` whose row held `abc123` took a fresh row — and that same
spelling typed on the confirmation page was then refused as a conflict with the
row it had just failed to match. Worse, the SQL half is decided by the database
**collation**, so it behaved one way on the sqlite dev database and another on a
postgres deployment: green locally, broken only in production.

The fix is always the same — **one implementation, called by both** — and the
audit question is: *does any concept in this codebase get decided in two places,
and does one of them delegate to something the environment controls* (a
database, a locale, a browser, a clock)?

**The client-side variant, which fails silently and reads as success.** A path
check in JavaScript deciding *which pages are monitored* is a second source of
truth about a question the server already answers. When the two disagree, the
script simply declines to run: no error, no exception, no failing test — the
column fills with clean values for everybody and a dead feature looks like good
news. `exp_pilots` shipped exactly this (a hard `return` on any `/outro/` path
in `_static/global/js/ai_safety_monitor.js`), so its questionnaire pages could have been wired perfectly
server-side and still recorded nothing.

The general rule: **wiring can be verified, a silent refusal to run cannot** —
unless something asserts that observations actually *arrive*. Any client-side
instrumentation needs a test that a monitored page produces a record, not merely
that the page is configured to be monitored.

**A second instance, same shape, different mechanism: `form.submit()` does not
fire submit event listeners.** A page whose real work lives in an
`addEventListener('submit', …)` handler — `preventDefault`, a gate POST, a
reload carrying a flag — is bypassed entirely by `form.submit()`. The page
reloads without the flag, auto-submits again, and loops forever: no participant
row, no error, no failing test, and it happens **only to real arrivals** whose
URL carries an id. Use **`form.requestSubmit()`**, which fires the handler, and
pair any auto-submit with a loop guard that falls back to showing the button
when the gate POST fails or the reload comes back without its flag.
