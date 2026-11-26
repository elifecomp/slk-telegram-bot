import aiohttp
from config import PANEL_URL, PANEL_TOKEN


class Panel3XUIClient:
    def __init__(self, base_url: str = PANEL_URL, api_token: str = PANEL_TOKEN, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def post_api(self, endpoint: str, payload: dict | None = None) -> dict:
        url = f"{self.base_url}/panel/api{endpoint}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, headers=self._headers(), json=payload or {}) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    async def try_post_api(self, endpoint: str, payload: dict | None = None) -> tuple[int, dict | None]:
        url = f"{self.base_url}/panel/api{endpoint}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, headers=self._headers(), json=payload or {}) as resp:
                if resp.status == 404:
                    return 404, None
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                return resp.status, data

    async def get_api(self, endpoint: str) -> dict:
        url = f"{self.base_url}/panel/api{endpoint}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url, headers=self._headers()) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    async def try_get_api(self, endpoint: str) -> tuple[int, dict | None]:
        url = f"{self.base_url}/panel/api{endpoint}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url, headers=self._headers()) as resp:
                if resp.status == 404:
                    return 404, None
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                return resp.status, data
