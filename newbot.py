import math
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from aiogram import Dispatcher, Bot
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    Message,
    InputMediaPhoto,
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)

from utils2 import *

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    conn = sqlite3.connect("telegram_users.sqlite")
    conn.row_factory = sqlite3.Row  # Для доступа к данным по имени столбца
    try:
        yield conn
    finally:
        conn.close()

active_login_tasks = {}  # Словарь для отслеживания активных задач
user_messages = {}
# client = MongoClient("mongodb://admin:Pguppgdn@194.87.243.172:27018")
# db = client["checkerdb"]
# collection = db["users"]


bot = Bot(token=TOKEN)
dp = Dispatcher()



class TelegramUser:
    def __init__(self, telegram_id, username=None):
        self.telegram_id = telegram_id
        self.username = username

    def save(self, cursor):
        # Проверяем, существует ли пользователь в базе данных
        cursor.execute(
            "SELECT login_count FROM Users WHERE telegram_id = ?", (self.telegram_id,)
        )
        row = cursor.fetchone()

        if row:
            # Если пользователь существует, увеличиваем login_count на 1
            new_login_count = row[0] + 1
            cursor.execute(
                "UPDATE Users SET login_count = ? WHERE telegram_id = ?",
                (new_login_count, self.telegram_id),
            )
        else:
            # Если пользователь не существует, создаем новую запись с login_count = 1
            cursor.execute(
                "INSERT INTO Users (telegram_id, username, login_count) VALUES (?, ?, ?)",
                (self.telegram_id, self.username, 1),
            )

    @staticmethod
    def get_by_telegram_id(cursor, telegram_id):
        cursor.execute("SELECT * FROM Users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        if row:
            return TelegramUser(row[1], row[2], row[3])
        return None


class Settings:
    def __init__(
        self,
        user_id,
        fortnite_enabled=False,
        transaction_enabled=False,
        autodelete_friends=False,
        autodelete_external_auths=False,
        my_username_enabled=False,
        bot_username_enabled=False,
        logo_enabled=False,
    ):
        self.user_id = user_id
        self.fortnite_enabled = fortnite_enabled
        self.transaction_enabled = transaction_enabled
        self.autodelete_friends = autodelete_friends
        self.autodelete_external_auths = autodelete_external_auths
        self.my_username_enabled = my_username_enabled
        self.bot_username_enabled = bot_username_enabled
        self.logo_enabled = logo_enabled

    def save(self, cursor):
        cursor.execute(
            "INSERT OR REPLACE INTO Settings (user_id, fortnite_enabled, transaction_enabled, autodelete_friends, autodelete_external_auths, my_username_enabled, bot_username_enabled, logo_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.user_id,
                self.fortnite_enabled,
                self.transaction_enabled,
                self.autodelete_friends,
                self.autodelete_external_auths,
                self.my_username_enabled,
                self.bot_username_enabled,
                self.logo_enabled,
            ),
        )

    @staticmethod
    def get_by_user_id(cursor, user_id):
        cursor.execute("SELECT * FROM Settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return Settings(
                row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8]
            )
        return None


class Login:
    def __init__(self, user_id, login_time=datetime.now()):
        self.user_id = user_id
        self.login_time = login_time

    def save(self, cursor):
        cursor.execute(
            "INSERT INTO Logins (user_id, login_time) VALUES (?, ?)",
            (self.user_id, self.login_time),
        )

    @staticmethod
    def get_by_user_id(cursor, user_id):
        cursor.execute("SELECT * FROM Logins WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        return [Login(row[1], row[2]) for row in rows]

    @staticmethod
    def get_count_by_user_id(cursor, user_id):
        cursor.execute("SELECT * FROM Logins WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        return [Login(row[1], row[2]) for row in rows]


class Customization:
    def __init__(
        self,
        user_id,
        skins_enabled=True,
        backpacks_enabled=True,
        pickaxes_enabled=True,
        emotes_enabled=True,
        gliders_enabled=True,
        wraps_enabled=True,
        sprays_enabled=True,
        banners_enabled=True,
        all_items_enabled=False,
    ):
        self.user_id = user_id
        self.skins_enabled = skins_enabled
        self.backpacks_enabled = backpacks_enabled
        self.pickaxes_enabled = pickaxes_enabled
        self.emotes_enabled = emotes_enabled
        self.gliders_enabled = gliders_enabled
        self.wraps_enabled = wraps_enabled
        self.sprays_enabled = sprays_enabled
        self.banners_enabled = banners_enabled
        self.all_items_enabled = all_items_enabled

    def save(self, cursor):
        cursor.execute(
            "INSERT OR REPLACE INTO Customization (user_id, skins_enabled, backpacks_enabled, pickaxes_enabled, emotes_enabled, gliders_enabled, wraps_enabled, banners_enabled, all_items_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.user_id,
                self.skins_enabled,
                self.backpacks_enabled,
                self.pickaxes_enabled,
                self.emotes_enabled,
                self.gliders_enabled,
                self.wraps_enabled,
                self.banners_enabled,
                self.all_items_enabled,
            ),
        )

    @staticmethod
    def get_by_user_id(cursor, user_id):
        cursor.execute("SELECT * FROM Customization WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return Customization(
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
            )
        return None


class EpicUser:
    def __init__(self, data=None):
        self.raw = data
        self.access_token = data.get("access_token", "")
        self.expires_in = data.get("expires_in", 0)
        self.expires_at = data.get("expires_at", "")
        self.token_type = data.get("token_type", "")
        self.refresh_token = data.get("refresh_token", "")
        self.refresh_expires = data.get("refresh_expires", "")
        self.refresh_expires_at = data.get("refresh_expires_at", "")
        self.account_id = data.get("account_id", "")
        self.client_id = data.get("client_id", "")
        self.internal_client = data.get("internal_client", False)
        self.client_service = data.get("client_service", "")
        self.display_name = data.get("displayName", "")
        self.app = data.get("app", "")
        self.in_app_id = data.get("in_app_id", "")


class EpicGenerator:
    def __init__(self) -> None:
        self.user_agent = (
            f"DeviceAuthGenerator/{platform.system()}/{platform.version()}"
        )
        self.http = aiohttp.ClientSession(headers={"User-Agent": self.user_agent})
        self.access_token = ""
        self.http: aiohttp.ClientSession

    async def start(self) -> None:
        self.access_token = await self.get_access_token()

    async def get_access_token(self) -> str:
        # async with self.http.request(
        #     method = "POST",
        #         url = f"https://www.epicgames.com/id/api/redirect?clientId={CLIENT_ID}&responseType=code",
        #
        # )
        async with self.http.request(
            method="POST",
            url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"basic {SWITCH_TOKEN}",
            },
            data={
                "grant_type": "client_credentials",
            },
        ) as response:
            data = await response.json()
            return data["access_token"]

    async def create_device_code(self) -> tuple:
        async with self.http.request(
            method="POST",
            url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/deviceAuthorization",
            headers={
                "Authorization": f"bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as response:
            data = await response.json()
            return data["verification_uri_complete"], data["device_code"]

    async def create_exchange_code(self, user: EpicUser) -> str:
        async with self.http.request(
            method="GET",
            url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/exchange",
            headers={"Authorization": f"bearer {user.access_token}"},
        ) as response:
            data = await response.json()
            return data["code"]

    async def wait_for_device_code_completion(self, user_id, code: str) -> EpicUser:
        while True:
            async with self.http.request(
                method="POST",
                url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token",
                headers={
                    "Authorization": f"basic {SWITCH_TOKEN}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "device_code", "device_code": code},
            ) as request:
                token = await request.json()

                if request.status == 200:
                    break
                else:
                    if (
                        token["errorCode"]
                        == "errors.com.epicgames.account.oauth.authorization_pending"
                    ):
                        pass
                    elif token["errorCode"] == "g":
                        pass
                    else:
                        print(json.dumps(token, sort_keys=False, indent=4))

                await asyncio.sleep(1)

        async with self.http.request(
            method="GET",
            url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/exchange",
            headers={"Authorization": f"bearer {token['access_token']}"},
        ) as request:
            exchange = await request.json()

        async with self.http.request(
            method="POST",
            url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token",
            headers={
                "Authorization": f"basic {IOS_CREDENTIALS}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "exchange_code",
                "exchange_code": exchange["code"],
            },
        ) as request:
            auth_information = await request.json()

            return EpicUser(data=auth_information)

    async def create_device_auths(self, user: EpicUser) -> dict:
        async with self.http.request(
            method="POST",
            url=f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{user.account_id}/deviceAuth",
            headers={
                "Authorization": f"bearer {user.access_token}",
                "Content-Type": "application/json",
            },
        ) as request:
            data = await request.json()
            return {
                "device_id": data["deviceId"],
                "account_id": data["accountId"],
                "secret": data["secret"],
                "user_agent": data["userAgent"],
                "created": {
                    "location": data["created"]["location"],
                    "ip_address": data["created"]["ipAddress"],
                    "datetime": data["created"]["dateTime"],
                },
            }

    async def get_cosmetic_info(
        cosmetic_id: str, session: aiohttp.ClientSession
    ) -> dict:
        async with session.get(
            f"https://fortnite-api.com/v2/cosmetics/br/{cosmetic_id}"
        ) as resp:
            if resp.status != 200:
                return {
                    "id": cosmetic_id,
                    "rarity": "Common",
                    "name": "Unknown",
                    "styles": [],
                }
            data = await resp.json()
            return {
                "id": cosmetic_id,
                "rarity": data.get("rarity", "Common"),
                "name": data.get("name", "Unknown"),
            }


async def set_affiliate(
    session: aiohttp.ClientSession,
    account_id: str,
    access_token: str,
    affiliate_name: str = "Kaayyy",
) -> str | Any:
    async with session.post(
        f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/SetAffiliateName?profileId=common_core",
        headers={
            "Authorization": f"Bearer {access_token}",
            "content-type": "application/json",
        },
        json={"affiliateName": affiliate_name},
    ) as resp:
        if resp.status != 200:
            return f"Error setting affiliate name ({resp.status})"
        else:
            return await resp.json()


async def get_profile(
    session: aiohttp.ClientSession, info: dict, profileid: str = "athena"
) -> str | Any:
    async with session.post(
        f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{info['account_id']}/client/QueryProfile?profileId={profileid}",
        headers={
            "Authorization": f"bearer {info['access_token']}",
            "content-type": "application/json",
        },
        json={},
    ) as resp:
        if resp.status != 200:
            return f"Error ({resp.status})"
        else:
            profile_data = await resp.json()
            return profile_data


async def get_cosmetic_info(cosmetic_id: str, session: aiohttp.ClientSession) -> dict:
    async with session.get(
        f"https://fortnite-api.com/v2/cosmetics/br/{cosmetic_id}"
    ) as resp:
        if resp.status != 200:
            return {
                "id": cosmetic_id,
                "rarity": "Common",
                "name": "Unknown",
                "styles": [],
            }
        data = await resp.json()
        rarity = data.get("data", {}).get("rarity", {}).get("displayValue", "Common")
        name = data.get("data", {}).get("name", "Unknown")
        # if cosmetic_id.lower() in mythic_ids:
        #     rarity = "Mythic"
        if name == "Unknown":
            name = cosmetic_id

        return {
            "id": cosmetic_id,
            "rarity": rarity,
            "name": name,
        }


def get_cosmetic_type(cosmetic_id: str) -> str | None:
    """
    Определяет тип косметики по её ID.
    :param cosmetic_id: ID косметики.
    :return: Тип косметики или None, если тип не найден.
    """
    for pattern, cosmetic_type in COSMETIC_PATTERNS.items():
        if pattern.search(cosmetic_id):
            return cosmetic_type
    return None


def combine_images(
    images,
    username: str,
    item_count: int,
    item_type: str,
):
    logo_filename = "logo.png"
    max_width = 1848
    max_height = 2048

    num_items = len(images)
    base_max_cols = 6
    max_cols = base_max_cols
    num_rows = math.ceil(num_items / max_cols)

    while num_rows > max_cols:
        max_cols += 1
        num_rows = math.ceil(num_items / max_cols)

    item_width = max_width // max_cols
    item_height = max_height // num_rows

    image_size = min(item_width, item_height)
    spacing = 0

    total_width = max_cols * image_size + (max_cols - 1) * spacing
    total_height = num_rows * image_size + (num_rows - 1) * spacing

    empty_space_height = image_size
    total_height += empty_space_height

    combined_image = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 255))

    # Resize images in parallel
    def resize_image(image, size):
        return image.resize(size, resample=Image.Resampling.LANCZOS)

    with ThreadPoolExecutor() as executor:
        resized_images = list(
            executor.map(resize_image, images, [(image_size, image_size)] * len(images))
        )

    # Paste resized images
    for idx, resized_image in enumerate(resized_images):
        col = idx % max_cols
        row = idx // max_cols
        position = (col * (image_size + spacing), row * (image_size + spacing))
        combined_image.paste(resized_image, position, resized_image)

    # Add logo
    logo = Image.open(logo_filename).convert("RGBA")
    logo_height = int(empty_space_height * 0.6)
    logo_width = int((logo_height / logo.height) * logo.width)
    logo_position = (
        10,
        total_height - empty_space_height + (empty_space_height - logo_height) // 2,
    )
    logo = logo.resize((logo_width, logo_height))
    combined_image.paste(logo, logo_position, logo)

    # Prepare text
    text1 = f"{item_type}: {item_count}"
    text2 = f"Checked by {username} | {datetime.now().strftime('%d/%m/%y')}"
    text3 = "t.me/Fornite_Checker_Bot"
    max_text_width = total_width - (logo_position[0] + logo_width + 10)

    # Binary search for optimal font size
    low = 8
    high = logo_height // 3
    optimal_font_size = low
    while low <= high:
        mid = (low + high) // 2
        font = ImageFont.truetype(FONT_PATH, size=mid)
        text_bbox1 = font.getbbox(text1)
        text_bbox2 = font.getbbox(text2)
        text_bbox3 = font.getbbox(text3)
        text_width1, text_height1 = text_bbox1[2] - text_bbox1[0], text_bbox1[3] - text_bbox1[1]
        text_width2, text_height2 = text_bbox2[2] - text_bbox2[0], text_bbox2[3] - text_bbox2[1]
        text_width3, text_height3 = text_bbox3[2] - text_bbox3[0], text_bbox3[3] - text_bbox3[1]
        if (
            text_width1 <= max_text_width
            and text_width2 <= max_text_width
            and text_width3 <= max_text_width
        ):
            optimal_font_size = mid
            low = mid + 1
        else:
            high = mid - 1

    font = ImageFont.truetype(FONT_PATH, size=optimal_font_size)
    text_height1 = font.getbbox(text1)[3] - font.getbbox(text1)[1]
    text_height2 = font.getbbox(text2)[3] - font.getbbox(text2)[1]
    text_height3 = font.getbbox(text3)[3] - font.getbbox(text3)[1]

    text_x1 = logo_position[0] + logo_width + 10
    text_y1 = (
        logo_position[1]
        + (empty_space_height - text_height1 - text_height2 - text_height3) // 2
    )
    text_x2 = text_x1
    text_y2 = text_y1 + text_height1 + 5
    text_x3 = text_x1
    text_y3 = text_y2 + text_height2 + 5

    draw = ImageDraw.Draw(combined_image)
    draw.text((text_x1, text_y1), text1, fill="white", font=font)
    draw.text((text_x2, text_y2), text2, fill="white", font=font)
    draw.text((text_x3, text_y3), text3, fill="white", font=font)

    return combined_image


async def create_img(
    img_ids: list,
    session: aiohttp.ClientSession,
    username: str = "DefaultUser",
    sort_by_rarity: bool = False,
    item_order: list = None,
    group: str = None,
):
    logger.info(f"Creating image for {username} with {len(img_ids)} items")

    if not os.path.exists("./cache"):
        logger.error("Cache doesn't exist")

    images = []
    img_info_list = []
    cosmetic_info_tasks = [get_cosmetic_info(img_id, session) for img_id in img_ids]

    for img_id, img_info in zip(img_ids, await asyncio.gather(*cosmetic_info_tasks)):
        try:
            imgpath = f"./cache/{img_id}.png"
            img = Image.open(imgpath)
            if img.size == (1, 1):
                raise IOError("Image is empty")
            img_info_list.append(img_info)
            images.append(img)
            logger.info(
                f"Take image {img_info['name']} with rarity {img_info['rarity']}"
            )
        except Exception as e:
            logger.error("create_img error: ", {e})
            continue

    if images:
        if sort_by_rarity:
            sorted_images = [
                img
                for _, img in sorted(
                    zip(img_info_list, images),
                    key=lambda x: rarity_priority.get(x[0]["rarity"], 6),
                )
            ]
        elif item_order:
            sorted_images = [
                img
                for _, img in sorted(
                    zip(img_info_list, images),
                    key=lambda x: (
                        item_order.index(get_cosmetic_type(x[0]["id"]))
                        if get_cosmetic_type(x[0]["id"]) in item_order
                        else 999
                    ),
                )
            ]
        else:
            sorted_images = images
        combined_image = combine_images(
            sorted_images,
            username,
            len(img_ids),
            group,
        )
        with io.BytesIO() as buffer:
            combined_image.save(buffer, "PNG")
            logger.info(f"Created final combined image for {username}")
            return bytes(buffer.getvalue())


async def sort_ids_by_rarity(ids: list, session: aiohttp.ClientSession) -> list:
    cosmetic_info_tasks = [get_cosmetic_info(id, session) for id in ids]
    info_list = await asyncio.gather(*cosmetic_info_tasks, return_exceptions=True)
    for idx, result in enumerate(info_list):
        if isinstance(result, Exception):
            logger.error(f"Error fetching cosmetic info for {ids[idx]}: {result}")
            info_list[idx] = {"id": ids[idx], "rarity": "Common", "name": "Unknown"}
    sorted_ids = [
        id
        for _, id in sorted(
            zip(info_list, ids), key=lambda x: rarity_priority.get(x[0]["rarity"], 6)
        )
    ]
    return sorted_ids



async def get_external_auths(session: aiohttp.ClientSession, user: EpicUser) -> dict:
    async with session.get(
        f"https://account-public-service-prod03.ol.epicgames.com/account/api/public/account/{user.account_id}/externalAuths",
        headers={"Authorization": f"bearer {user.access_token}"},
    ) as resp:
        if resp.status != 200:
            return {}
        external_auths = await resp.json()
        return external_auths


async def get_account_info(session: aiohttp.ClientSession, user: EpicUser) -> dict:
    async with session.get(
        f"https://account-public-service-prod03.ol.epicgames.com/account/api/public/account/{user.account_id}",
        headers={"Authorization": f"bearer {user.access_token}"},
    ) as resp:
        if resp.status != 200:
            return {"error": f"Error fetching account info ({resp.status})"}
        account_info = await resp.json()
        if "email" in account_info:
            account_info["email"] = mask_email(account_info["email"])

        creation_date = account_info.get("created", "Unknown")
        if creation_date != "Unknown":
            creation_date = datetime.strptime(
                creation_date, "%Y-%m-%dT%H:%M:%S.%fZ"
            ).strftime("%d/%m/%Y")
        account_info["creation_date"] = creation_date

        account_info["externalAuths"] = await get_external_auths(session, user)

        return account_info


async def get_profile_info(session: aiohttp.ClientSession, user: EpicUser) -> dict:
    async with session.post(
        f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{user.account_id}/client/QueryProfile?profileId=common_core&rvn=-1",
        headers={"Authorization": f"bearer {user.access_token}"},
        json={},
    ) as resp:
        if resp.status != 200:
            return {"error": f"Error fetching profile info ({resp.status})"}
        profile_info = await resp.json()

        creation_date = (
            profile_info.get("profileChanges", [{}])[0]
            .get("profile", {})
            .get("created", "Unknown")
        )
        if creation_date != "Unknown":
            creation_date = datetime.strptime(
                creation_date, "%Y-%m-%dT%H:%M:%S.%fZ"
            ).strftime("%d/%m/%Y")
        profile_info["creation_date"] = creation_date

        async with session.get(
            f"https://account-public-service-prod03.ol.epicgames.com/account/api/public/account/{user.account_id}/externalAuths",
            headers={"Authorization": f"bearer {user.access_token}"},
        ) as external_resp:
            if external_resp.status != 200:
                profile_info["externalAuths"] = {}
            else:
                external_auths = await external_resp.json()
                profile_info["externalAuths"] = external_auths

        return profile_info


async def get_vbucks_info(session: aiohttp.ClientSession, user: EpicUser) -> dict:
    async with session.post(
        f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{user.account_id}/client/QueryProfile?profileId=common_core&rvn=-1",
        headers={
            "Authorization": f"bearer {user.access_token}",
            "Content-Type": "application/json",
        },
        json={},
    ) as resp:
        if resp.status != 200:
            return {"error": f"Error fetching V-Bucks info ({resp.status})"}
        data = await resp.json()

        vbucks_categories = [
            "Currency:MtxPurchased",
            "Currency:MtxEarned",
            "Currency:MtxGiveaway",
            "Currency:MtxPurchaseBonus",
        ]

        total_vbucks = 0
        profile_items = (
            data.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})
        )
        for item_id, item_data in profile_items.items():
            if item_data.get("templateId") in vbucks_categories:
                total_vbucks += item_data.get("quantity", 0)

        return {"totalAmount": total_vbucks}


async def get_profile_stats(session: aiohttp.ClientSession, user: EpicUser) -> dict:
    async with session.post(
        f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{user.account_id}/client/QueryProfile?profileId=athena&rvn=-1",
        headers={
            "Authorization": f"bearer {user.access_token}",
            "Content-Type": "application/json",
        },
        json={},
    ) as resp:
        if resp.status != 200:
            return {"error": f"Error fetching account stats ({resp.status})"}
        data = await resp.json()

        attributes = (
            data.get("profileChanges", [{}])[0]
            .get("profile", {})
            .get("stats", {})
            .get("attributes", {})
        )
        account_level = attributes.get("accountLevel", 0)

        past_seasons = attributes.get("past_seasons", [])
        total_wins = sum(season.get("numWins", 0) for season in past_seasons)
        total_matches = sum(
            season.get("numHighBracket", 0)
            + season.get("numLowBracket", 0)
            + season.get("numHighBracket_LTM", 0)
            + season.get("numLowBracket_LTM", 0)
            + season.get("numHighBracket_Ar", 0)
            + season.get("numLowBracket_Ar", 0)
            for season in past_seasons
        )
        try:
            last_login_raw = attributes.get("last_match_end_datetime", "N/A")
            if last_login_raw != "N/A":
                last_played_date = datetime.strptime(
                    last_login_raw, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
                last_played_str = last_played_date.strftime("%d/%m/%y")
                days_since_last_played = (datetime.utcnow() - last_played_date).days
                last_played_info = f"{last_played_str} ({days_since_last_played} дней)"
            else:
                last_played_info = "LOL +1200"
        except Exception as e:
            logger.error(f"Error parsing last_match_end_datetime: {e}")
            last_played_info = "LOL +1200"
        seasons_info = []
        for season in past_seasons:
            season_info = (
                f"Сезон {season.get('seasonNumber', 'Неизвестно')}\n"
                f"› Уровень: {season.get('seasonLevel', 'Неизвестно')}\n"
                f"› Боевой пропуск куплен: {bool_to_emoji(season.get('purchasedVIP', False))}\n"
                f"› Побед в сезоне: {season.get('numWins', 0)}\n"
            )
            seasons_info.append(season_info)

        return {
            "account_level": account_level,
            "total_wins": total_wins,
            "total_matches": total_matches,
            "last_played_info": last_played_info,
            "seasons_info": seasons_info,
        }


def create_season_messages(seasons_info):
    messages = []
    current_message = "Information about temporary passes\n"
    message_length = len(current_message)

    for season_info in seasons_info:
        if message_length + len(season_info) + 2 > 4096:
            messages.append(current_message)
            current_message = "Information about temporary passes\n"
            message_length = len(current_message)

        current_message += season_info + "\n\n"
        message_length += len(season_info) + 2

    if message_length > 0:
        messages.append(current_message)

    return messages


async def fetch_user_info(session, username):
    api_url = f"https://api.proswapper.xyz/external/name/{username}"
    async with session.get(api_url) as response:
        if response.status == 200:
            response_body = await response.text()
            user_info_list = json.loads(response_body)
            return user_info_list
        return None


async def fetch_ranks_info(session, account_id):
    ranks_api_url = f"https://api.proswapper.xyz/ranks/lookup/id/{account_id}"
    async with session.get(ranks_api_url) as response:
        if response.status == 200:
            response_body = await response.text()
            ranks_info = json.loads(response_body)
            return ranks_info
        return None


@dp.message(Command("user_info"))
async def user_info(message: Message):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    try:
        username = " ".join(message.args).strip()

        if not username:
            await message.answer(
                text="Write correct username.. Use: /userinfo <username>",
            )
            return

        async with aiohttp.ClientSession() as session:
            user_info_list = await fetch_user_info(session, username)

            if not user_info_list:
                await message.answer(
                    text=f"Error while retrieving user information {username}."
                )
                return

            for user_info in user_info_list:
                account_id = user_info["id"]
                display_name = user_info.get("displayName", "Unknown")

                response_text = f"Username: {display_name}\nAccount ID: {account_id}\n"

                psn_auth = user_info.get("externalAuths", {}).get("psn")
                if psn_auth:
                    response_text += f"\nAccount ID PSN: {psn_auth['externalAuthId']}\n"
                    response_text += (
                        f"PSN Username: {psn_auth['externalDisplayName']}\n"
                    )

                nintendo_auth = user_info.get("externalAuths", {}).get("nintendo")
                if nintendo_auth:
                    for auth_id in nintendo_auth["authIds"]:
                        response_text += f"\nAccount ID Nintendo: {auth_id['id']}\n"

                ranks_info = await fetch_ranks_info(session, account_id)

                if ranks_info:
                    for item in ranks_info:
                        ranking_type = item.get("rankingType")
                        current_division_name = item.get("currentDivisionName")
                        promotion_progress = item.get("promotionProgress")

                        if ranking_type == "ranked-br":
                            response_text += (
                                f"\nRanked Battle Royale: {current_division_name}"
                            )
                            if promotion_progress:
                                response_text += f" ({promotion_progress:.0%})"
                            response_text += "\n"

                        elif ranking_type == "ranked-zb":
                            response_text += (
                                f"\nRanked Zero Build: {current_division_name}"
                            )
                            if promotion_progress:
                                response_text += f" ({promotion_progress:.0%})"
                            response_text += "\n"

                await message.answer(text=response_text)

    except Exception as e:
        await message.answer(text=f"Error: {e}")
        print(f"Error in userinfo_task: {e}")


@dp.message(Command("launch"))
async def launch_task(message: Message):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    try:
        global general_exchange_code, general_user_account_id, general_path
        epic_generator = EpicGenerator()
        await epic_generator.start()
        device_code_url, device_code = await epic_generator.create_device_code()
        await message.answer(
            text=f"Пожалуйста, авторизуйте свою учетную запись, перейдя по следующей ссылке: {device_code_url}",
        )

        user = await epic_generator.wait_for_device_code_completion(device_code)
        exchange_code = await epic_generator.create_exchange_code(user)
        path = "C:\\Program Files\\Epic Games\\Fortnite\\FortniteGame\\Binaries\\Win64"
        data = f"launch_game:{str(path)}:{str(exchange_code)}:{str(user.account_id)}"
        print(sys.getsizeof(data))
        launch_command = (
            "<code>"
            f'start /d "{path}"\\FortniteLauncher.exe '
            f"-AUTH_LOGIN=unused "
            f"-AUTH_PASSWORD={exchange_code} "
            f"-AUTH_TYPE=exchangecode "
            f"-epicapp=Fortnite "
            f"-epicenv=Prod "
            f"-EpicPortal "
            f"-epicuserid={user.account_id}"
            "</code>"
        )
        launch_command2 = (
            "<code>"
            f'start -WorkingDirectory "C:\\Program Files\\Epic Games\\Fortnite\\FortniteGame\\Binaries\\Win64" '
            f'-FilePath "{path}\\FortniteLauncher.exe" '
            f'-ArgumentList "-AUTH_LOGIN=unused -AUTH_PASSWORD={exchange_code} -AUTH_TYPE=exchangecode -epicapp=Fortnite -epicenv=Prod -EpicPortal -epicuserid={user.account_id}"'
            "</code>"
        )

        await message.answer(
            f"Start the game using the following command:\n\n{launch_command2}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(text=f"Ошибка обработки запроса: {e}")


# async def delete_friends_http(session: aiohttp.ClientSession, user: EpicUser):
#     async with session.get(
#         f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user.account_id}",
#         headers={"Authorization": f"bearer {user.access_token}"},
#     ) as resp:
#         if resp.status != 200:
#             return f"Error fetching friends list ({resp.status})"
#         friends = await resp.json()
#
#     for friend in friends:
#         async with session.delete(
#             f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user.account_id}/{friend['accountId']}",
#             headers={"Authorization": f"bearer {user.access_token}"},
#         ) as resp:
#             if resp.status != 204:
#                 print(f"Error deleting friend {friend['accountId']} ({resp.status})")
#
#
# async def delete_friends(session):
#     try:
#         with session:
#             async with session.get(
#                     f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user.account_id}",
#                     headers={"Authorization": f"bearer {user.access_token}"},
#             ) as resp:
#                 if resp.status != 200:
#                     return f"Error fetching friends list ({resp.status})"
#                 friends = await resp.json()
#             async with aiohttp.ClientSession() as session:
#                 for friend in friends:
#                     async with session.delete(
#                             f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user.account_id}/{friend['accountId']}",
#                             headers={"Authorization": f"bearer {user.access_token}"},
#                     ) as resp:
#                         if resp.status != 204:
#                             print(f"Error deleting friend {friend['accountId']} ({resp.status})")
#     except Exception as e:

@dp.message(Command("help"))
async def help_task(message: Message):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    try:
        help_text = (
            "Доступные команды:\n\n"
            "/login - Проверьте свою учетную запись Fortnite, чтобы увидеть все ваши предметы\n\n"
            "/launch - Запустите свою учетную запись Fortnite без необходимости ввода электронной почты и пароля\n\n"
            "/delete_friends - Удалить всех друзей из учетной записи Epic Games\n\n"
            "/userinfo - Получить Account ID только по имени пользователя Fortnite"
        )
        await message.answer(text=help_text)
    except Exception as e:
        await message.answer(text=f"Error: {e}")

def get_user_settings(user_id):
    logging.info(f"Вызов get_user_settings для user_id={user_id}")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT skins_enabled, backpacks_enabled, pickaxes_enabled, emotes_enabled, gliders_enabled, wraps_enabled, sprays_enabled, all_items_enabled "
            "FROM Customization WHERE user_id = ?",
            (user_id,),
        )
        result = cursor.fetchone()
        if result:
            return {
                "skins_enabled": bool(result[0]),
                "backpacks_enabled": bool(result[1]),
                "pickaxes_enabled": bool(result[2]),
                "emotes_enabled": bool(result[3]),
                "gliders_enabled": bool(result[4]),
                "wraps_enabled": bool(result[5]),
                "sprays_enabled": bool(result[6]),
                "all_items_enabled": bool(result[7]),
            }


@dp.message(Command("login"))
async def login_task(message: Message):

    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    try:
        user_id = message.from_user.id
        if user_id in active_login_tasks:
            task = active_login_tasks[user_id]
            task.cancel()
            logger.info("таска логина удалена")

            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=user_messages[user_id]
            )
            # Удаляем message_id из словаря, так как сообщение больше не существует
            del user_messages[user_id]
    except Exception as e:
        # Если сообщение с клавиатурой уже удалено или недоступно
        logger.error(f"Ошибка при удалении клавиатуры: {e}")
    try:
        logger.info("Starting login task")
        epic_generator = EpicGenerator()
        logger.info("Epicgenerator init")
        telegram_user = TelegramUser(message.from_user.id, message.from_user.username)
        await epic_generator.start()
        logger.info("Epicgenerator start")
        device_code_url, device_code = await epic_generator.create_device_code()
        logger.info("create_device_code worked")
        url_device_message = await message.answer(
            text=f"Проверьте свой аккаунт по следующей ссылке: {device_code_url}"
        )

        task = asyncio.create_task(
            epic_generator.wait_for_device_code_completion(user_id=message.from_user.id, code=device_code)
        )
        active_login_tasks[message.from_user.id] = task
        current_user = await task
        logger.info(f"User data: {current_user.__dict__}")
        if not current_user.access_token or not current_user.account_id:
            logger.error("Access token or account ID is empty")
            await message.answer(
                text="Ошибка: не удалось получить токен доступа или ID аккаунта.",
            )
            return
        with get_db_connection() as conn:
            cursor = conn.cursor()
            need_additional_info_message = cursor.execute(
                "SELECT need_additional_info_message FROM Settings WHERE user_id = ?",
                (message.from_user.id,),
            )

        async with aiohttp.ClientSession() as session:
            await bot.delete_message(chat_id=message.chat.id, message_id=url_device_message.message_id)
            set_affiliate_response = await set_affiliate(
                session, current_user.account_id, current_user.access_token, "Kaayyy"
            )
            logger.info("set_affiliate worked")
            if isinstance(set_affiliate_response, str):
                if "403" in set_affiliate_response:
                    logger.info(
                        "Ошибка получения информации (Аккаунт заблокирован)",
                    )
                else:
                    await message.answer(text=set_affiliate_response)
                return
            account_info = await get_account_info(session, current_user)
            logger.info("get_account_info worked")
            if "error" in account_info:
                await message.answer(account_info["error"])
                return
            profile = await get_profile(
                session,
                {
                    "account_id": current_user.account_id,
                    "access_token": current_user.access_token,
                },
                "athena",
            )
            if isinstance(profile, str):
                await message.answer(profile)
                return
            vbucks_info = await get_vbucks_info(session, current_user)
            if "error" in vbucks_info:
                await message.answer(vbucks_info["error"])
                return

            profile_info = await get_profile_info(session, current_user)
            creation_date = profile_info.get("creation_date", "Unknown")
            external_auths = account_info.get("externalAuths", [])
            message_text = (
                f"Информация об аккаунте\n"
                f"#️⃣ ID аккаунта: {mask_account_id(current_user.account_id)}\n"
                f"📧 Почта: {account_info.get('email', 'Unknown')}\n"
                f"🧑 Ник: {current_user.display_name}\n"
                f"🔐 Электронная почта подтверждена: {bool_to_emoji(account_info.get('emailVerified', False))}\n"
                f"👪 Родительский контроль: {bool_to_emoji(account_info.get('minorVerified', False))}\n"
                f"🔒 Наличие двухфакторной аутентификации: {bool_to_emoji(account_info.get('tfaEnabled', False))}\n"
                f"📛 Имя: {account_info.get('name', 'Unknown')}\n"
                f"🌐 Страна: {account_info.get('country', 'Unknown')} {country_to_flag(account_info.get('country', ''))}\n"
                f"💰 Кошелек: {vbucks_info.get('totalAmount', 0)}\n"
                f"🏷 Дата создания: {creation_date}\n"
            )

            await message.answer(message_text)

            if external_auths:
                connected_accounts_message = "Подключенные аккаунты\n"

                for auth in external_auths:
                    auth_type = auth.get("type", "Неизвестно").lower()
                    display_name = auth.get("externalDisplayName", "Неизвестно")
                    external_id = auth.get("externalAuthId", "Неизвестно")
                    date_added = auth.get("dateAdded", "Неизвестно")
                    if date_added != "Неизвестно":
                        date_added = datetime.strptime(
                            date_added, "%Y-%m-%dT%H:%M:%S.%fZ"
                        ).strftime("%d/%m/%Y")
                    connected_accounts_message += (
                        f"{auth_type.upper()}\n"
                        f"{external_id}\n"
                        f"Имя: {display_name}\n"
                        f"Связан: {date_added}\n\n"
                    )
            else:
                connected_accounts_message = "Подключенных аккаунтов нет\n"

            await message.answer(connected_accounts_message)
            logger.info("Sent connected accounts information")
            account_stats = await get_profile_stats(session, current_user)
            if "error" in account_stats:
                await message.answer(account_stats["error"])
                return

            if need_additional_info_message:
                additional_info_message = (
                    f"Дополнительная информация (BR & ZB)\n"
                    f"🆔 Уровень аккаунта: {account_stats['account_level']}\n"
                    f"🏆 Всего побед: {account_stats['total_wins']}\n"
                    f"🎟 Всего матчей: {account_stats['total_matches']}\n"
                    f"🕒 Последняя сыгранная игра: {account_stats['last_played_info']}\n"
                )
                await message.answer(additional_info_message)
                logger.info("Sent additional information")
                seasons_info_embeds = account_stats["seasons_info"]
                if seasons_info_embeds:
                    seasons_info_message = (
                        "Информация о прошлом сезоне (BR и ZB)\n\n"
                        + "\n".join(seasons_info_embeds)
                    )
                else:
                    seasons_info_message = "Информации о прошлом сезоне нет"
                await message.answer(seasons_info_message)
                logger.info("Sent seasons information")

                username = message.from_user.username

                settings = get_user_settings(message.from_user.id)

                item_groups = {
                    "Skins": [],  # Список для предметов
                    "Backpacks": [],
                    "Pickaxes": [],
                    "Emotes": [],
                    "Gliders": [],
                    "Wraps": [],
                    "Sprays": [],
                }
                profile_info_obj = list(
                    profile["profileChanges"][0]["profile"]["items"].values()
                )
                filtered_items = filter(
                    lambda item: item.get("attributes", {}).get("item_seen")
                    is not None,
                    profile_info_obj,
                )
                for item in filtered_items:
                    try:
                        id = item.get("templateId", "")
                        if idpattern.match(id):
                            item_type = get_cosmetic_type(id)
                            if item_type and settings.get(
                                f"{item_type}_enabled".lower()
                            ):
                                item_groups[item_type].append(id.split(":")[1])
                    except Exception as e:
                        logger.error(
                            f"Ошибка при получении значений из profile.values() : {e}"
                        )
                        continue

                combined_images = []
                for group in item_groups:
                    sorted_ids = await sort_ids_by_rarity(
                        item_groups[group], session
                    )
                    if group in item_groups:
                        sorted_ids = await sort_ids_by_rarity(
                            item_groups[group], session
                        )
                        if sorted_ids:

                            image_data = await create_img(
                                sorted_ids, session, username=username, sort_by_rarity=False, group=group,
                            )
                            if not image_data:
                                logger.error(
                                    f"Failed to generate image for group {group}. Image data is empty."
                                )
                                continue
                            try:
                                image_file = BufferedInputFile(
                                    file=image_data, filename=f"image_{group}.png"
                                )
                                combined_images.append(
                                    InputMediaPhoto(
                                        media=image_file,
                                        caption=f"Image {group}",
                                        parse_mode=None,
                                        caption_entities=None,
                                        show_caption_above_media=None,
                                        has_spoiler=None,
                                    )
                                )
                            except Exception as e:
                                logger.error(f"Ошибка: {e}")
                                continue
                        else:
                            logger.warning(
                                f"No items found for group {group}. Skipping."
                            )
                            continue


                await message.answer_media_group(media=combined_images)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                telegram_user.save(cursor)
            if message.from_user.id in active_login_tasks:
                del active_login_tasks[message.from_user.id]
    except Exception as e:
        logger.error(f"Ошибка: {e}")



@dp.message(Command("settings"))
async def settings_command(message: Message):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    sent_message = await message.answer("Настройки:", reply_markup=get_settings_keyboard())
    user_messages[message.from_user.id] = sent_message.message_id


class SettingsCallback(CallbackData, prefix="settings"):
    db_name: str  # Основное действие (navigate, toggle)
    menu: str     # Текущее меню (main, customization, automation)
    target: str   # Целевой раздел/настройка

class CustomizationCallback(CallbackData, prefix="customization"):
    db_name: str  # Основное действие (navigate, toggle)
    menu: str     # Текущее меню (main, customization, automation)
    target: str   # Целевой раздел/настройка


def get_settings_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Кастомизация",
                    callback_data=SettingsCallback(
                        db_name="Customization", menu="settings", target="customization"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Автоматизация",
                    callback_data=SettingsCallback(
                        db_name="Automation", menu="settings", target="automation"
                    ).pack(),
                )
            ],
        ]
    )
    return keyboard

@dp.callback_query(SettingsCallback.filter())
async def settings_callback_handler(
    callback: CallbackQuery, callback_data: SettingsCallback
):
    target = callback_data.target
    db_name = callback_data.db_name

    if target == "customization":
        await callback.message.edit_text(
            "Кастомизация:", reply_markup=get_customization_keyboard()
        )
    elif target == "automation":
        await callback.message.edit_text(
            "Автоматизация:", reply_markup=get_items_keyboard(callback.from_user.id, db_name, automation)
        )

def get_customization_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Какие предметы чекать",
                    callback_data=CustomizationCallback(
                        db_name="Customization", menu="customization", target="items_to_check"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Дополнительные данные",
                    callback_data=CustomizationCallback(
                        db_name="Customization", menu="customization", target="additional_data"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data=CustomizationCallback(
                        db_name="Customization", menu="customization", target="settings"
                    ).pack(),
                )
            ],
        ]
    )
    return keyboard

@dp.callback_query(CustomizationCallback.filter())
async def customization_callback_handler(
    callback: CallbackQuery, callback_data: CustomizationCallback
):
    target = callback_data.target

    if target == "items_to_check":
        await callback.message.edit_text(
            "Какие предметы чекать:", reply_markup=get_items_keyboard(callback.from_user.id, "Customization", order)
        )
    elif target == "additional_info":
        await callback.message.edit_text(
            "Дополнительные данные:", reply_markup=get_items_keyboard(callback.from_user.id, "Automation", order)
        )
    elif target == "settings":
        await callback.message.edit_text(
            "Настройки:", reply_markup=get_settings_keyboard()
        )





def get_items_keyboard(user_id, db_name, item_dict):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {db_name} WHERE user_id = ?", (user_id,))
        table = cursor.fetchone()
        if not table:
            cursor.execute(
                f"INSERT INTO {db_name} (user_id) VALUES (?)",
                (user_id,),
            )
            conn.commit()
            table = cursor.fetchone()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for item_name, field_name in item_dict.items():
        # Получаем текущее состояние (включено/выключено)
        is_enabled = table[field_name]

        # Создаем кнопку с текстом, отражающим текущее состояние
        button_text = f"{item_name} {'✅' if is_enabled else '❌'}"
        keyboar       text=button_text,
                    callback_data=ItemsCallback(
                        action="toggle", item=field_name, db_name=db_name
                    ).pack(),
                )
            ]
        )

    keyboard.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="Назад",
                callback_data=CustomizationCallback(action="back", setting="main").pack(),
            )
        ]
    )

    return keyboard


class ItemsCallback(CallbackData, prefix="items"):
    action: str  # Действие (например, "toggle")
    item: str  # Категория предмета (например, "skins", "backpacks")
    db_name: str


@dp.callback_query(ItemsCallback.filter())
async def item_toggle_callback_handler(callback: CallbackQuery, callback_data: ItemsCallback):
    user_id = callback.from_user.id
    item_name = callback_data.item
    action = callback_data.action
    db_name = callback_data.db_name
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_data = cursor.execute(
            f"SELECT * FROM {db_name} WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not db_data:
            # Если записи нет, создаем новую с настройками по умолчанию
            cursor.execute(
                f"INSERT INTO {db_name} (user_id) VALUES (?)",
                (user_id,),
            )
            conn.commit()

    if action == "toggle":
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Обновляем значение в базе данных
            cursor.execute(
                f"UPDATE {db_name} SET {item_name} = NOT {item_name} WHERE user_id = ?",
                (user_id,),
            )
            customization = cursor.execute(
                f"SELECT * FROM {db_name} WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not customization:
                # Если записи нет, создаем новую с настройками по умолчанию
                cursor.execute(
                    f"INSERT INTO {db_name} user_id = ?",
                    (user_id,),
                )
                cursor.execute(
                    f"UPDATE {db_name} SET {item_name} = NOT {item_name} WHERE user_id = ?",
                    (user_id,),
                )
            conn.commit()

            # Получаем обновленное состояние
            cursor.execute(
                f"SELECT {item_name} FROM {db_name} WHERE user_id = ?", (user_id,)
            )

            new_state = cursor.fetchone()

        # Обновляем клавиатуру только если состояние изменилось
        await callback.message.edit_reply_markup(
            reply_markup=get_items_keyboard(user_id, db_name, automation)
        )

        # Отправляем уведомление об успешном изменении
        await callback.answer(f"Изменено на {'✅' if new_state else '❌'}!")
d.inline_keyboard.append(
            [
                InlineKeyboardButton(


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

    print("Telegram-бот запустился")
