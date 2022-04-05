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

from src.models import BotAudio, BotUser, BotMessage
from src.config import Config

logger = logging.getLogger(__name__)

VOLUME_CHANGING_STEPS = [30, 50, 70]
DEFAULT_MINUS = 'kurtez'
FILENAME_BY_MINUS = {
    'kurtez': 'kurtez.mp3',
    'govno': 'govno.mp3',
    'jaguar': 'jaguar.mp3',
}


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


async def run_transformation(
        input_filepath: str, volume: float, minus: str, output_filepath: str,
    ):
    """
    the other way to do the same is (see https://github.com/kkroening/ffmpeg-python):
        inputs = [ffmpeg.input(minus).filter('volume', float(volume / 100.0)),
                  ffmpeg.input(filename)]
        result, _ = ffmpeg.filter(inputs, 'amix', inputs=2, duration='shortest').output(output_file).run()
    """
    minus = Path(__file__).absolute().parent.parent / 'files' / FILENAME_BY_MINUS[minus]
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

            audio = await BotAudio.create(
                file_id=file_id,
                file_path=source_file.name,
                user=user_object,
                volume_level=user_object.volume_level,
                minus=DEFAULT_MINUS,
            )

            ret = await run_transformation(
                input_filepath=source_file.name,
                volume=user_object.volume_level,
                minus=DEFAULT_MINUS,
                output_filepath=destination_file.name,
            )
            if ret:
                logger.warning(f'Convert failed: code {ret}')

            with open(destination_file.name, 'rb') as sending_file:
                await bot.send_voice(
                    chat_id=message.chat.id,
                    voice=sending_file,
                    caption=f'@{(await bot.me).username}',
                    reply_markup=get_initial_markup(user_object, audio),
                )


def get_initial_markup(user_object: BotUser, audio: BotAudio):
    markup=types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            f'🔈 Громкость: {user_object.volume_level * 100:.0f}%',
            callback_data=f'switch_volume_{audio.hash}',
        ),
    )
    markup.row(
        types.InlineKeyboardButton(
            f'🔈 Минус: {audio.minus}',
            callback_data=f'switch_minus_{audio.hash}',
        )
    )
    return markup


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


def get_minus_inline_choose_keyboard(audio: BotAudio):
    keyboard = []
    keyboard.append(
        [
            types.InlineKeyboardButton(f'🔈 {minus}', callback_data=f'minus_{audio.hash}_{minus}')
            for minus in FILENAME_BY_MINUS
        ]
    )
    return types.InlineKeyboardMarkup(1, keyboard)


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
    await update_audio(
        query=query,
        user=user,
        audio=audio,
        volume=volume,
        minus=audio.minus,
    )


async def on_choose_minus(query: types.CallbackQuery):
    audio_hash = query.data.split('_')[-1]
    audio = await BotAudio.get_or_none(hash=audio_hash)
    if not audio:
        await query.bot.answer_callback_query(query.id, text='Не удалось найти войс. Перешли мне сообщение пожалуйста ещё раз', show_alert=True)
        return

    await query.bot.edit_message_reply_markup(chat_id=query.message.chat.id, message_id=query.message.message_id,
                                              reply_markup=get_minus_inline_choose_keyboard(audio))


async def on_change_minus(query: types.CallbackQuery):
    await query.bot.send_chat_action(chat_id=query.message.chat.id, action=types.ChatActions.RECORD_AUDIO)

    audio_hash, minus = query.data.split('_')[-2:]

    audio = await BotAudio.get_or_none(hash=audio_hash)
    if not audio or not os.path.exists(audio.file_path):
        await query.bot.answer_callback_query(query.id, text='Не удалось найти войс. Перешли мне сообщение пожалуйста ещё раз', show_alert=True)
        return

    if minus not in FILENAME_BY_MINUS:
        await query.bot.answer_callback_query(query.id, text='Не удалось найти минусовку.', show_alert=True)
        return

    user = await BotUser.get_or_none(id=query.from_user.id)
    volume = user.volume_level if user else 1

    audio.minus = minus
    await audio.save()
    await query.bot.answer_callback_query(query.id, text=f'Минус: {minus}', show_alert=False)
    await update_audio(
        query=query,
        user=user,
        audio=audio,
        volume=volume,
        minus=audio.minus,
    )


async def update_audio(
        query: types.CallbackQuery,
        user: BotUser,
        audio: BotAudio,
        volume: float,
        minus: str,
):
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as destination_file:
        ret = await run_transformation(
            input_filepath=audio.file_path,
            volume=volume,
            minus=minus,
            output_filepath=destination_file.name,
        )
        if ret:
            logger.warning(f'Convert failed: code {ret}')
        with open(destination_file.name, 'rb') as audio_file_fp:
            await query.bot.send_voice(
                chat_id=query.message.chat.id,
                voice=audio_file_fp,
                caption=f'@{(await query.bot.me).username}',
                reply_markup=get_initial_markup(user, audio),
            )
            try:
                await query.bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
            except aiogram.exceptions.MessageToDeleteNotFound:
                logger.warning(f'Looks like message {query.message.message_id} in chat {query.message.chat.id} was already deleted. Fine.')


async def send_stats(message: types.Message):
    user_id = message.chat.id if message.chat else None
    if not user_id or int(user_id) not in Config.ADMIN_USERS:
        logger.warning(f'{message.chat} wants to have a chat btw')
        return

    now = datetime.datetime.now()
    day_ago = now - datetime.timedelta(days=1)
    week_ago = now - datetime.timedelta(days=7)
    month_ago = now - datetime.timedelta(days=30)
    audios_day, audios_week, audios_month, audios_total = \
        await BotAudio.filter(created_at__gte=day_ago).count(), \
        await BotAudio.filter(created_at__gte=week_ago).count(), \
        await BotAudio.filter(created_at__gte=month_ago).count(), \
        await BotAudio.all().count()

    users_day, users_week, users_month, users_total = \
        await BotUser.filter(created_at__gte=day_ago).count(), \
        await BotUser.filter(created_at__gte=week_ago).count(), \
        await BotUser.filter(created_at__gte=month_ago).count(), \
        await BotUser.all().count()

    messages_day, messages_week, messages_month, messages_total = \
        await BotMessage.filter(created_at__gte=day_ago).count(), \
        await BotMessage.filter(created_at__gte=week_ago).count(), \
        await BotMessage.filter(created_at__gte=month_ago).count(), \
        await BotMessage.all().count()

    await message.reply(f'📡 Stats: day / week / month / total\n'
                        f'🔊 Audios processed: {audios_day} / {audios_week} / {audios_month} / {audios_total}\n'
                        f'😎 New Users: {users_day} / {users_week} / {users_month} / {users_total}\n'
                        f'📝 Messages: {messages_day} / {messages_week} / {messages_month} / {messages_total}')


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
    dp.register_message_handler(send_stats, commands=['stats'], content_types=ContentType.TEXT, chat_type=[types.ChatType.PRIVATE])

    dp.register_message_handler(on_voice, content_types=types.ContentType.VOICE)
    dp.register_message_handler(on_voice, content_types=types.ContentType.AUDIO)
    dp.register_callback_query_handler(on_choose_volume, regexp='^switch_volume_[0-9a-z]+$')
    dp.register_callback_query_handler(on_choose_volume, regexp='^setvol_')  # catching old-format callbacks queries here

    dp.register_callback_query_handler(on_change_volume, regexp='^run_[0-9a-z]+_[\+-]('
                                                                + '|'.join(map(str, VOLUME_CHANGING_STEPS)) + ')$')

    dp.register_callback_query_handler(on_choose_minus, regexp='^switch_minus_[0-9a-z]+$')
    dp.register_callback_query_handler(on_change_minus, regexp='^minus_[0-9a-z]+_[0-9a-z]+$')

    loop = asyncio.get_event_loop()
    loop.create_task(schedule_repeated_task(delete_old_audios, 3600 * 24))
