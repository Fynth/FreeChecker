import math
import platform
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from typing import Any

import aiosqlite
from aiogram import Dispatcher, Bot, Router, F, types
from aiogram.exceptions import TelegramBadRequest
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

from utils import *

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


logger = logging.getLogger(__name__)

router = Router()


@asynccontextmanager
async def get_db_connection():
    async with aiosqlite.connect("telegram_users.sqlite") as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


active_login_tasks = {}  # Словарь для отслеживания активных задач
user_messages = {}
# client = MongoClient("mongodb://admin:Pguppgdn@194.87.243.172:27018")
# db = client["checkerdb"]
# collection = db["users"]


bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router)


global general_exchange_code, general_user_account_id, general_path

class TelegramUser:
    def __init__(self, user_id, username=None):
        self.user_id = user_id
        self.username = username

    async def save(self, cursor):

        # Проверяем, существует ли пользователь в базе данных
        await cursor.execute(
            "SELECT login_count FROM users WHERE user_id = ?", (self.user_id,)
        )
        row = await cursor.fetchone()

        if row:
            # Если пользователь существует, увеличиваем login_count на 1
            new_login_count = row[0] + 1
            await cursor.execute(
                "UPDATE Users SET login_count = ? WHERE user_id = ?",
                (new_login_count, self.user_id),
            )
        else:
            # Если пользователь не существует, создаем новую запись с login_count = 1
            await cursor.execute(
                "INSERT INTO Users (user_id, username, login_count) VALUES (?, ?, ?)",
                (self.user_id, self.username, 1),
            )

    @staticmethod
    async def get_all_by_telegram_id(cursor, user_id):
        await cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return TelegramUser(row[1], row[2])
        return None

    @staticmethod
    async def create(cursor, user_id, username):
        await cursor.execute(
            "INSERT INTO Users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )


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

    async def wait_for_device_code_completion(self, code: str) -> EpicUser:
        while True:
            async with self.http.request(
                method="POST",
                url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token",
                headers={
                    "Authorization": f"basic {SWITCH_TOKEN}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "device_code",
                    "device_code": code,
                },
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


# async def set_affiliate(
#     session: aiohttp.ClientSession,
#     account_id: str,
#     access_token: str,
#     affiliate_name: str = "Kaayyy",
# ) -> str | Any:
#     async with session.post(
#         f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/SetAffiliateName?profileId=common_core",
#         headers={
#             "Authorization": f"Bearer {access_token}",
#             "content-type": "application/json",
#         },
#         json={"affiliateName": affiliate_name},
#     ) as resp:
#         if resp.status != 200:
#             return f"Error setting affiliate name ({resp})"
#         else:
#             return await resp.json()


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
        if profileid=="common_core&rvn=-1":
            creation_date = (
                profile_data.get("profileChanges", [{}])[0]
                .get("profile", {})
                .get("created", "Unknown")
            )
            if creation_date != "Unknown":
                creation_date = datetime.strptime(
                    creation_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                ).strftime("%d/%m/%Y")
            profile_data["creation_date"] = creation_date

            vbucks_categories = [
                "Currency:MtxPurchased",
                "Currency:MtxEarned",
                "Currency:MtxGiveaway",
                "Currency:MtxPurchaseBonus",
            ]

            total_vbucks = 0
            profile_items = (
                profile_data.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})
            )
            for item_id, item_data in profile_items.items():
                if item_data.get("templateId") in vbucks_categories:
                    total_vbucks += item_data.get("quantity", 0)
            profile_data["totalAmount"] = total_vbucks

            async with session.get(
                    f"https://account-public-service-prod03.ol.epicgames.com/account/api/public/account/{info["account_id"]}/externalAuths",
                    headers={"Authorization": f"bearer {info["access_token"]}"},
            ) as external_resp:
                if external_resp.status != 200:
                    profile_data["externalAuths"] = {}
                else:
                    external_auths = await external_resp.json()
                    profile_data["externalAuths"] = external_auths



        return profile_data


async def get_account_library(
            session: aiohttp.ClientSession, info: dict
    ):
    async with session.get(
            f"https://library-service.live.use1a.ol.epicgames.com/library/api/public/collection/EGS_STATIC_OWNED_COLLECTION/item/account/{info['account_id']}",
            headers={
                "Authorization": f"Bearer {info['access_token']}",
                "content-type": "application/json",
            },
            json = {},
    ) as resp:
        if resp.status != 200:
            return f"Error ({resp.status})"
        else:
            account_library = await resp.json()
            return account_library


async def delete_external_auths(session: aiohttp.ClientSession, info: dict, external_auth):
    async with session.delete(
            f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{info['account_id']}/externalAuths/{external_auth}",
            headers={
                "Authorization": f"Bearer {info['access_token']}",
                "content-type": "application/json",
            },
            json = {},
    ) as resp:
        if resp.status != 204:
            return f"Error ({resp.status})"


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


async def get_cosmetic_type(cosmetic_id: str) -> str | None:
    """
    Определяет тип косметики по её ID.
    :param cosmetic_id: ID косметики.
    :return: Тип косметики или None, если тип не найден.
    """
    for pattern, cosmetic_type in COSMETIC_PATTERNS.items():
        if pattern.search(cosmetic_id):
            return cosmetic_type
    return None


async def combine_images(
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
    text1 = f" {item_count} {item_type}"
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
        text_width1, text_height1 = (
            text_bbox1[2] - text_bbox1[0],
            text_bbox1[3] - text_bbox1[1],
        )
        text_width2, text_height2 = (
            text_bbox2[2] - text_bbox2[0],
            text_bbox2[3] - text_bbox2[1],
        )
        text_width3, text_height3 = (
            text_bbox3[2] - text_bbox3[0],
            text_bbox3[3] - text_bbox3[1],
        )
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
            cosmetic_types = [
                await get_cosmetic_type(info["id"]) for info in img_info_list
            ]
            sorted_images = [
                img
                for _, img in sorted(
                    zip(img_info_list, images),
                    key=lambda x: (
                        item_order.index(cosmetic_types[img_info_list.index(x[0])])
                        if cosmetic_types[img_info_list.index(x[0])] in item_order
                        else 999
                    ),
                )
            ]
        else:
            sorted_images = images
        combined_image = await combine_images(
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
    cosmetic_info_tasks = [get_cosmetic_info(item_id, session) for item_id in ids]
    info_list = await asyncio.gather(*cosmetic_info_tasks, return_exceptions=True)
    for idx, result in enumerate(info_list):
        if isinstance(result, Exception):
            logger.error(f"Error fetching cosmetic info for {ids[idx]}: {result}")
            info_list[idx] = {"id": ids[idx], "rarity": "Common", "name": "Unknown"}
    sorted_ids = [
        item_id
        for _, item_id in sorted(
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

#
# async def get_profile_info(session: aiohttp.ClientSession, user: EpicUser) -> dict:
#     async with session.post(
#         f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{user.account_id}/client/QueryProfile?profileId=common_core&rvn=-1",
#         headers={"Authorization": f"bearer {user.access_token}"},
#         json={},
#     ) as resp:
#         if resp.status != 200:
#             return {"error": f"Error fetching profile info ({resp.status})"}
#         profile_info = await resp.json()
#
#         creation_date = (
#             profile_info.get("profileChanges", [{}])[0]
#             .get("profile", {})
#             .get("created", "Unknown")
#         )
#         if creation_date != "Unknown":
#             creation_date = datetime.strptime(
#                 creation_date, "%Y-%m-%dT%H:%M:%S.%fZ"
#             ).strftime("%d/%m/%Y")
#         profile_info["creation_date"] = creation_date
#
#         async with session.get(
#             f"https://account-public-service-prod03.ol.epicgames.com/account/api/public/account/{user.account_id}/externalAuths",
#             headers={"Authorization": f"bearer {user.access_token}"},
#         ) as external_resp:
#             if external_resp.status != 200:
#                 profile_info["externalAuths"] = {}
#             else:
#                 external_auths = await external_resp.json()
#                 profile_info["externalAuths"] = external_auths
#
#         return profile_info


# async def get_vbucks_info(session: aiohttp.ClientSession, user: EpicUser) -> dict:
#     async with session.post(
#         f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{user.account_id}/client/QueryProfile?profileId=common_core&rvn=-1",
#         headers={
#             "Authorization": f"bearer {user.access_token}",
#             "Content-Type": "application/json",
#         },
#         json={},
#     ) as resp:
#         if resp.status != 200:
#             return {"error": f"Error fetching V-Bucks info ({resp.status})"}
#         data = await resp.json()
#
#         vbucks_categories = [
#             "Currency:MtxPurchased",
#             "Currency:MtxEarned",
#             "Currency:MtxGiveaway",
#             "Currency:MtxPurchaseBonus",
#         ]
#
#         total_vbucks = 0
#         profile_items = (
#             data.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})
#         )
#         for item_id, item_data in profile_items.items():
#             if item_data.get("templateId") in vbucks_categories:
#                 total_vbucks += item_data.get("quantity", 0)
#
#         return {"totalAmount": total_vbucks}


async def get_game_profile_info(session: aiohttp.ClientSession, user: EpicUser) -> dict:
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
        current_season = attributes.get("season", [])
        past_seasons = attributes.get("past_seasons", [])
        total_wins = attributes.get("lifetime_wins")
        total_matches = (
            sum(
                season.get("numHighBracket", 0)
                + season.get("numLowBracket", 0)
                + season.get("numHighBracket_LTM", 0)
                + season.get("numLowBracket_LTM", 0)
                + season.get("numHighBracket_Ar", 0)
                + season.get("numLowBracket_Ar", 0)
                for season in past_seasons
            )
            + current_season.get("numHighBracket", 0)
            + current_season.get("numLowBracket", 0)
            + current_season.get("numHighBracket_LTM", 0)
            + current_season.get("numLowBracket_LTM", 0)
            + current_season.get("numHighBracket_Ar", 0)
            + current_season.get("numLowBracket_Ar", 0)
        )

        try:
            # Получаем значение last_match_end_datetime из attributes
            last_login_raw = attributes.get("last_match_end_datetime", "N/A")

            if last_login_raw != "N/A":
                # Парсим дату с учетом формата ISO 8601
                last_played_date = datetime.strptime(
                    last_login_raw, "%Y-%m-%dT%H:%M:%S.%fZ"
                )

                # Преобразуем в offset-aware datetime (добавляем UTC временную зону)
                last_played_date = last_played_date.replace(tzinfo=UTC)

                # Текущее время в UTC
                current_time = datetime.now(UTC)

                # Вычисляем разницу в днях
                days_since_last_played = (current_time - last_played_date).days

                # Форматируем дату для вывода
                last_played_str = last_played_date.strftime("%d/%m/%y")
                last_played_info = f"{last_played_str} ({days_since_last_played} дней)"
            else:
                # Если last_match_end_datetime отсутствует
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

            for current_user_info in user_info_list:
                account_id = current_user_info["id"]
                display_name = current_user_info.get("displayName", "Unknown")

                response_text = f"Username: {display_name}\nAccount ID: {account_id}\n"

                psn_auth = current_user_info.get("externalAuths", {}).get("psn")
                if psn_auth:
                    response_text += f"\nAccount ID PSN: {psn_auth['externalAuthId']}\n"
                    response_text += (
                        f"PSN Username: {psn_auth['externalDisplayName']}\n"
                    )

                nintendo_auth = current_user_info.get("externalAuths", {}).get("nintendo")
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

        user = await epic_generator.wait_for_device_code_completion(code=device_code)
        exchange_code = await epic_generator.create_exchange_code(user)
        path = "C:\\Program Files\\Epic Games\\Fortnite\\FortniteGame\\Binaries\\Win64"
        data = f"launch_game:{str(path)}:{str(exchange_code)}:{str(user.account_id)}"
        print(sys.getsizeof(data))
        launch_command = (
            "<code>"
            f'start -WorkingDirectory "C:\\Program Files\\Epic Games\\Fortnite\\FortniteGame\\Binaries\\Win64" '
            f'-FilePath "{path}\\FortniteLauncher.exe" '
            f'-ArgumentList "-AUTH_LOGIN=unused -AUTH_PASSWORD={exchange_code} -AUTH_TYPE=exchangecode -epicapp=Fortnite -epicenv=Prod -EpicPortal -epicuserid={user.account_id}"'
            "</code>"
        )

        await message.answer(
            f"Start the game using the following command:\n\n{launch_command}",
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


async def get_user_settings(user_id):
    logging.info(f"Вызов get_user_settings для user_id={user_id}")
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            )
            result = await cursor.fetchone()
            if result:
                return dict(result)


@dp.message(Command("start"))
async def start(message: Message):
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cursor:
                await TelegramUser.create(
                    cursor=cursor,
                    user_id=message.from_user.id,
                    username=message.from_user.username,
                )
        await message.answer("""
            Welcome to checker!
            
        List of bot commands:
        /login - Login account to check
        /launch - launch game with your account
        /settings - settings, personalisation for bot
        """)

    except Exception as e:
        logger.error("error in start task", e)


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
                chat_id=message.chat.id, message_id=user_messages[user_id]
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
            epic_generator.wait_for_device_code_completion(code=device_code)
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
        async with get_db_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT need_additional_info_message, autodelete_external_auths, all_items_enabled FROM users WHERE user_id = ?",
                    (message.from_user.id,),
                )
                row = await cursor.fetchone()
                need_additional_info_message = (
                    row["need_additional_info_message"] if row else None
                )
                autodelete_external_auths = (
                    row["autodelete_external_auths"] if row else None
                )
        settings = await get_user_settings(message.from_user.id)

        async with aiohttp.ClientSession() as session:
            await bot.delete_message(
                chat_id=message.chat.id, message_id=url_device_message.message_id
            )
            # set_affiliate_response = await set_affiliate(
            #     session, current_user.account_id, current_user.access_token, "Kaayyy"
            # )
            # logger.info("set_affiliate worked")
            # if isinstance(set_affiliate_response, str):
            #     if "403" in set_affiliate_response:
            #         logger.info(
            #             "Ошибка получения информации (Аккаунт заблокирован)",
            #         )
            #     else:
            #         await message.answer(text=set_affiliate_response)
            #     return
            account_info = await get_account_info(session, current_user)
            logger.info("get_account_info worked")
            if "error" in account_info:
                await message.answer(account_info["error"])
                return
            game_profile = await get_profile(
                session,
                {
                    "account_id": current_user.account_id,
                    "access_token": current_user.access_token,
                },
                "athena",
            )
            game_profiles_items = game_profile.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})

            common_core_profile_info = await get_profile(
                session,
                info={
                    "account_id": current_user.account_id,
                    "access_token": current_user.access_token,
                },
                profileid="common_core&rvn=-1"
            )
            creation_date = common_core_profile_info.get("creation_date", "Unknown")
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
                f"💰 Кошелек: {common_core_profile_info.get('totalAmount', 0)}\n"
                f"🏷 Дата создания: {creation_date}\n"
            )
            external_auths_message_text = ""
            if external_auths:
                connected_accounts_message = "Подключенные аккаунты\n"

                for auth in external_auths:
                    auth_type = auth.get("type", "Неизвестно").lower()
                    display_name = auth.get("externalDisplayName", "Неизвестно")
                    external_type = auth.get("type", "Unknown")
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
                    if autodelete_external_auths:
                        await delete_external_auths(
                            session,
                            {
                                "account_id": current_user.account_id,
                                "access_token": current_user.access_token,
                            },
                            external_type
                        )
                        external_auths_message_text += f"{external_type} auth deleted\n"

            else:
                connected_accounts_message = "Подключенных аккаунтов нет\n"
            logger.info("Sent connected accounts information")
            game_profile_info = await get_game_profile_info(session, current_user)
            if "error" in game_profile_info:
                await message.answer(game_profile_info["error"])
                return
            # library  = await get_account_library(
            #     session,
            #     {
            #         "account_id": current_user.account_id,
            #         "access_token": current_user.access_token,
            #     },
            # )
            # print(library)

            if need_additional_info_message:
                additional_info_message = (
                    f"Дополнительная информация (BR & ZB)\n"
                    f"🆔 Уровень аккаунта: {game_profile_info['account_level']}\n"
                    f"🏆 Всего побед: {game_profile_info['total_wins']}\n"
                    f"🎟 Всего матчей: {game_profile_info['total_matches']}\n"
                    f"🕒 Последняя сыгранная игра: {game_profile_info['last_played_info']}\n"
                )

                logger.info("Sent additional information")
                seasons_info_embeds = game_profile_info["seasons_info"]
                if seasons_info_embeds:
                    seasons_info_message = (
                        "Информация о прошлом сезоне (BR и ZB)\n\n"
                        + "\n".join(seasons_info_embeds)
                    )
                else:
                    seasons_info_message = "Информации о прошлом сезоне нет"

                logger.info("Sent seasons information")

            username = message.from_user.username

            item_groups = {
                "Skins": [],  # Список для предметов
                "Backpacks": [],
                "Pickaxes": [],
                "Emotes": [],
                "Gliders": [],
                "Wraps": [],
                "Sprays": [],
                "Items": []
            }
            game_profile_items_values = list(
                game_profiles_items.values()
            )
            filtered_items = filter(
                lambda filtered_item: filtered_item.get("attributes", {}).get("item_seen") is not None,
                game_profile_items_values,
            )
            for item in filtered_items:
                try:
                    template_id = item.get("templateId", "")
                    if idpattern.match(template_id):
                        item_type = await get_cosmetic_type(template_id)
                        item = template_id.split(":")[1]
                        if item_type and settings.get(f"{item_type}_enabled".lower()):
                            item_groups[item_type].append(item)
                        if settings.get(f"all_items_enabled"):
                            item_groups["Items"].append(item)
                except Exception as e:
                    logger.error(
                        f"Ошибка при получении значений из profile.values() : {e}"
                    )
                    continue

            combined_images = []
            for group in item_groups:
                if group in item_groups:
                    sorted_ids = await sort_ids_by_rarity(item_groups[group], session)
                    if sorted_ids:

                        image_data = await create_img(
                            sorted_ids,
                            session,
                            username=username,
                            sort_by_rarity=False,
                            group=group,
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
                            logger.error(f"Ошибка в цикле groups: {e}")
                            continue
                    else:
                        logger.warning(f"No items found for group {group}. Skipping.")
                        continue

            if isinstance(game_profile, str):
                await message.answer(game_profile)
                return
            if external_auths_message_text:
                await message.answer(external_auths_message_text)
            await message.answer(message_text)
            await message.answer(connected_accounts_message)
            await message.answer(additional_info_message)
            await message.answer(seasons_info_message)
            await message.answer_media_group(media=combined_images)
            async with get_db_connection() as conn:
                async with conn.cursor() as cursor:
                    await telegram_user.save(cursor)
            if message.from_user.id in active_login_tasks:
                del active_login_tasks[message.from_user.id]
    except Exception as e:
        logger.error(f"Ошибка: {e}")


class SettingsCallback(CallbackData, prefix="settings"):
    menu: str
    action: str
    section: str


class ItemsCallback(CallbackData, prefix="items"):
    menu: str
    action: str
    field: str


async def build_keyboard(menu_name: str, user_id: int) -> InlineKeyboardMarkup:
    menu = MENU_CONFIG[menu_name]
    builder = InlineKeyboardBuilder()

    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT * FROM users 
                                            WHERE user_id = ?""",
                (user_id,),
            )
            user = await cursor.fetchone()

            # Если пользователя нет - создаем
            if not user:
                await cursor.execute(
                    """INSERT INTO users (user_id) 
                             VALUES (?)""",
                    (user_id,),
                )
                await conn.commit()
                await cursor.execute(
                    """SELECT * FROM users 
                                    WHERE user_id = ?""",
                    (user_id,),
                )
                user = await cursor.fetchone()

        # Добавляем переключатели для полей
        if "fields" in menu:
            for field, label in menu["fields"].items():
                # Получаем значение из БД (индекс поля + 1, так как user_id первый)
                status = "✅" if user[field] else "❌"

                builder.button(
                    text=f"{label} {status}",
                    callback_data=ItemsCallback(
                        menu=menu_name, action="toggle", field=field
                    ).pack(),
                )

        # Добавляем кнопки навигации
        if "buttons" in menu:
            for btn in menu["buttons"]:
                builder.button(
                    text=btn["text"],
                    callback_data=SettingsCallback(
                        menu=menu_name, action="navigate", section=btn["menu"]
                    ).pack(),
                )

        # Добавляем кнопку "Назад"
        if "back" in menu:
            builder.button(
                text="🔙 Назад",
                callback_data=SettingsCallback(
                    menu=menu_name, action="navigate", section=menu["back"]
                ).pack(),
            )

    # Оптимизируем расположение кнопок
    builder.adjust(2, repeat=True)
    return builder.as_markup()


@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    await message.delete()
    sent = await message.answer(
        text=MENU_CONFIG["main"]["title"],
        reply_markup=await build_keyboard("main", message.from_user.id),
    )
    # Сохраняем ID сообщения для последующего обновления
    user_messages[message.from_user.id] = sent.message_id


@router.callback_query(SettingsCallback.filter(F.action == "navigate"))
async def handle_navigation(
    callback: types.CallbackQuery, callback_data: SettingsCallback
):
    await callback.answer()
    await callback.message.edit_text(
        text=MENU_CONFIG[callback_data.section]["title"],
        reply_markup=await build_keyboard(callback_data.section, callback.from_user.id),
    )


@router.callback_query(ItemsCallback.filter(F.action == "toggle"))
async def handle_toggle(callback: CallbackQuery, callback_data: ItemsCallback):
    try:
        user_id = callback.from_user.id
        field = callback_data.field

        async with get_db_connection() as conn:
            async with conn.cursor() as cursor:
                # Получаем текущее состояние
                await cursor.execute(
                    f"SELECT {field} FROM users WHERE user_id = ?", (user_id,)
                )
                result = await cursor.fetchone()
                current_state = result[0] if result else None

                # Вычисляем новое состояние
                new_state = 0 if current_state else 1

                # Обновляем только если состояние изменится
                await cursor.execute(
                    f"UPDATE users SET {field} = ? WHERE user_id = ?",
                    (new_state, user_id),
                )
                await conn.commit()

                # Проверяем реальное изменение
                await cursor.execute(
                    f"SELECT {field} FROM users WHERE user_id = ?", (user_id,)
                )
                result = await cursor.fetchone()
                updated_state = result[0] if result else None

                if current_state == updated_state:
                    await callback.answer("ℹ️ Состояние не изменилось")
                    return

        # Обновляем клавиатуру
        new_keyboard = await build_keyboard(callback_data.menu, user_id)
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        await callback.answer("⚙️ Настройка обновлена!")

    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("ℹ️ Состояние не изменилось")
        else:
            logger.error(f"Telegram error: {e}")
            await callback.answer("⚠️ Ошибка обновления")

    except Exception as e:
        logger.error(f"Toggle error: {e}")
        await callback.answer("⚠️ Ошибка обновления")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

    print("Telegram-бот запустился")
