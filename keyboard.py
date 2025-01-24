import math
import platform
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    Message,
    InputMediaPhoto,
    BufferedInputFile,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from newbot import router, logger

# Конфигурация меню
MENU_CONFIG = {
    "main": {
        "title": "⚙️ Главное меню настроек",
        "buttons": [
            {"text": "🎮 Настройки предметов", "menu": "items"},
            {"text": "🔧 Другие настройки", "menu": "other"}
        ]
    },
    "items": {
        "title": "🎮 Настройки предметов",
        "fields": {
            "skins_enabled": "Скины",
            "backpacks_enabled": "Рюкзаки",
            "pickaxes_enabled": "Кирки",
            "emotes_enabled": "Эмоции",
            "gliders_enabled": "Дельтапланы",
            "wraps_enabled": "Обертки",
            "sprays_enabled": "Спреи"
        },
        "back": "main"
    },
    "other": {
        "title": "🔧 Другие настройки",
        "fields": {
            "autodelete_friends": "Автоудаление друзей",
            "autodelete_external_auths": "Автоудаление авторизаций",
            "fortnite_enabled": "Доступ к Fortnite",
            "transaction_enabled": "Транзакции",
            "my_username_enabled": "Мой username",
            "bot_username_enabled": "Username бота",
            "logo_enabled": "Логотип",
            "need_additional_info_message": "Запрос доп. информации"
        },
        "back": "main"
    }
}
user_messages = {}


class SettingsCallback(CallbackData, prefix="settings"):
    menu: str
    action: str
    section: str


class ItemsCallback(CallbackData, prefix="items"):
    menu: str
    action: str
    field: str


def get_db_connection():
    conn = sqlite3.connect('telegram_users.sqlite')
    conn.row_factory = sqlite3.Row
    return conn


def build_keyboard(menu_name: str, user_id: int) -> InlineKeyboardMarkup:
    menu = MENU_CONFIG[menu_name]
    builder = InlineKeyboardBuilder()

    with get_db_connection() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (user_id,)
        ).fetchone()

        if not user:
            conn.execute("""
                INSERT INTO users (telegram_id) 
                VALUES (?)
            """, (user_id,))
            conn.commit()
            user = conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (user_id,)
            ).fetchone()

        if "fields" in menu:
            for field, label in menu["fields"].items():
                status = "✅" if user[field] else "❌"
                builder.button(
                    text=f"{label} {status}",
                    callback_data=ItemsCallback(
                        menu=menu_name,
                        action="toggle",
                        field=field
                    ).pack()
                )

        if "buttons" in menu:
            for btn in menu["buttons"]:
                builder.button(
                    text=btn["text"],
                    callback_data=SettingsCallback(
                        menu=menu_name,
                        action="navigate",
                        section=btn["menu"]
                    ).pack()
                )

        if "back" in menu:
            builder.button(
                text="🔙 Назад",
                callback_data=SettingsCallback(
                    menu=menu_name,
                    action="navigate",
                    section=menu["back"]
                ).pack()
            )

    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    try:
        await message.delete()
        sent = await message.answer(
            text=MENU_CONFIG["main"]["title"],
            reply_markup=build_keyboard("main", message.from_user.id)
        )
        user_messages[message.from_user.id] = sent.message_id
    except Exception as e:
        logger.error(f"Settings error: {e}")
        await message.answer("⚠️ Ошибка загрузки настроек")


@router.callback_query(SettingsCallback.filter(F.action == "navigate"))
async def handle_navigation(callback: CallbackQuery, callback_data: SettingsCallback):
    await callback.answer()
    await callback.message.edit_text(
        text=MENU_CONFIG[callback_data.section]["title"],
        reply_markup=build_keyboard(callback_data.section, callback.from_user.id)
    )


@router.callback_query(ItemsCallback.filter(F.action == "toggle"))
async def handle_toggle(callback: CallbackQuery, callback_data: ItemsCallback):
    user_id = callback.from_user.id
    field = callback_data.field

    valid_fields = set()
    for menu in MENU_CONFIG.values():
        if "fields" in menu:
            valid_fields.update(menu["fields"].keys())

    if field not in valid_fields:
        await callback.answer("⚠️ Неверная настройка")
        return

    try:
        with get_db_connection() as conn:
            conn.execute(
                f"UPDATE users SET {field} = NOT {field} WHERE telegram_id = ?",
                (user_id,)
            )
            conn.commit()

        await callback.message.edit_reply_markup(
            reply_markup=build_keyboard(callback_data.menu, user_id)
        )
        await callback.answer("⚙️ Настройка обновлена!")

    except sqlite3.Error as e:
        logger.error(f"DB error: {e}")
        await callback.answer("⚠️ Ошибка базы данных")
    except Exception as e:
        logger.error(f"Toggle error: {e}")
        await callback.answer("⚠️ Ошибка обновления")


# Добавить роутер в диспетчер
def setup(dp):
    dp.include_router(router)
