import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

BASE_DIR = Path(__file__).absolute().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env')


class Config:
	BOT_ID = 'krovostok'
	DB_PATH = os.environ['DB_PATH']
	ADMIN_USERS: List[int] = list(map(int, filter(None, os.environ.get('ADMIN_USERS', '').split(','))))
	TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
	LOGFILE = os.environ.get("LOGFILE", BOT_ID)
	LOG_PATH = str(BASE_DIR / 'logs' / f'{LOGFILE}.log')
