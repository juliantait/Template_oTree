"""DOT-BI visual bot gate — the SERVER-SIDE answer key and variant chooser.

DOT-BI (Bleeker & Gotsch 2025, "Dynamic Optical Test for Bot Identification",
arXiv 2512.03580, MIT, github.com/MalteBleeker/DOT-BI) draws a hidden number in
the SAME random black-and-white pixel texture as its background. It is invisible
in any single frame; a human reads it only because the number and the background
move and scale differently across the animation. GPT-5-Thinking and Gemini 2.5
Pro both failed it even when told the mechanism, while 99.5% of 182 humans solved
it (~10.7s median) — which is exactly what an active screen-out needs.

WHY THIS FILE EXISTS, AND THE ONE SECURITY RULE IT ENFORCES.
    The upstream repo encodes the correct answer ONLY in the filename stem
    (`243.gif` => the hidden number is 243, with no manifest). If we served the
    variants under those names, the answer would sit in the URL and the DOM and
    any participant — or agent — could read it off. So the vendored variants are
    renamed to OPAQUE ids (`dotbi_01.gif` … `dotbi_15.gif`, pixels unaltered) and
    the id->answer map lives HERE, server-side, NEVER under `_static/` and NEVER
    sent to the client. The client is handed the opaque id (in the <img> src)
    and grades NOTHING; grading happens on the server, in `check` below.

FORMAT / SIZE (reported at build): the variants are the ORIGINAL animated GIFs,
    copied byte-for-byte, NOT re-encoded. Re-encoding to a smaller muted MP4/WebM
    was considered and rejected for this build: lossy compression of a
    random-noise texture can destroy the very concealment the test relies on, and
    that human-solvability could not be verified here. So we keep the GIFs and
    ship a SUBSET (15 of the repo's 121 variants, ~37 MB) to bound template size;
    a fork can vendor more from _ai/dotbi_bundle/ and extend ANSWERS.

MIT ATTRIBUTION is retained beside the served variants
(`_static/global/img/dot_bi/LICENSE` and `ATTRIBUTION.md`), as the licence
requires wherever the variants are redistributed.

Pure module: it imports nothing from oTree, so a test can load it by path (like
scripts/tests/quiz_answers.py) and compute the same answer the server will.
"""
import hashlib

# opaque id -> the hidden number. THE ANSWER KEY. Server-side only; do not move
# any part of this under _static/, and do not emit an answer into any page. Keys
# match the files vendored into _static/global/img/dot_bi/ (a SUBSET of
# _ai/dotbi_bundle/answers.json). Extend this in lockstep when vendoring more.
ANSWERS = {
    'dotbi_01': 104,
    'dotbi_02': 131,
    'dotbi_03': 162,
    'dotbi_04': 203,
    'dotbi_05': 236,
    'dotbi_06': 266,
    'dotbi_07': 299,
    'dotbi_08': 322,
    'dotbi_09': 347,
    'dotbi_10': 375,
    'dotbi_11': 414,
    'dotbi_12': 446,
    'dotbi_13': 475,
    'dotbi_14': 516,
    'dotbi_15': 552,
}

# Sorted so the chooser is stable across processes and machines.
VARIANTS = tuple(sorted(ANSWERS))

# The served location of a variant, relative to the static root. The template
# turns this into a URL via {% static %}; the OPAQUE id is all that reaches the
# client (never the answer, never an original filename).
STATIC_SUBDIR = 'global/img/dot_bi'


def choose_variant(seed) -> str:
    """Pick a variant DETERMINISTICALLY from a per-participant seed.

    Deterministic so a page reload (or the grading pass) shows and grades the
    SAME variant — no stored state needed, and no way to reroll into an easier
    one. A hash of the seed spread over VARIANTS ROTATES variants across
    participants (the spec's predictability-reduction), while staying stable for
    one participant. Seed with something stable and per-participant, e.g.
    `participant.code`.
    """
    key = str(seed or '')
    digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
    return VARIANTS[int(digest, 16) % len(VARIANTS)]


def variant_static_path(variant) -> str:
    """The static-relative path for a variant id, e.g.
    'global/img/dot_bi/dotbi_03.gif'. Raises KeyError for an unknown id, so a
    typo is loud rather than a broken <img>."""
    if variant not in ANSWERS:
        raise KeyError(f"unknown DOT-BI variant {variant!r}")
    return f"{STATIC_SUBDIR}/{variant}.gif"


def answer_for(variant):
    """The hidden number for a variant, or None for an unknown id (never raises —
    grading must never 500 a participant's page)."""
    return ANSWERS.get(variant)


def check(seed, submitted) -> bool:
    """Did this participant type the RIGHT number for THEIR variant?

    Recomputes the variant from `seed` (so the server never trusts a client-sent
    variant) and compares the submitted value as an integer. Tolerant of
    surrounding whitespace and a stray leading '+'; anything non-numeric is
    simply wrong (never an exception). Grading is entirely here — the answer
    never reaches the client.
    """
    expected = answer_for(choose_variant(seed))
    if expected is None:
        return False
    raw = str(submitted or '').strip().lstrip('+')
    if not raw.isdigit():
        return False
    return int(raw) == expected
