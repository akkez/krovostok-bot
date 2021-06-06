import logging

import tortoise
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

from src.models import BotUser, BotMessage


def setup_logging(file, level=logging.INFO):
	log_format = '[%(asctime)s] %(name)s: %(levelname)s %(message)s'
	logging.basicConfig(level=level, filename=file, format=log_format)
	console = logging.StreamHandler()
	console.setLevel(level)
	formatter = logging.Formatter(log_format)
	console.setFormatter(formatter)
	logging.getLogger().addHandler(console)


class LogMiddleware(BaseMiddleware):
	async def on_process_update(self, message: types.Update, data: dict):
		bot_obj = await message.bot.me
		user_obj = None

		if message.callback_query:
			from_user = message.callback_query.from_user
		else:
			from_user = message.message.from_user
		if from_user:
			if not await BotUser.filter(id=from_user.id).count():
				try:
					user_obj = await BotUser.create(id=from_user.id, username=from_user.username,
					                                first_name=from_user.first_name, last_name=from_user.last_name,
					                                language_code=from_user.language_code, bot=bot_obj.username)
				except tortoise.exceptions.IntegrityError:
					pass
			else:
				user_obj = await BotUser.filter(id=from_user.id).first()

		message_text = None
		if message and message.message and message.message.text:
			message_text = message.message.text
		await BotMessage.create(user=user_obj, update=message.to_python(), text=message_text)
