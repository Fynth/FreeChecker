import json
from datetime import datetime, UTC

import aiohttp
import platform
from typing import Optional, Dict, Any

from utils import SWITCH_TOKEN, logger, bool_to_emoji


class EpicApi:
    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        self.access_token = None
        self.raw = data or {}
        self._init_from_data()
        self.http = aiohttp.ClientSession(
            headers={"User-Agent": self.user_agent}
        )

    def _init_from_data(self) -> None:
        """Инициализирует поля из переданных данных"""
        self.access_token: str = self.raw.get("access_token", "")
        self.expires_in: int = self.raw.get("expires_in", 0)
        self.expires_at: str = self.raw.get("expires_at", "")
        self.token_type: str = self.raw.get("token_type", "")
        self.refresh_token: str = self.raw.get("refresh_token", "")
        self.refresh_expires: str = self.raw.get("refresh_expires", "")
        self.refresh_expires_at: str = self.raw.get("refresh_expires_at", "")
        self.account_id: str = self.raw.get("account_id", "")
        self.client_id: str = self.raw.get("client_id", "")
        self.internal_client: bool = self.raw.get("internal_client", False)
        self.client_service: str = self.raw.get("client_service", "")
        self.display_name: str = self.raw.get("displayName", "")
        self.app: str = self.raw.get("app", "")
        self.in_app_id: str = self.raw.get("in_app_id", "")
        self.user_agent: str = f"DeviceAuthGenerator/{platform.system()}/{platform.version()}"

    async def start(self) -> None:
        """Инициализация сессии"""
        self.access_token = await self.get_access_token()

    async def get_access_token(self) -> str:
        """Получение токена доступа"""
        async with self.http.post(
            url="https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"basic {SWITCH_TOKEN}",
            },
            data={"grant_type": "client_credentials"},
        ) as response:
            response.raise_for_status()
            data = await response.json()
            self._update_fields(data)
            return self.access_token

    async def create_device_code(self) -> tuple[str, str]:
        """Создание кода устройства"""
        async with self.http.post(
            url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/deviceAuthorization",
            headers={
                "Authorization": f"bearer {self.access_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return (
                data["verification_uri_complete"],
                data["device_code"],
            )

    async def create_exchange_code(self) -> str:
        """Создание кода обмена"""
        async with self.http.get(
            url="https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/exchange",
            headers={"Authorization": f"bearer {self.access_token}"},
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return data["code"]

    def _update_fields(self, data: Dict[str, Any]) -> None:
        """Обновление полей класса из полученных данных"""
        self.raw.update(data)
        self.__dict__.update(
            {k: data.get(k, v) for k, v in self.__dict__.items() if k in data}
        )

    async def close(self) -> None:
        """Закрытие сессии"""
        await self.http.close()

    def __repr__(self) -> str:
        """Представление объекта для отладки"""
        fields = "\n".join(f"{k}: {v}" for k, v in self.__dict__.items() if not k.startswith("_"))
        return f"EpicApi:\n{fields}"


async def get_profile_stats(session: aiohttp.ClientSession, user: EpicApi) -> dict:
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
                days_since_last_played = (datetime.now(UTC) - last_played_date).days
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
