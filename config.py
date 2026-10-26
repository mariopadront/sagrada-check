import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


def _dates(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("["):
        return [str(d) for d in json.loads(raw)]
    return [d.strip() for d in raw.split(",") if d.strip()]


TARGET_DATES = _dates(os.getenv("TARGET_DATES", ""))
NUM_TICKETS = int(os.getenv("NUM_TICKETS", "1"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "900"))
PRODUCT_ID = int(os.getenv("PRODUCT_ID", "4375"))
NOTIFY_METHOD = os.getenv("NOTIFY_METHOD", "console").lower()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ALERT_ON_STARTUP = os.getenv("ALERT_ON_STARTUP", "true").lower() in ("1", "true", "yes")

NOTIFY_EVERY_CHECK = os.getenv("NOTIFY_EVERY_CHECK", "false").lower() in ("1", "true", "yes")

STATE_FILE = BASE_DIR / "state.json"
SALES_GROUP_ID = 1
VENUE_ID = 1
POS_ID = "649"
API = "https://services.clorian.com"
SITE = "https://tickets.sagradafamilia.org"
# Public, anonymous client credential embedded in the site's own JavaScript.
TOKEN_URL = f"{API}/user/api/oauth/token?secretKey=thesagradafamiliafrontendoftomorrow"
BUY_URL = f"{SITE}/en/1-individual/{PRODUCT_ID}-sagrada-familia"
