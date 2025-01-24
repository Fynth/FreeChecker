import base64
import io
import json
import logging
import re
import sqlite3

import aiohttp
import asyncio
import os
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


logger = logging.getLogger(__name__)

if not os.path.exists("cache"):
    os.makedirs("cache")

current_dir = os.path.dirname(__file__)
TOKEN = "7280187426:AAFoH-W21uUGi9X2CqAD09NIKutlY8cSha8"
directory_actual = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(directory_actual, "fonts", "font.ttf")

order = {
    "Skins": "skins_enabled",
    "Backpacks": "backpacks_enabled",
    "Pickaxes": "pickaxes_enabled",
    "Emotes": "emotes_enabled",
    "Gliders": "gliders_enabled",
    "Wraps": "wraps_enabled",
    "Sprays": "sprays_enabled",
    "All items": "all_items_enabled",
}

automation = {
    "Автоудаление друзей": "autodelete_friends",
    "Автоудаление привязанных аккаунтов": "autodelete_external_auths",
}

COSMETIC_PATTERNS = {
    re.compile(r"character_|CID"): "Skins",
    re.compile(r"BID_|backpack"): "Backpacks",
    re.compile(
        r"pickaxe_|pickaxe_id_|defaultpickaxe|halloweenScythe|happyPickaxe|sickleBatPickaxe|skiIcepickaxe|spikypickaxe"
    ): "Pickaxes",
    re.compile(r"EID|emoji"): "Emotes",
    re.compile(
        r"glider|founderumbrella|founderglider|solo_umbrella|umbrella"
    ): "Gliders",
    re.compile(r"wrap"): "Wraps",
    re.compile(r"spray|SPID"): "Sprays",
}

idpattern = re.compile(r"Athena(.*?):(.*?)_(.*)")

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
            "sprays_enabled": "Граффити",
            "all_items_enabled": "Все предметы"
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

def init_db():
    conn = sqlite3.connect("telegram_users.sqlite")
    cursor = conn.cursor()

    cursor.execute(
        """CREATE TABLE Users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            login_count INTEGER DEFAULT 0
        );
        
        CREATE TABLE Settings (
            setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            fortnite_enabled BOOLEAN DEFAULT 1,
            transaction_enabled BOOLEAN DEFAULT 0,
            autodelete_friends BOOLEAN DEFAULT 0,
            autodelete_external_auths BOOLEAN DEFAULT 0,
            my_username_enabled BOOLEAN DEFAULT 1,
            bot_username_enabled BOOLEAN DEFAULT 1,
            logo_enabled BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        );
        
        CREATE TABLE Commands (
            command_id INTEGER PRIMARY KEY AUTOINCREMENT,
            command_name TEXT UNIQUE NOT NULL,
            command_type TEXT NOT NULL
        );
        
        CREATE TABLE Logins (
            login_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            login_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        );
        
        CREATE TABLE Customization (
            customization_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            skins_enabled BOOLEAN DEFAULT 1,
            backpacks_enabled BOOLEAN DEFAULT 1,
            pickaxes_enabled BOOLEAN DEFAULT 1,
            emotes_enabled BOOLEAN DEFAULT 1,
            gliders_enabled BOOLEAN DEFAULT 1,
            wraps_enabled BOOLEAN DEFAULT 1,
            banners_enabled BOOLEAN DEFAULT 1,
            sprays_enabled BOOLEAN DEFAULT 1,
            all_items_enabled BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        );"""
    )

    conn.commit()
    return conn, cursor


DEFAULT_SETTINGS = {
    "user_id": None,
    "language": "en",
    "show_skins": True,
    "show_backpacks": True,
    "show_pickaxes": True,
    "show_emotes": True,
    "show_gliders": True,
    "show_wraps": True,
    "show_sprays": True,
    "show_online_status": True,
    "auto_delete_friends": False,
    "auto_delete_foreign_accounts": False,
    "auto_delete__archive_items": False,
    "auto_close_profile": False,
}

rarity_backgrounds = {
    "Common": os.path.join(current_dir, "backgrounds", "common.png"),
    "Uncommon": os.path.join(current_dir, "backgrounds", "uncommon.png"),
    "Rare": os.path.join(current_dir, "backgrounds", "rare.png"),
    "Epic": os.path.join(current_dir, "backgrounds", "epic.png"),
    "Legendary": os.path.join(current_dir, "backgrounds", "legendary.png"),
    "Mythic": os.path.join(current_dir, "backgrounds", "mythic.png"),
    "MARVEL SERIES": os.path.join(current_dir, "backgrounds", "marvel.png"),
    "DARK SERIES": os.path.join(current_dir, "backgrounds", "dark.png"),
    "DC SERIES": os.path.join(current_dir, "backgrounds", "dc.png"),
    "FROZEN SERIES": os.path.join(current_dir, "backgrounds", "frozen.png"),
    "GAMING LEGENDS SERIES": os.path.join(current_dir, "backgrounds", "gaming.png"),
    "LAVA SERIES": os.path.join(current_dir, "backgrounds", "lava.png"),
    "SHADOW SERIES": os.path.join(current_dir, "backgrounds", "shadow.png"),
    "SLURP SERIES": os.path.join(current_dir, "backgrounds", "slurp.png"),
    "STAR WARS SERIES": os.path.join(current_dir, "backgrounds", "star_wars.png"),
    "ICON SERIES": os.path.join(current_dir, "backgrounds", "icon_series.png"),
}

special_rarities = {
    "ICON SERIES",
    "DARK SERIES",
    "STAR WARS SERIES",
    "GAMING LEGENDS SERIES",
    "MARVEL SERIES",
    "DC SERIES",
    "SHADOW SERIES",
    "SLURP SERIES",
    "LAVA SERIES",
    "FROZEN SERIES",
}


Image.MAX_IMAGE_PIXELS = None

VERIFICATION_COUNT_FILE = "verification.json"


def load_verification_counts():
    if os.path.exists(VERIFICATION_COUNT_FILE):
        with open(VERIFICATION_COUNT_FILE, "r") as f:
            return json.load(f)
    return {}


def save_verification_counts(counts):
    with open(VERIFICATION_COUNT_FILE, "w") as f:
        json.dump(counts, f)


def bool_to_emoji(value):
    return "✅" if value else "❌"


def country_to_flag(country_code):
    if len(country_code) != 2:
        return country_code
    return chr(ord(country_code[0]) + 127397) + chr(ord(country_code[1]) + 127397)


def mask_email(email):
    """
    Маскирует локальную часть email-адреса, оставляя только первый и последний символы.
    Например: "example@example.com" -> "e*****e@example.com".
    """
    if not email or "@" not in email:
        return email

    # Регулярное выражение для замены локальной части email
    masked_email = re.sub(r"(?<=^.)(.*?)(?=.@)", lambda m: "*" * len(m.group(1)), email)
    return masked_email


def mask_account_id(account_id):
    """
    Маскирует центральную часть account_id, оставляя первые 2 и последние 2 символа.
    Например: "1234567890" -> "12*****890".
    """
    if not account_id or len(account_id) <= 4:
        return account_id

    # Регулярное выражение для замены центральной части
    masked_id = re.sub(r"(?<=.{2}).(?=.{2}$)", "*", account_id)
    return masked_id


idpattern = re.compile(r"Athena(.*?):(.*?)_(.*?)")

current_dir = os.path.dirname(__file__)
rarity_backgrounds = {
    "Common": os.path.join(current_dir, "backgrounds", "common.png"),
    "Uncommon": os.path.join(current_dir, "backgrounds", "uncommon.png"),
    "Rare": os.path.join(current_dir, "backgrounds", "rare.png"),
    "Epic": os.path.join(current_dir, "backgrounds", "epic.png"),
    "Legendary": os.path.join(current_dir, "backgrounds", "legendary.png"),
    "Mythic": os.path.join(current_dir, "backgrounds", "mythic.png"),
    "Icon Series": os.path.join(current_dir, "backgrounds", "icon_series.png"),
    "DARK SERIES": os.path.join(current_dir, "backgrounds", "dark.png"),
    "Star Wars Series": os.path.join(current_dir, "backgrounds", "star_wars.png"),
    "MARVEL SERIES": os.path.join(current_dir, "backgrounds", "marvel.png"),
    "DC SERIES": os.path.join(current_dir, "backgrounds", "dc.png"),
    "Gaming Legends Series": os.path.join(current_dir, "backgrounds", "gaming.png"),
    "Shadow Series": os.path.join(current_dir, "backgrounds", "shadow.png"),
    "Slurp Series": os.path.join(current_dir, "backgrounds", "slurp.png"),
    "Lava Series": os.path.join(current_dir, "backgrounds", "lava.png"),
    "Frozen Series": os.path.join(current_dir, "backgrounds", "frozen.png"),
}

rarity_priority = {
    "Mythic": 1,
    "Legendary": 2,
    "Epic": 13,
    "Rare": 14,
    "Uncommon": 15,
    "Common": 16,
    "Icon Series": 11,
    "DARK SERIES": 3,
    "Star Wars Series": 5,
    "MARVEL SERIES": 6,
    "DC SERIES": 12,
    "Gaming Legends Series": 9,
    "Shadow Series": 10,
    "Slurp Series": 4,
    "Lava Series": 7,
    "Frozen Series": 8,
}

# mythic_ids = {
#     "cid_017_athena_commando_m",
#     "cid_028_athena_commando_f",
#     "cid_029_athena_commando_f_halloween",
#     "cid_032_athena_commando_m_medieval",
#     "cid_033_athena_commando_f_medieval",
#     "cid_035_athena_commando_m_medieval",
#     "cid_a_256_athena_commando_f_uproarbraids_8iozw",
#     "cid_052_athena_commando_f_psblue",
#     "cid_095_athena_commando_m_founder",
#     "cid_096_athena_commando_f_founder",
#     "cid_113_athena_commando_m_blueace",
#     "cid_114_athena_commando_f_tacticalwoodland",
#     "cid_175_athena_commando_m_celestial",
#     "cid_089_athena_commando_m_retrogrey",
#     "cid_085_athena_commando_m_twitch",
#     "cid_174_athena_commando_f_carbidewhite",
#     "cid_183_athena_commando_m_modernmilitaryred",
#     "cid_207_athena_commando_m_footballdudea",
#     "cid_208_athena_commando_m_footballdudeb",
#     "cid_209_athena_commando_m_footballdudec",
#     "cid_210_athena_commando_f_footballgirla",
#     "cid_030_athena_commando_m_halloween",
#     "cid_211_athena_commando_f_footballgirlb",
#     "cid_212_athena_commando_f_footballgirlc",
#     "cid_238_athena_commando_f_footballgirld",
#     "cid_239_athena_commando_m_footballduded",
#     "cid_240_athena_commando_f_plague",
#     "cid_313_athena_commando_m_kpopfashion",
#     "cid_082_athena_commando_m_scavenger",
#     "cid_090_athena_commando_m_tactical",
#     "cid_342_athena_commando_m_streetracermetallic",
#     "cid_434_athena_commando_f_stealthhonor",
#     "cid_441_athena_commando_f_cyberscavengerblue",
#     "cid_479_athena_commando_f_davinci",
#     "cid_657_athena_commando_f_techopsblue",
#     "cid_478_athena_commando_f_worldcup",
#     "cid_515_athena_commando_m_barbequelarry",
#     "cid_516_athena_commando_m_blackwidowrogue",
#     "cid_657_athena_commando_f_techOpsBlue",
#     "cid_619_athena_commando_f_techllama",
#     "cid_660_athena_commando_f_bandageninjablue",
#     "cid_703_athena_commando_m_cyclone",
#     "cid_084_athena_commando_m_assassin",
#     "cid_083_athena_commando_f_tactical",
#     "cid_761_athena_commando_m_cyclonespace",
#     "cid_783_athena_commando_m_aquajacket",
#     "cid_964_athena_commando_m_historian_869bc",
#     "cid_084_athena_commando_m_assassin",
#     "cid_039_athena_commando_f_disco",
#     "cid_116_athena_commando_m_carbideblack",
#     "eid_ashtonboardwalk",
#     "eid_ashtonsaltlake",
#     "eid_bendy",
#     "eid_bollywood",
#     "eid_chicken",
#     "cid_757_athena_commando_f_wildcat",
#     "cid_080_athena_commando_m_space",
#     "eid_crackshotclock",
#     "eid_dab",
#     "eid_fireworksspin",
#     "eid_fresh",
#     "eid_griddles",
#     "eid_hiphop01",
#     "eid_iceking",
#     "eid_kpopdance03",
#     "eid_macaroon_45lhe",
#     "eid_ridethepony_athena",
#     "eid_robot",
#     "eid_rockguitar",
#     "eid_solartheory",
#     "eid_taketheL",
#     "eid_tapshuffle",
#     "cid_386_athena_commando_m_streetopsstealth",
#     "cid_371_athena_commando_m_speedymidnight",
#     "eid_torchsnuffer",
#     "eid_trophycelebrationfncs",
#     "eid_trophycelebration",
#     "eid_twistdaytona",
#     "eid_zest_q1k5v",
#     "founderumbrella",
#     "founderglider",
#     "glider_id_001",
#     "glider_id_002_medieval",
#     "glider_id_003_district",
#     "glider_id_004_disco",
#     "glider_id_014_dragon",
#     "glider_id_090_celestial",
#     "glider_id_176_blackmondaycape_4p79k",
#     "glider_id_206_donut",
#     "umbrella_snowflake",
#     "glider_warthog",
#     "glider_voyager",
#     "bid_001_bluesquire",
#     "bid_002_royaleknight",
#     "bid_004_blackknight",
#     "bid_005_raptor",
#     "bid_025_tactical",
#     "eid_electroshuffle",
#     "cid_850_athena_commando_f_skullbritecube",
#     "bid_024_space",
#     "bid_027_scavenger",
#     "bid_029_retrogrey",
#     "bid_030_tacticalrogue",
#     "bid_055_psburnout",
#     "bid_072_vikingmale",
#     "bid_103_clawed",
#     "bid_102_buckles",
#     "bid_138_celestial",
#     "bid_468_cyclone",
#     "bid_520_cycloneuniverse",
#     "halloweenscythe",
#     "pickaxe_id_013_teslacoil",
#     "pickaxe_id_015_holidaycandycane",
#     "pickaxe_id_021_megalodon",
#     "pickaxe_id_019_heart",
#     "pickaxe_id_029_assassin",
#     "pickaxe_id_077_carbidewhite",
#     "pickaxe_id_088_psburnout",
#     "pickaxe_id_116_celestial",
#     "pickaxe_id_294_candycane",
#     "pickaxe_id_359_cyclonemale",
#     "pickaxe_id_376_fncs",
#     "pickaxe_id_508_historianmale_6bqsw",
#     "pickaxe_id_011_medieval",
#     "eid_takethel",
#     "eid_floss",
#     "pickaxe_id_804_fncss20male",
#     "pickaxe_id_stw007_basic",
#     "pickaxe_lockjaw",
# }

CLIENT_ID = "ec684b8c687f479fadea3cb2ad83f5c6"
CLIENT_SECRET = "e1f31c211f28413186262d37a13fc84d"
IOS_CLIENT_ID = "3f69e56c7649492c8cc29f1af08a8a12"
IOS_CLIENT_SECRET = "b51ee9cb12234f50a69efa67ef53812e"

CREDENTIALS = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")).decode(
    "utf-8"
)
IOS_CREDENTIALS = base64.b64encode(
    f"{IOS_CLIENT_ID}:{IOS_CLIENT_SECRET}".encode("utf-8")
).decode("utf-8")

SWITCH_TOKEN = "OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3"
IOS_TOKEN = "MzQ0NmNkNzI2OTRjNGE0NDg1ZDgxYjc3YWRiYjIxNDE6OTIwOWQ0YTVlMjVhNDU3ZmI5YjA3NDg5ZDMxM2I0MWE="


async def get_cosmetic_requirements(filename):
    # URL API для получения всех косметических предметов
    url = "https://fortnite-api.com/v2/cosmetics/br"

    # Проверяем, существует ли файл, и читаем уже записанные идентификаторы
    existing_ids = set()
    if os.path.exists(filename):
        with open(filename, "r") as file:
            existing_ids = set(file.read().splitlines())

    try:
        # Создаём асинхронную сессию
        async with aiohttp.ClientSession() as session:
            # Выполняем GET-запрос
            async with session.get(url) as response:
                # Проверяем статус ответа
                if response.status == 200:
                    # Читаем JSON-ответ
                    data = await response.json()

                    # Извлекаем массив косметических предметов
                    cosmetics = data.get("data", [])

                    # Открываем файл для записи новых идентификаторов
                    with open(filename, "a") as file:
                        # Перебираем косметические предметы
                        for cosmetic in cosmetics:
                            cosmetic_id = cosmetic["id"]
                            # Проверяем, есть ли идентификатор уже в файле
                            if cosmetic_id not in existing_ids:
                                # Записываем новый идентификатор в файл
                                file.write(cosmetic_id + "\n")
                                print(f"Добавлен новый идентификатор: {cosmetic_id}")
                            else:
                                print(f"Идентификатор уже существует: {cosmetic_id}")
                else:
                    print(f"Ошибка: Статус {response.status}")

    except aiohttp.ClientError as e:
        print(f"Ошибка запроса: {e}")


def read_skin_ids(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file if line.strip()]


# async def download_image(session, id, semaphore):
#     imgpath = f"./cache/{id}.png"
#     if os.path.exists(imgpath) and os.path.isfile(imgpath):
#         print(f"Изображение {imgpath} уже существует.")
#         return
#
#     urls = [
#         f"https://fortnite-api.com/images/cosmetics/br/{id}/icon.png",
#         f"https://fortnite-api.com/images/cosmetics/br/{id}/smallicon.png"
#     ]
#     async with semaphore:
#         for url in urls:
#             try:
#                 async with session.get(url) as resp:
#                     if resp.status == 200:
#                         with open(imgpath, "wb") as f:
#                             f.write(await resp.read())
#                         print(f"Загружено изображение: {imgpath}")
#                         break
#             except Exception as e:
#                 print(f"Ошибка при загрузке {url}: {e}")
#         else:
#             with open(imgpath, "wb") as f:
#                    f.write(open("tbd.png", "rb").read())
#             print(f"Не удалось загрузить изображение для {id}, используется изображение по умолчанию.")


async def is_valid_image(session, image_url, icon_path):
    try:
        async with session.get(image_url) as response:
            with open(icon_path, "wb") as f:
                f.write(await response.read())
                icon = Image.open(icon_path)
                return True
    except (IOError, SyntaxError):
        return False


async def download_images(session, cosmetic_id, semaphore):
    directory_actual = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(directory_actual, "cache", f"{cosmetic_id}.png")

    cosmetic_data_url = f"https://fortnite-api.com/v2/cosmetics/br/{cosmetic_id}"
    image_urls = [
        f"https://fortnite-api.com/images/cosmetics/br/{cosmetic_id}/icon.png",
        f"https://fortnite-api.com/images/cosmetics/br/{cosmetic_id}/smallicon.png",
    ]
    async with semaphore:
        try:
            async with session.get(cosmetic_data_url) as response:
                if response.status == 200:
                    with open(icon_path, "wb") as f:
                        data = await response.json()
                        image_url = (
                            image_urls[0]
                            if await is_valid_image(session, image_urls[0], icon_path)
                            else image_urls[1]
                        )
                        rarity = (
                            data.get("data", {})
                            .get("rarity", "Common")
                            .get("displayValue")
                        )
                        name = data.get("data", {}).get("name", "Без названия")
                        background_path = rarity_backgrounds.get(
                            rarity, rarity_backgrounds["Common"]
                        )
                        logger.info(f"Combining image {name} with background")

                        combined_image = await combine_with_background(
                            session, rarity, icon_path, background_path, name, image_url
                        )
                        combined_image.save(icon_path)
                    print(f"Загружено изображение: {icon_path}")
        except Exception as e:
            print(f"Ошибка при загрузке {cosmetic_data_url}: {e}")


async def combine_with_background(
    session,
    rarity: str,
    icon_path: str,
    background_path: str,
    name: str,
    image_url: str,
):
    directory_actual = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(directory_actual, "fonts", "font.ttf")

    try:
        async with session.get(image_url) as response:
            background = Image.open(background_path).convert("RGBA")
            image_data = await response.read()
            icon = (
                Image.open(io.BytesIO(image_data))
                .convert("RGBA")
                .resize(background.size, Image.Resampling.LANCZOS)
            )
            background.paste(icon, (0, 0), icon)
            draw = ImageDraw.Draw(background)

            max_font_size = 40
            if rarity.upper() in special_rarities:
                max_font_size *= 2

            min_font_size = 10
            max_text_width = background.width - 20
            font_size = max_font_size

            name = name.upper()

            while font_size > min_font_size:
                font = ImageFont.truetype(font_path, size=font_size)
                text_bbox = draw.textbbox((0, 0), name, font=font)
                text_width, text_height = (
                    text_bbox[2] - text_bbox[0],
                    text_bbox[3] - text_bbox[1],
                )

                if text_width <= max_text_width:
                    break

                font_size -= 1

            font = ImageFont.truetype(font_path, size=font_size)
            text_bbox = draw.textbbox((0, 0), name, font=font)
            text_width, text_height = (
                text_bbox[2] - text_bbox[0],
                text_bbox[3] - text_bbox[1],
            )
            text_x = (background.width - text_width) // 2

            muro_y_position = int(background.height * 0.80)
            muro_height = background.height - muro_y_position

            muro = Image.new(
                "RGBA", (background.width, muro_height), (0, 0, 0, int(255 * 0.7))
            )
            background.paste(muro, (0, muro_y_position), muro)

            text_y = muro_y_position + (muro_height - text_height) // 2

            draw.text((text_x, text_y), name, fill="white", font=font)

            img_byte_arr = io.BytesIO()
            background.save(img_byte_arr, format="PNG")

            logger.info(f"Combined image {name} with background successfully")
            return background

    except UnidentifiedImageError:
        print(f"Файл {icon_path} не является валидным изображением.")
        return None


async def main():
    # await get_cosmetic_requirements("skins.txt")
    skin_ids = read_skin_ids("skins.txt")
    semaphore = asyncio.Semaphore(2)
    async with aiohttp.ClientSession() as session:
        tasks = (download_images(session, id, semaphore) for id in skin_ids)

        # await download_images(session, "Emoji_PoolParty", semaphore)
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
