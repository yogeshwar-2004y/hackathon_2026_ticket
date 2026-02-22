import logging
import requests

logger = logging.getLogger(__name__)

def notify_console(message: str):
    logger.warning("NOTIFY: %s", message)
    print(f"NOTIFY: {message}")

def notify_slack(webhook_url: str, message: str):
    """
    Send a fake Slack webhook. For this project we will attempt a POST but
    fall back to printing if the URL is dummy or unreachable.
    """
    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=3)
        logger.info("Slack webhook sent, status=%s", resp.status_code)
    except Exception as e:
        logger.info("Slack webhook failed, printing instead: %s", e)
        print("SLACK:", message)

