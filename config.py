import os, json
from aiogram import Bot

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN=os.getenv('BOT_TOKEN')
bot = Bot(token=BOT_TOKEN)

IS_LOGGING = True
LOG_LEVEL = "DEBUG"  ''' "INFO", "DEBUG", "ERROR" '''
LOG_AIOGRAM = False

# --- DATABASE ---
DATABASE_USER=os.getenv('DATABASE_USER')
DATABASE_PASSWORD=os.getenv('DATABASE_PASSWORD')
DATABASE_NAME=os.getenv('DATABASE_NAME')
DATABASE_HOST=os.getenv('DATABASE_HOST')

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost") 

PORT = os.getenv('PORT', 5000)

# --- MARZBAN ---
S001_MARZBAN_USERNAME=os.getenv('S001_MARZBAN_USERNAME')
S001_MARZBAN_PASSWORD=os.getenv('S001_MARZBAN_PASSWORD')
S001_BASE_URL=os.getenv('S001_BASE_URL', 'https://s001.orbitcorp.space:8000/')

# --- TON API ---
TON_ADDRESS=os.getenv('TON_ADDRESS')
TONAPI_URL=os.getenv('TONAPI_URL')
TONAPI_KEY=os.getenv('TONAPI_KEY')
TON_EXPLORER_TX_URL = f"https://tonviewer.com/{TON_ADDRESS}"

# --- CRYPTOBOT ---
CRYPTOBOT_TOKEN = os.getenv('CRYPTOPAY_TOKEN')

# --- CONSTANTS ---
FREE_TRIAL_DAYS = 7 
REFERRAL_BONUS = 50.0
REDIS_TTL = 300

TELEGRAM_STARS_RATE = 1.35
TON_RUB_RATE=220
TON_CHECK_INTERVAL=30


with open('plans.json', 'r') as f:
    PLANS = json.load(f)

for key, env_var in {
    "sub_1m": "SUB_1M_PRICE",
    "sub_3m": "SUB_3M_PRICE",
    "sub_6m": "SUB_6M_PRICE",
    "sub_12m": "SUB_12M_PRICE",
}.items():
    if key in PLANS:
        PLANS[key]["price"] = int(os.getenv(env_var, PLANS[key]["price"]))