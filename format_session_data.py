#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
import pandas as pd

def is_json(myjson):
    try:
        json.loads(myjson)
        return True
    except Exception:
        return False

def main(input_csv: str, session_number: str):
    input_path = Path(input_csv).expanduser()
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}")
        sys.exit(1)

    print(f"Reading: {input_path}")
    df = pd.read_csv(str(input_path))

    session_number = str(session_number)

    json_columns = ['block1_tasks', 'block2_tasks']
    required_columns = {
        "participant.earned",
        "participant.code",
        "outro.1.player.bank",
        "outro.1.player.bic",
        "outro.1.player.bank_confirmation",
    }

    for column in json_columns:
        if column in df.columns:
            df[column] = df[column].apply(lambda x: '' if is_json(str(x)) else x)

    large_data_threshold = 1000
    columns_to_drop = []
    for column in df.columns:
        if df[column].dtype == 'object':
            mean_len = df[column].astype(str).str.len().mean()
            if mean_len > large_data_threshold and column not in required_columns:
                columns_to_drop.append(column)

    if columns_to_drop:
        df = df.drop(columns=columns_to_drop)

    out_dir_sensitive = 'REDACTED_USER_PATH/Documents/Current/Projects/Mistakes/Data/SENSITIVE/Raw - SENSITIVE'
    os.makedirs(out_dir_sensitive, exist_ok=True)
    cleaned_path = os.path.join(out_dir_sensitive, f"Session_{session_number}.csv")
    df.to_csv(cleaned_path, index=False)
    print(f"Cleaned CSV file has been saved to: {cleaned_path}")
    print(f"Removed columns (large): {columns_to_drop}")

    payment_cols = [
        "participant.earned",
        "participant.code",
        "outro.1.player.bank",
        "outro.1.player.bic",
    ]
    existing_payment_cols = [c for c in payment_cols if c in df.columns]

    if existing_payment_cols:
        out_dir_payment = 'REDACTED_USER_PATH/Documents/Current/Projects/Mistakes/Data/SENSITIVE/Payments'
        os.makedirs(out_dir_payment, exist_ok=True)
        payment_path = os.path.join(out_dir_payment, f"Session_{session_number}.csv")
        df[existing_payment_cols].to_csv(payment_path, index=False)
        print(f"Payment CSV saved to: {payment_path} (columns: {existing_payment_cols})")
    else:
        print("Warning: payment columns not found; skipping payment CSV.")

    anon_drop_cols = [
        "outro.1.player.bank",
        "outro.1.player.bic",
        "participant.earned",
        "outro.1.player.bank_confirmation",
    ]
    df_anonymous = df.drop(columns=[c for c in anon_drop_cols if c in df.columns], errors='ignore')

    out_dir_anon = 'REDACTED_USER_PATH/Documents/Current/Projects/Mistakes/Data/Raw - Anonymous'
    out_dir_datasets = 'REDACTED_USER_PATH/Documents/Current/Projects/Mistakes/Data/Datasets'
    os.makedirs(out_dir_anon, exist_ok=True)
    os.makedirs(out_dir_datasets, exist_ok=True)

    anon_path_1 = os.path.join(out_dir_anon, f"Session_{session_number}.csv")
    anon_path_2 = os.path.join(out_dir_datasets, f"Session_{session_number}.csv")
    df_anonymous.to_csv(anon_path_1, index=False)
    df_anonymous.to_csv(anon_path_2, index=False)

    print(f"Anonymous CSV saved to: {anon_path_1}")
    print(f"Anonymous CSV also saved to: {anon_path_2}")


    # --- draft Mail.app message with the anonymised file attached ---
    import subprocess
    import tempfile

    def draft_email_with_attachment(attachment_path, session_number,
                                    recipient="REDACTED_EMAIL"):
        p = Path(attachment_path).expanduser()
        if not p.exists():
            print(f"Email draft skipped — attachment not found: {p}")
            return

        applescript = f'''
            set theAttachment to POSIX file "{p}"
            tell application "Mail"
                set newMessage to make new outgoing message with properties {{subject:"Exp 2418 Session {session_number}", content:"Dear team,

                    Attached is the anonymised data for session {session_number}.
                    
                    ", visible:true}}
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
            print(f"Draft email created in Mail.app to {recipient} with attachment {p.name}")
        except subprocess.CalledProcessError as e:
            print("Failed to create draft email:", e)
        finally:
            try:
                os.remove(tf.name)
            except OSError:
                pass

    # create the draft using the anonymous file we just wrote
    draft_email_with_attachment(anon_path_1, session_number)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: clean_sessions.py /path/to/input.csv SESSION_NUMBER")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])