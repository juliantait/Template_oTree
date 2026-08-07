#!/usr/bin/env python3
"""Download the full data exports over an AUTHENTICATED admin HTTP session.

Fetches both:
  - /ExportWide       (one row per participant, all apps)
  - /ExportPageTimes  (page-by-page timing)

into a target directory as CSV files.

IMPORTANT — schema drift returns HTTP 500. If you run this against a server
whose DATABASE was created by an OLDER version of the code than is now running
(columns added/removed since the db was made), the export view raises and you
get a 500. The fix is NOT this script — it is to export from a server running
the SAME code the database was built with, or to reset the database. This script
detects the 500 and says so explicitly instead of writing a truncated file.

Usage:
    python scripts/export_data.py [--base-url URL] [--out DIR]
                                  [--user USER] [--password PASS]

Credentials default to the OTREE_ADMIN_USERNAME / OTREE_ADMIN_PASSWORD env vars
(themselves defaulting to admin/admin in dev).
"""
import argparse
import os
import sys

import requests


EXPORTS = {
    'ExportWide': '/ExportWide',
    'ExportPageTimes': '/ExportPageTimes',
}


def login(session: requests.Session, base_url: str, user: str, password: str) -> None:
    """Log in to the admin so the session cookie authorises the export views.

    In dev (AUTH_LEVEL unset) the exports are open and login is a harmless no-op;
    under STUDY/production it is required. oTree's CSRF field is named
    'csrftoken' and its value must match the session cookie issued on GET.
    """
    login_url = base_url + '/login'
    r = session.get(login_url)
    r.raise_for_status()
    token = _find_csrf(r.text)
    data = {'username': user, 'password': password}
    if token:
        data['csrftoken'] = token
    r = session.post(login_url, data=data, allow_redirects=True)
    r.raise_for_status()
    # A failed login re-renders the login form rather than redirecting away.
    if r.url.rstrip('/').endswith('/login') and 'name="password"' in r.text:
        sys.exit("FATAL: admin login failed — check OTREE_ADMIN_USERNAME / OTREE_ADMIN_PASSWORD.")


def _find_csrf(html: str):
    import re
    m = re.search(r'name="csrftoken"[^>]*value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"[^>]*name="csrftoken"', html)
    return m.group(1) if m else None


def download(session: requests.Session, base_url: str, name: str, path: str, out_dir: str) -> None:
    url = base_url + path
    r = session.get(url)
    if r.status_code == 500:
        sys.exit(
            f"FATAL: {name} returned HTTP 500.\n"
            f"  This usually means the DATABASE schema predates the running code "
            f"(a column was added/removed since the db was built).\n"
            f"  Export from a server running the code the db was built with, or "
            f"reset the database. NOT a bug in this script."
        )
    r.raise_for_status()
    dest = os.path.join(out_dir, f"{name}.csv")
    with open(dest, 'wb') as f:
        f.write(r.content)
    print(f"  wrote {dest} ({len(r.content)} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-url', default=os.environ.get('OTREE_BASE_URL', 'http://localhost:8000'))
    ap.add_argument('--out', default='exports')
    ap.add_argument('--user', default=os.environ.get('OTREE_ADMIN_USERNAME', 'admin'))
    ap.add_argument('--password', default=os.environ.get('OTREE_ADMIN_PASSWORD', 'admin'))
    args = ap.parse_args()

    base_url = args.base_url.rstrip('/')
    os.makedirs(args.out, exist_ok=True)

    session = requests.Session()
    print(f"Logging in to {base_url} as {args.user} ...")
    login(session, base_url, args.user, args.password)
    print("Downloading exports:")
    for name, path in EXPORTS.items():
        download(session, base_url, name, path, args.out)
    print("Done.")


if __name__ == '__main__':
    main()
