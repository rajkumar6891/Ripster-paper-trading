"""
Optional hourly email delivery via Gmail SMTP (app password auth).

Credentials are never stored in this repo -- they live in a JSON file in
the user's home directory (see CONFIG_PATH below), which run.py reads at
send time. If that file doesn't exist, sending is silently skipped so the
monitor still works without email configured.

Expected config file shape:
{
  "sender_email": "you@gmail.com",
  "app_password": "xxxx xxxx xxxx xxxx",
  "recipient_email": "you@gmail.com"
}
"""

import json
import os
import smtplib
from email.mime.text import MIMEText

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".ripster_paper_trading_email.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def build_headline(entries, seed_mode):
    if seed_mode:
        return "Baseline seed run -- no live signals evaluated."
    if not entries:
        return "No new bullish entries this run."
    tickers = ", ".join(e["ticker"] for e in entries)
    return f"New bullish EMA-cloud entries this run: {tickers}"


def compose_email(report, entries, seed_mode, subject_stamp):
    subject = f"Paper trading update - {subject_stamp}"
    headline = build_headline(entries, seed_mode)
    body = f"{headline}\n\n{report}"
    return subject, body


def send_report_email(report, entries, seed_mode, subject_stamp, dry_run=False):
    """Returns a dict describing what happened -- never raises, so a mail
    failure can't take down the run itself."""
    subject, body = compose_email(report, entries, seed_mode, subject_stamp)

    if dry_run:
        return {"sent": False, "dry_run": True, "subject": subject, "body": body}

    config = load_config()
    if config is None:
        return {"sent": False, "reason": f"no email config at {CONFIG_PATH}"}

    recipient = config.get("recipient_email", config["sender_email"])
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config["sender_email"]
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
            server.login(config["sender_email"], config["app_password"])
            server.sendmail(config["sender_email"], [recipient], msg.as_string())
        return {"sent": True, "to": recipient, "subject": subject}
    except Exception as e:  # noqa: BLE001 - report, don't crash the run
        return {"sent": False, "reason": str(e)}
