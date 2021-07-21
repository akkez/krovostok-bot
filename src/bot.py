import asyncio
import logging

from aiogram import Bot, Dispatcher, executor
from tortoise import Tortoise

from src import audio_handlers
from src.config import Config
from src.loggers import LogMiddleware, setup_logging

logger = logging.getLogger(__name__)


async def init_db():
	await Tortoise.init(db_url=Config.DB_PATH, modules={"models": ["src.models"]})
	await Tortoise.generate_schemas()


if __name__ == '__main__':
	setup_logging(Config.LOG_PATH, logging.INFO)

	loop = asyncio.get_event_loop()
	loop.run_until_complete(init_db())

	bot = Bot(token=Config.TELEGRAM_TOKEN)
	dp = Dispatcher(bot)

	dp.middleware.setup(LogMiddleware())
	audio_handlers.setup(dp)

	executor.start_polling(dp, skip_updates=True)
