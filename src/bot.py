import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, executor
from dotenv import load_dotenv
from tortoise import Tortoise

from src import audio_handlers
from src.loggers import LogMiddleware, setup_logging

BOT_ID = 'krovostok'
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).absolute().parent.parent
load_dotenv(dotenv_path=BASE_DIR / '.env')


async def init_db():
	await Tortoise.init(db_url=os.environ['DB_PATH'], modules={"models": ["src.models"]})
	await Tortoise.generate_schemas()


if __name__ == '__main__':
	setup_logging(str(BASE_DIR / 'logs' / f'{os.environ.get("LOGFILE", BOT_ID)}.log'), logging.INFO)

	loop = asyncio.get_event_loop()
	loop.run_until_complete(init_db())

	bot = Bot(token=os.environ['TELEGRAM_TOKEN'])
	dp = Dispatcher(bot)

	dp.middleware.setup(LogMiddleware())
	audio_handlers.setup(dp)

	executor.start_polling(dp, skip_updates=True)
