import io
import logging

import aiohttp
import asyncio
import os
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError


logger = logging.getLogger(__name__)

if not os.path.exists("cache"):
    os.makedirs("cache")

current_dir = os.path.dirname(__file__)

rarity_backgrounds = {
    "Common": os.path.join(current_dir, "backgrounds", "common.png"),
    "Uncommon": os.path.join(current_dir, "backgrounds", "uncommon.png"),
    "Rare": os.path.join(current_dir, "backgrounds", "rare.png"),
    "Epic": os.path.join(current_dir, "backgrounds", "epic.png"),
    "Legendary": os.path.join(current_dir, "backgrounds", "legendary.png"),
    "Mythic": os.path.join(current_dir, "backgrounds", "mythic.png"),
    "Icon Series": os.path.join(current_dir, "backgrounds", "idolo.png"),
    "DARK SERIES": os.path.join(current_dir, "backgrounds", "dark.png"),
    "Star Wars Series": os.path.join(current_dir, "backgrounds", "starwars.png"),
    "MARVEL SERIES": os.path.join(current_dir, "backgrounds", "marvel.png"),
    "DC SERIES": os.path.join(current_dir, "backgrounds", "dc.png"),
    "Gaming Legends Series": os.path.join(current_dir, "backgrounds", "gaming.png"),
    "Shadow Series": os.path.join(current_dir, "backgrounds", "shadow.png"),
    "Slurp Series": os.path.join(current_dir, "backgrounds", "slurp.png"),
    "Lava Series": os.path.join(current_dir, "backgrounds", "lava.png"),
    "Frozen Series": os.path.join(current_dir, "backgrounds", "ice.png"),
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

                        combined_image = await combine_with_background(session, rarity, icon_path, background_path, name, image_url)
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
            icon = Image.open(io.BytesIO(image_data)).convert("RGBA").resize(background.size, Image.Resampling.LANCZOS)
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
