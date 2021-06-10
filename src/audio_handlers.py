import asyncio
import datetime
import glob
import logging
import os
import tempfile
from pathlib import Path

import aiogram
from aiogram import Dispatcher, types
from aiogram.types import ContentType

from src.models import BotAudio, BotUser

logger = logging.getLogger(__name__)

VOLUME_CHANGING_STEPS = [3, 10, 50]


async def send_welcome(message: types.Message):
	await message.reply('Привет! Просто пришли мне войс\n\n'
	                    'Если добавишь меня в чат - я смогу отвечать всем собеседникам войсами на войс 🔊')


async def execute_shell_command(cmd):
	proc = await asyncio.create_subprocess_shell(
		cmd,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE)

	stdout, stderr = await proc.communicate()

	logger.info(f'[{cmd!r} exited with {proc.returncode}]')
	if stdout:
		# print(f'[stdout]\n{stdout.decode()}')
		...
	if stderr:
		# print(f'[stderr]\n{stderr.decode()}')
		...
	return proc.returncode


async def run_transformation(input_filepath: str, volume: float, output_filepath: str):
	"""
	the other way to do the same is (see https://github.com/kkroening/ffmpeg-python):
		inputs = [ffmpeg.input(minus).filter('volume', float(volume / 100.0)),
                  ffmpeg.input(filename)]
        result, _ = ffmpeg.filter(inputs, 'amix', inputs=2, duration='shortest').output(output_file).run()
    """
	minus = Path(__file__).absolute().parent.parent / 'files' / 'krovominus.mp3'
	shell_command = f'ffmpeg -y -i {minus} -i {input_filepath} -filter_complex "[0]volume={volume:.2f}[s0];[s0][1]amix=duration=shortest:inputs=2[s1]" -map [s1] {output_filepath}'
	ret_code = await execute_shell_command(shell_command)
	return ret_code


async def on_voice(message: [types.voice.Voice, types.audio.Audio]):
	await message.bot.send_chat_action(chat_id=message.chat.id, action=types.ChatActions.RECORD_AUDIO)
	bot = message.bot
	media = message.voice or message.audio
	file_id = media.file_id

	file = await bot.get_file(file_id)
	file_path = file.file_path

	with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as source_file:
		with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as destination_file:
			await bot.download_file(file_path, source_file.name)

			user_object = await BotUser.get_or_none(id=message.from_user.id)
			if not user_object:
				logger.warning(f'Could not find user for audio: {message.from_user}')
				await message.reply('Произошла ошибка, попробуй еще раз')
				return

			audio = await BotAudio.create(file_id=file_id, file_path=source_file.name, user=user_object, volume_level=user_object.volume_level)

			ret = await run_transformation(source_file.name, user_object.volume_level, destination_file.name)
			if ret:
				logger.warning(f'Convert failed: code {ret}')

			with open(destination_file.name, 'rb') as sending_file:
				await bot.send_voice(chat_id=message.chat.id, voice=sending_file, caption=f'@{(await bot.me).username}',
				                     reply_markup=types.InlineKeyboardMarkup(1, [
					                     [types.InlineKeyboardButton(f'🔈 Громкость {user_object.volume_level * 100:.0f}%',
					                                                 callback_data=f'switch_volume_{audio.hash}')]
				                     ]))


def get_volume_inline_choose_keyboard(audio: BotAudio):
	keyboard = []
	for step in VOLUME_CHANGING_STEPS:
		keyboard.append(
			[
				types.InlineKeyboardButton(f'🔈 -{step}%', callback_data=f'run_{audio.hash}_-{step}'),
				types.InlineKeyboardButton(f'🔊 +{step}%', callback_data=f'run_{audio.hash}_+{step}')
			]
		)
	return types.InlineKeyboardMarkup(3, keyboard)


async def on_choose_volume(query: types.CallbackQuery):
	audio_hash = query.data.split('_')[-1]
	audio = await BotAudio.get_or_none(hash=audio_hash)
	if not audio:
		await query.bot.answer_callback_query(query.id, text='Не удалось найти войс. Перешли мне сообщение пожалуйста ещё раз', show_alert=True)
		return

	await query.bot.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id,
	                                          reply_markup=get_volume_inline_choose_keyboard(audio))


async def on_change_volume(query: types.CallbackQuery):
	await query.bot.send_chat_action(chat_id=query.message.chat.id, action=types.ChatActions.RECORD_AUDIO)

	audio_hash, volume = query.data.split('_')[-2:]

	audio = await BotAudio.get_or_none(hash=audio_hash)
	if not audio or not os.path.exists(audio.file_path):
		await query.bot.answer_callback_query(query.id, text='Не удалось найти войс. Перешли мне сообщение пожалуйста ещё раз', show_alert=True)
		return

	user = await BotUser.get_or_none(id=query.from_user.id)
	modifiers = dict()
	for step in VOLUME_CHANGING_STEPS:
		modifiers[f'-{step}'] = -step / 100.0
		modifiers[f'+{step}'] = +step / 100.0
	volume = max((user.volume_level if user else 1) + modifiers.get(volume, 0), 0.01)
	if user:
		user.volume_level = volume
		await user.save()
	await query.bot.answer_callback_query(query.id, text=f'Громкость: {volume * 100:.0f}%', show_alert=False)

	with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as destination_file:
		ret = await run_transformation(audio.file_path, volume, destination_file.name)
		if ret:
			logger.warning(f'Convert failed: code {ret}')
		with open(destination_file.name, 'rb') as audio_file_fp:
			await query.bot.send_voice(chat_id=query.message.chat.id,
			                           voice=audio_file_fp,
			                           caption=f'@{(await query.bot.me).username}',
			                           reply_markup=get_volume_inline_choose_keyboard(audio))
			try:
				await query.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
			except aiogram.exceptions.MessageToDeleteNotFound:
				logger.warning(f'Looks like message {query.message.message_id} in chat {query.message.chat.id} was already deleted. Fine.')


async def delete_old_audios():
	PENDING_PERIOD = 3600 * 48
	now = datetime.datetime.now()
	for filename in glob.glob('/tmp/*.mp3') + glob.glob('/tmp/*.ogg'):
		if not os.path.isfile(filename):
			continue
		file_modified_at = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
		if (now - file_modified_at).total_seconds() > PENDING_PERIOD:
			logger.info(f'Removing old recording: {filename}')
			os.unlink(filename)


async def schedule_repeated_task(coroutine, interval: int, timeout: int = 5):
	await asyncio.sleep(timeout)
	while True:
		try:
			await coroutine()
		except Exception:
			logger.exception(f'Failed to perform task {coroutine}')
		await asyncio.sleep(interval)


def setup(dp: Dispatcher):
	dp.register_message_handler(send_welcome, commands=['start'], content_types=ContentType.TEXT, chat_type=[types.ChatType.PRIVATE])

	dp.register_message_handler(on_voice, content_types=types.ContentType.VOICE)
	dp.register_message_handler(on_voice, content_types=types.ContentType.AUDIO)
	dp.register_callback_query_handler(on_choose_volume, regexp='^switch_volume_[0-9a-z]+$')
	dp.register_callback_query_handler(on_choose_volume, regexp='^setvol_')  # catching old-format callbacks queries here

	dp.register_callback_query_handler(on_change_volume, regexp='^run_[0-9a-z]+_[\+-]('
	                                                            + '|'.join(map(str, VOLUME_CHANGING_STEPS)) + ')$')

	loop = asyncio.get_event_loop()
	loop.create_task(schedule_repeated_task(delete_old_audios, 3600 * 24))
