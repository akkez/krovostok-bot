import random
import string

from tortoise import fields
from tortoise.models import Model


class BotUser(Model):
    id = fields.BigIntField(pk=True)
    bot = fields.CharField(max_length=128, index=True)
    username = fields.CharField(null=True, max_length=256, index=True)
    first_name = fields.CharField(null=True, max_length=256)
    last_name = fields.CharField(null=True, max_length=256)
    language_code = fields.CharField(null=True, max_length=64)
    created_at = fields.DatetimeField(auto_now_add=True)

    messages: fields.ReverseRelation["models.BotMessage"]
    audios: fields.ReverseRelation["models.BotAudio"]

    volume_level = fields.FloatField(default=1.0)

    class Meta:
        table = "bot_users"


class BotMessage(Model):
    id = fields.BigIntField(pk=True)
    user: fields.ForeignKeyRelation[BotUser] = fields.ForeignKeyField(
        "models.BotUser", related_name="messages", null=True, on_delete=fields.SET_NULL
    )
    text = fields.CharField(null=True, max_length=10000)
    update = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "bot_messages"


def generate_random_key(length):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


class BotAudio(Model):
    id = fields.IntField(pk=True)
    file_id = fields.CharField(max_length=256)
    file_path = fields.CharField(max_length=512)
    user: fields.ForeignKeyRelation[BotUser] = fields.ForeignKeyField(
        "models.BotUser", related_name="audios", null=True, on_delete=fields.SET_NULL
    )
    hash = fields.CharField(max_length=16, default=lambda: generate_random_key(16), index=True)
    volume_level = fields.FloatField()
    minus = fields.CharField(max_length=256)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "bot_audios"
