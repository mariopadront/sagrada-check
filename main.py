import json
import logging
import time
from datetime import date, datetime

import requests

import config
import notify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("monitor")

MAX_FAILURES_BEFORE_ALERT = 5


class Clorian:
    """Minimal client for the public Clorian calendar endpoint (no reCAPTCHA needed)."""

    def __init__(self, num_tickets=None, product_id=None):
        self.num_tickets = num_tickets or config.NUM_TICKETS
        self.product_id = product_id or config.PRODUCT_ID
        self.s = requests.Session()
        self.s.headers.update({
            "Origin": config.SITE,
            "Referer": config.SITE + "/",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "pos": config.POS_ID,
        })
        self.token_expiry = 0.0

    def _login(self):
        r = self.s.post(config.TOKEN_URL, timeout=20)
        r.raise_for_status()
        data = r.json()
        self.s.headers["Authorization"] = "Bearer " + data["access_token"]
        self.token_expiry = time.time() + data.get("expires_in", 3600) - 120

    def _get(self, url, params):
        if time.time() >= self.token_expiry:
            self._login()
        r = self.s.get(url, params=params, timeout=20)
        if r.status_code in (401, 403):  # token rejected: refresh once and retry
            self._login()
            r = self.s.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def month(self, year: int, month: int) -> dict[str, str]:
        url = f"{config.API}/catalog/salesGroups/{config.SALES_GROUP_ID}/product/{self.product_id}/availability"
        return self._get(url, {
            "minTickets": self.num_tickets, "month": month,
            "venueId": config.VENUE_ID, "year": year,
        })


def load_state() -> dict[str, int] | None:
    """Per date: number of consecutive checks it has been available (old bool state still loads)."""
    try:
        return {d: int(v) for d, v in json.loads(config.STATE_FILE.read_text()).items()}
    except (OSError, ValueError, AttributeError):
        return None


def save_state(state: dict[str, int]) -> None:
    config.STATE_FILE.write_text(json.dumps(state, indent=2))


def step(previous: dict[str, int], current: dict[str, bool]) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Alert lifecycle per date: 'new' (1st available check), 'still' (2nd, once), then silence,
    'gone' when it was available and no longer is. Returns (dates per event, new counters)."""
    events: dict[str, list[str]] = {"new": [], "still": [], "gone": []}
    counts: dict[str, int] = {}
    for d, ok in current.items():
        before = previous.get(d, 0)
        counts[d] = min(before + 1, 3) if ok else 0
        if ok and before == 0:
            events["new"].append(d)
        elif ok and before == 1:
            events["still"].append(d)
        elif not ok and before > 0:
            events["gone"].append(d)
    return events, counts


def event_messages(events: dict[str, list[str]], tickets: int, buy_url: str) -> list[str]:
    names = lambda ds: ", ".join(pretty(d) for d in ds)
    msgs = []
    if events["new"]:
        msgs.append(f"Tickets available for {names(events['new'])} ({tickets} ticket(s))\nBuy now: {buy_url}")
    if events["still"]:
        msgs.append(f"Tickets are still available for {names(events['still'])}\nBuy now: {buy_url}")
    if events["gone"]:
        msgs.append(f"Tickets are no longer available for {names(events['gone'])}")
    return msgs


def check(client: Clorian) -> dict[str, bool]:
    months = sorted({(d[:4], d[5:7]) for d in config.TARGET_DATES})
    calendar: dict[str, str] = {}
    for y, m in months:
        calendar.update(client.month(int(y), int(m)))
    return {d: calendar.get(d) == "availability" for d in config.TARGET_DATES}


def pretty(d: str) -> str:
    return date.fromisoformat(d).strftime("%d %B %Y").lstrip("0")


def run_once(client: Clorian, previous: dict[str, int] | None) -> dict[str, int]:
    current = check(client)
    for d, ok in current.items():
        log.info("%s: %s", d, "AVAILABLE" if ok else "no availability")
    if previous is None:  # first ever run
        previous = {} if config.ALERT_ON_STARTUP else {d: 2 for d, ok in current.items() if ok}
    events, counts = step(previous, current)
    for msg in event_messages(events, config.NUM_TICKETS, config.BUY_URL):
        notify.send(msg)
    if config.NOTIFY_EVERY_CHECK:
        lines = [f"{pretty(d)}: {'AVAILABLE' if ok else 'no availability'}" for d, ok in current.items()]
        header = f"Check at {datetime.now():%H:%M} ({config.NUM_TICKETS} ticket(s))"
        notify.send("\n".join([header, *lines]))
    save_state(counts)
    return counts


def main():
    if not config.TARGET_DATES:
        raise SystemExit("Set TARGET_DATES in .env")
    log.info("Watching %s for %d ticket(s), every %ds",
             config.TARGET_DATES, config.NUM_TICKETS, config.CHECK_INTERVAL)
    client = Clorian()
    state = load_state()
    failures = 0
    while True:
        try:
            state = run_once(client, state)
            failures = 0
        except Exception as e:
            failures += 1
            log.warning("Check failed (%d in a row): %s", failures, e)
            if failures == MAX_FAILURES_BEFORE_ALERT:
                notify.send(f"Sagrada monitor: {failures} consecutive failures. Last error: {e}")
        time.sleep(config.CHECK_INTERVAL if failures == 0 else min(config.CHECK_INTERVAL, 120 * failures))


def once():
    """Single check for schedulers (e.g. GitHub Actions). Exits non-zero on failure so the run shows as failed."""
    if not config.TARGET_DATES:
        raise SystemExit("Set TARGET_DATES")
    run_once(Clorian(), load_state())


def loop_for(minutes: int):
    """Check repeatedly for a limited time (one scheduled CI job), so a late or skipped cron tick costs little."""
    if not config.TARGET_DATES:
        raise SystemExit("Set TARGET_DATES")
    client, state, end = Clorian(), load_state(), time.time() + minutes * 60
    while True:
        try:
            state = run_once(client, state)
        except Exception as e:
            log.warning("Check failed: %s", e)
        if time.time() + config.CHECK_INTERVAL >= end:
            return
        time.sleep(config.CHECK_INTERVAL)


if __name__ == "__main__":
    import sys
    try:
        if "--loop-for" in sys.argv:
            loop_for(int(sys.argv[sys.argv.index("--loop-for") + 1]))
        elif "--once" in sys.argv:
            once()
        else:
            main()
    except KeyboardInterrupt:
        log.info("Stopped.")
