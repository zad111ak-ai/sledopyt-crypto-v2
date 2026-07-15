"""
Единая aiohttp сессия на всё приложение.
Не создавай новую сессию на каждый запрос — это утечка.
"""
import asyncio
import aiohttp
import os

PROXY = os.environ.get("HTTP_PROXY", "http://127.0.0.1:1082")


class HTTPClient:
    _session: aiohttp.ClientSession | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            async with cls._lock:
                if cls._session is None or cls._session.closed:
                    timeout = aiohttp.ClientTimeout(total=15, connect=5)
                    connector = aiohttp.TCPConnector(
                        limit=100,
                        limit_per_host=20,
                        ttl_dns_cache=300,
                        use_dns_cache=True,
                    )
                    cls._session = aiohttp.ClientSession(
                        timeout=timeout,
                        connector=connector,
                    )
        return cls._session

    @classmethod
    async def close(cls):
        if cls._session and not cls._session.closed:
            await cls._session.close()
            await asyncio.sleep(0.25)
            cls._session = None

    @classmethod
    async def get(cls, url: str, **kwargs):
        session = await cls.get_session()
        # Прокси через proxy URL
        if PROXY and "proxy" not in kwargs:
            kwargs["proxy"] = PROXY
        return await session.get(url, **kwargs)

    @classmethod
    async def post(cls, url: str, **kwargs):
        session = await cls.get_session()
        if PROXY and "proxy" not in kwargs:
            kwargs["proxy"] = PROXY
        return await session.post(url, **kwargs)
