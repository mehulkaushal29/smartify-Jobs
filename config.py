import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Australia/Melbourne")
DAILY_HOUR = int(os.getenv("DAILY_HOUR", 9))
DAILY_MINUTE = int(os.getenv("DAILY_MINUTE", 0))
RESULTS_PER_PAGE = 3

# ✅ NEW
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()  # should show this
