import argparse
import difflib
import hashlib
import os
import smtplib
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):
        return False


DEFAULT_URL = (
    "https://www.psoas.fi/en/apartments/?_sfm_htyyppi=k-%2C-p-%2C-y"
    "&_sfm_huoneistojen_tilanne=vapaa_ja_vapautumassa&_sfm_koko=7+84"
    "&_sfm_vuokra=161+791&_sfm_huonelkm=1+7"
)


def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def normalize_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style/noscript
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def send_email(subject: str, body: str) -> None:
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM", smtp_user or "")
    email_to = os.getenv("RECIPIENT_EMAIL", "litecointele@gmail.com")

    if not (smtp_user and smtp_pass and email_from and email_to):
        print("[WARN] Missing SMTP configuration; email not sent.", file=sys.stderr)
        return

    msg = MIMEMultipart()
    msg["From"] = email_from
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, [email_to], msg.as_string())


def send_telegram(message: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        # Silently skip if not configured
        print("[WARN] Telegram not configured; skipping Telegram send.", file=sys.stderr)
        return
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
        # Avoid Markdown parsing issues by sending plain text
    }
    try:
        r = requests.post(api_url, json=payload, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[WARN] Failed to send Telegram message: {e}", file=sys.stderr)


def read_state(state_dir: str):
    hash_path = os.path.join(state_dir, "last_hash.txt")
    text_path = os.path.join(state_dir, "last_text.txt")
    listings_path = os.path.join(state_dir, "last_listings.txt")
    last_hash = None
    last_text = None
    last_listings = set()
    try:
        if os.path.exists(hash_path):
            with open(hash_path, "r", encoding="utf-8") as f:
                last_hash = f.read().strip() or None
        if os.path.exists(text_path):
            with open(text_path, "r", encoding="utf-8") as f:
                last_text = f.read()
        if os.path.exists(listings_path):
            with open(listings_path, "r", encoding="utf-8") as f:
                last_listings = {ln.strip() for ln in f if ln.strip()}
    except Exception as e:
        print(f"[WARN] Failed to read state: {e}", file=sys.stderr)
    return last_hash, last_text, last_listings


def write_state(state_dir: str, h: str, text: str, listings: set | None = None) -> None:
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "last_hash.txt"), "w", encoding="utf-8") as f:
        f.write(h)
    with open(os.path.join(state_dir, "last_text.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if listings is not None:
        with open(os.path.join(state_dir, "last_listings.txt"), "w", encoding="utf-8") as f:
            for url in sorted(listings):
                f.write(url + "\n")


def make_diff(old: str, new: str, max_lines: int = 2000) -> str:
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm="", fromfile="previous", tofile="current"
    )
    lines = list(diff)
    # Truncate overly long diffs
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["... (diff truncated) ..."]
    return "\n".join(lines)


def extract_listings(html: str, base_url: str) -> set:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        abs_url = urljoin(base_url, href)
        # Heuristic: include detail pages under /en/apartments/ that are not query/list pages
        if "/en/apartments/" in abs_url:
            # exclude list/search pages with query params
            if "?" in abs_url:
                continue
            # Ensure there's more path beyond '/en/apartments/'
            tail = abs_url.split("/en/apartments/")[-1]
            if tail and tail.strip("/"):
                links.add(abs_url.rstrip("/"))
    return links


def run_once(debug: bool = False) -> int:
    url = os.getenv("URL", DEFAULT_URL)
    state_dir = os.getenv("STATE_DIR", os.path.join(os.getcwd(), ".state"))
    notify_first = env_bool("NOTIFY_ON_FIRST_RUN", False)

    if debug:
        print(f"[INFO] Fetching: {url}")
    html = fetch(url)
    text = normalize_text(html)
    h = stable_hash(text)
    listings = extract_listings(html, url)

    last_hash, last_text, last_listings = read_state(state_dir)

    if last_hash is None:
        write_state(state_dir, h, text, listings)
        did_notify = False
        if notify_first:
            subject = "PSOAS page baseline saved (first run)"
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
            body = (
                f"Time: {ts}\nURL: {url}\n\nBaseline content saved. Notifications will be sent on changes."
            )
            # Prefer Telegram if configured
            send_telegram(f"{subject}\n{body}")
            send_email(subject, body)
            did_notify = True
        if debug:
            print("[INFO] Baseline saved." + (" Notified first run." if did_notify else ""))
        return 0

    # Detect new listings
    new_listings = sorted(list(listings - last_listings)) if last_listings is not None else []
    if new_listings:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        header = f"New PSOAS listings detected ({len(new_listings)}) @ {ts}"
        sample = "\n".join(new_listings[:10])
        if len(new_listings) > 10:
            sample += f"\n... and {len(new_listings) - 10} more"
        message = f"{header}\nURL: {url}\n\n{sample}"
        if debug:
            print("[INFO] New listings detected, sending Telegram/email...")
        send_telegram(message)
        send_email("New PSOAS listings available", message)
        # Update state to include new listings and current snapshot
        write_state(state_dir, h, text, listings)
        return 0

    # Fallback: generic page change detection
    if h != last_hash:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        subject = f"PSOAS page changed @ {ts}"
        diff_text = make_diff(last_text or "", text)
        body = (
            f"URL: {url}\n\nChange detected. Hash: {last_hash} -> {h}\n\nDiff:\n{diff_text}\n"
        )
        if debug:
            print("[INFO] Change detected, sending email...")
        send_telegram(f"{subject}\n{body}")
        send_email(subject, body)
        write_state(state_dir, h, text, listings)
        return 0

    if debug:
        print("[INFO] No change detected.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Watch a page and email on changes.")
    parser.add_argument("--once", action="store_true", help="Run a single check and exit (default)")
    parser.add_argument("--debug", action="store_true", help="Verbose logging to stdout")
    args = parser.parse_args()

    # Load .env if present
    load_dotenv()

    try:
        return_code = run_once(debug=args.debug)
        sys.exit(return_code)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        if env_bool("EMAIL_ON_ERROR", False):
            send_email("PSOAS watcher error", str(e))
        if env_bool("TELEGRAM_ON_ERROR", True):
            send_telegram(f"PSOAS watcher error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
