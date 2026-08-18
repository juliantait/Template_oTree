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
