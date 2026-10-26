import logging

import requests

import config

log = logging.getLogger("notify")


def send(message: str, method: str | None = None, token: str | None = None, chat_id: str | None = None) -> None:
    method = method or config.NOTIFY_METHOD
    try:
        if method == "telegram":
            r = requests.post(
                f"https://api.telegram.org/bot{token or config.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id or config.TELEGRAM_CHAT_ID, "text": message},
                timeout=15,
            )
            r.raise_for_status()
        elif method == "discord":
            r = requests.post(config.DISCORD_WEBHOOK_URL, json={"content": message}, timeout=15)
            r.raise_for_status()
        else:
            print(f"\n*** {message}\n")
    except Exception:
        log.exception("Notification failed; message was: %s", message)
