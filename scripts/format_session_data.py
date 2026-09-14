#!/usr/bin/env python3
"""Format raw oTree session data into payment and anonymised CSVs.

Reads an exported session CSV, drops large/JSON columns, and writes three
files into the configured output directory:

    <out>/sensitive/Session_<N>.csv   full cleaned data (includes bank info)
    <out>/payments/Session_<N>.csv    payment columns only
    <out>/anonymous/Session_<N>.csv   anonymised data (no payment/bank columns)

Paths and the optional email recipient are configurable via CLI args or
environment variables. Nothing personal is hardcoded.

Usage:
    scripts/format_session_data.py <input.csv> <session_number> [--out <dir>]

Environment variables (optional):
    SESSION_DATA_OUT     base output directory (default: ./session_data)
    SESSION_DATA_EMAIL   recipient for the macOS Mail.app draft (skipped if unset)
"""
import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd


# =============================================================================
# BEHAVIOUR-CAPTURE DERIVATION (bucket B / measure B3, §D + §8.10 of the bot
# spec). The live WELCOME/QUIZ pages store ONLY the raw telemetry blob
# (participant.telemetry_welcome / telemetry_quiz). The AI-likelihood flags are
# derived HERE, ex-post, exactly as Mission Possible derives them downstream in
# Cleaning_Tracker.R — one place, re-tunable, off the raw JSON. This script then
# BLANKS the raw JSON in the analysis-ready outputs (it survives in the raw oTree
# export). NB the thresholds are lifted, with attribution, from the MIT
# `mission-possible-code` repo; re-tune the two numbers against your own pilot.
# =============================================================================

# median inter-keystroke interval at or below this reads as non-human (Mission
# Possible: ~8% of AI agents pass the typing-speed check).
TYPING_FAST_MAX_MS = 75.0
# a single input-length jump larger than this, with no matching keystrokes, is a
# paste-without-a-paste-event (their input-jump signal).
INPUT_JUMP_MIN_CHARS = 50

# The telemetry participant-field columns, and the page prefix each derives to.
TELEMETRY_COLUMNS = {
    'participant.telemetry_welcome': 'welcome',
    'participant.telemetry_quiz': 'quiz',
}


def _median(values):
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def derive_telemetry(blob):
    """Turn one raw behaviour-capture blob (a JSON string, or already-parsed
    dict) into analysis-ready flags. Returns a dict of UN-prefixed columns; the
    caller prefixes them per page. Returns {} for a blank / unparseable blob (a
    no-JS submission has no measured input — "not measured", never "clean").

    Mirrors telemetry_capture.js's field family. Pure and self-contained so it is
    unit-testable over fixture blobs without a browser (see
    scripts/tests/telemetry_derivation_test.py)."""
    if isinstance(blob, dict):
        data = blob
    else:
        text = str(blob or '').strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}

    key_times = data.get('key_times') or []
    intervals = []
    if isinstance(key_times, list) and len(key_times) >= 2:
        try:
            ordered = sorted(float(t) for t in key_times)
            intervals = [b - a for a, b in zip(ordered, ordered[1:]) if b >= a]
        except Exception:
            intervals = []
    median_ms = _median(intervals) if intervals else None
    max_jump = data.get('max_input_jump') or 0

    return {
        'paste_detected': bool(data.get('paste_detected')),
        'copy_detected': bool(data.get('copy_detected')),
        'input_jump': bool(isinstance(max_jump, (int, float))
                           and max_jump > INPUT_JUMP_MIN_CHARS),
        'typing_median_ms': median_ms,
        # Only a real typing sample can read as "fast": with no intervals the
        # flag is False, not a spurious True from an empty median.
        'typing_fast': bool(median_ms is not None and median_ms <= TYPING_FAST_MAX_MS),
        'keystroke_count': int(data.get('keydown_count') or 0),
        'mouse_move_count': int(data.get('mouse_move_count') or 0),
        'click_count': int(data.get('click_count') or 0),
        'scroll_count': int(data.get('scroll_event_count') or 0),
        'tab_hidden': bool(data.get('tab_hidden')),
        'window_blurred': bool(data.get('window_blurred')),
        'time_on_page_ms': data.get('time_on_page_ms'),
    }


def add_telemetry_derivation(df):
    """For each raw telemetry column present, emit the derived bot_<page>_* columns
    and BLANK the raw JSON in this (analysis-ready) frame. Mutates and returns df.
    A no-op when neither column is present (e.g. a session that never enabled the
    capture module)."""
    for raw_col, page in TELEMETRY_COLUMNS.items():
        if raw_col not in df.columns:
            continue
        derived = df[raw_col].apply(derive_telemetry)
        # Union of keys, so every row gets the full column set (missing -> None).
        keys = ['paste_detected', 'copy_detected', 'input_jump', 'typing_median_ms',
                'typing_fast', 'keystroke_count', 'mouse_move_count', 'click_count',
                'scroll_count', 'tab_hidden', 'window_blurred', 'time_on_page_ms']
        for k in keys:
            df[f'participant.bot_{page}_{k}'] = derived.apply(
                lambda d, k=k: d.get(k) if isinstance(d, dict) else None)
        # Blank the raw blob in the analysis-ready output (it stays in the raw
        # oTree export). Capture and judgement are kept separate.
        df[raw_col] = ''
    return df


def is_serialized_blob(value):
    """True for a cell holding a serialised container.

    Player LongStringFields (quiz_attempt_log, device_info_json) export as real
    JSON, but participant-vars columns (participant_extra, device_info, ...)
    export as the PYTHON REPR of the dict/list — single quotes, not JSON — so
    both parsers are tried. Only containers count: a cell holding a plain
    number or word is data, not a blob.
    """
    for parse in (json.loads, ast.literal_eval):
        try:
            return isinstance(parse(value), (dict, list))
        except Exception:
            pass
    return False


def draft_email_with_attachment(attachment_path: Path, session_number: str, recipient: str):
    # macOS-only convenience: opens a draft in Mail.app with the file attached.
    if not recipient:
        return
    if sys.platform != "darwin":
        print("Email draft skipped — Mail.app drafting only works on macOS.")
        return
    if not attachment_path.exists():
        print(f"Email draft skipped — attachment not found: {attachment_path}")
        return

    applescript = f'''
        set theAttachment to POSIX file "{attachment_path}"
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"Session {session_number}", content:"Attached is the anonymised data for session {session_number}.\n\n", visible:true}}
            tell newMessage
                make new to recipient with properties {{address:"{recipient}"}}
                make new attachment with properties {{file name:theAttachment}} at after the last paragraph
            end tell
            activate
        end tell
        '''
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".applescript", delete=False)
    try:
        tf.write(applescript)
        tf.close()
        subprocess.run(["osascript", tf.name], check=True)
        print(f"Draft email created in Mail.app to {recipient} with attachment {attachment_path.name}")
    except subprocess.CalledProcessError as e:
        print("Failed to create draft email:", e)
    finally:
        try:
            os.remove(tf.name)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Format an oTree session CSV into payment + anonymised outputs.")
    parser.add_argument("input_csv", help="Path to the raw exported session CSV.")
    parser.add_argument("session_number", help="Session number used in output filenames.")
    parser.add_argument(
        "--out",
        default=os.environ.get("SESSION_DATA_OUT", "./session_data"),
        help="Base output directory (default: ./session_data or $SESSION_DATA_OUT).",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("SESSION_DATA_EMAIL", ""),
        help="Optional recipient for a macOS Mail.app draft with the anonymised file attached.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv).expanduser()
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}")
        sys.exit(1)

    session_number = str(args.session_number)
    base_out = Path(args.out).expanduser()
    sensitive_dir = base_out / "sensitive"
    payments_dir = base_out / "payments"
    anonymous_dir = base_out / "anonymous"
    for d in (sensitive_dir, payments_dir, anonymous_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"Reading: {input_path}")
    df = pd.read_csv(str(input_path))

    # BEHAVIOUR-CAPTURE DERIVATION (§D/§8.10): emit the analysis-ready bot_<page>_*
    # flags from the raw telemetry blobs, then blank the raw JSON in these
    # outputs (it survives in the raw oTree export). Done here, before the sweeps
    # below, so the (large) raw blobs are already blanked and the derived columns
    # are present in every output written from df.
    df = add_telemetry_derivation(df)

    # Bulky JSON telemetry/audit blobs this template exports (see CODEBOOK.md).
    # Their cells are BLANKED in every output: they are logs for debugging and
    # audit, not analysis data, and they bloat the CSV. Payment and analysis
    # JSON (payouts, all_round_payoffs, payoff_vector, stage_timestamps) is
    # deliberately NOT listed and survives intact.
    json_columns = [
        "participant.participant_extra",     # free JSON bucket: screen-out history, raw UA copies
        "participant.device_info",           # raw device/screen blob (telemetry_device_capture)
        "participant.tab_monitor_focus_event_ids",       # tab-monitor dedup bookkeeping (tab_monitor_focus_loss_count is the datum)
        "participant.tab_monitor_focus_events",          # per-event {page, region, ts} log (tab_monitor_where is the readable form)
        "before.1.player.device_info_json",  # the same device blob, as submitted
        "intro.1.player.quiz_attempt_log",   # every graded quiz submission (round 1)
        "intro.2.player.quiz_attempt_log",   # ... and the lab re-read pass (round 2)
    ]
    # Never dropped by the large-column sweep below: the payment file is built
    # from these. NB the earned amount is `outro.1.player.earned` — there is no
    # `participant.earned` in this template's export.
    required_columns = {
        "participant.code",
        "participant.label",
        "participant.participant_id_external",
        "outro.1.player.earned",
        "outro.1.player.bank",
        "outro.1.player.bic",
        "outro.1.player.bank_confirmation",
    }

    for column in json_columns:
        if column in df.columns:
            df[column] = df[column].apply(
                lambda x: "" if is_serialized_blob(str(x)) else x)

    large_data_threshold = 1000
    columns_to_drop = []
    for column in df.columns:
        if df[column].dtype == "object":
            mean_len = df[column].astype(str).str.len().mean()
            if mean_len > large_data_threshold and column not in required_columns:
                columns_to_drop.append(column)

    if columns_to_drop:
        df = df.drop(columns=columns_to_drop)

    cleaned_path = sensitive_dir / f"Session_{session_number}.csv"
    df.to_csv(cleaned_path, index=False)
    print(f"Cleaned CSV saved to: {cleaned_path}")
    print(f"Removed columns (large): {columns_to_drop}")

    # Lab pays by bank transfer (bank/bic); Prolific pays through the platform,
    # keyed on the confirmed id. Both sets are listed; columns a session did
    # not collect are simply absent and filtered out below.
    payment_cols = [
        "participant.code",
        "participant.label",
        "participant.participant_id_external",
        "outro.1.player.earned",
        "outro.1.player.bank",
        "outro.1.player.bic",
    ]
    existing_payment_cols = [c for c in payment_cols if c in df.columns]

    if existing_payment_cols:
        payment_path = payments_dir / f"Session_{session_number}.csv"
        df[existing_payment_cols].to_csv(payment_path, index=False)
        print(f"Payment CSV saved to: {payment_path} (columns: {existing_payment_cols})")
    else:
        print("Warning: payment columns not found; skipping payment CSV.")

    # Anonymised = no payment/bank columns AND no recruitment identity: in this
    # template the participant label / Prolific id columns are the personal
    # identifiers, so they go too (participant.code alone remains as the
    # anonymous key).
    anon_drop_cols = [
        "outro.1.player.bank",
        "outro.1.player.bank_confirmation",
        "outro.1.player.bic",
        "outro.1.player.earned",
        "participant.label",
        "participant.participant_id_external",
        "before.1.player.participant_label",
        "before.1.player.participant_id_url",
        "before.1.player.participant_id_external",
        "before.1.player.prolific_label_conflict",
    ]
    df_anonymous = df.drop(columns=[c for c in anon_drop_cols if c in df.columns], errors="ignore")

    anon_path = anonymous_dir / f"Session_{session_number}.csv"
    df_anonymous.to_csv(anon_path, index=False)
    print(f"Anonymous CSV saved to: {anon_path}")

    draft_email_with_attachment(anon_path, session_number, args.email)


if __name__ == "__main__":
    main()
