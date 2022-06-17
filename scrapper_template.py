"""
Basic template for scrapping

Resources:
    Proxies:
        - https://free-proxy-list.net/
    User-Agents:
        - https://developers.whatismybrowser.com/useragents/explore/
    Test rotation:
        - http://httpbin.org/
        - https://ipinfo.io/ip
"""

import asyncio
import logging
import random

import aiohttp
from bs4 import BeautifulSoup


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)


PROXY_LIST_URL = "https://free-proxy-list.net/"
PROXY_TEST_URL = "http://httpbin.org/ip"


async def fetch_and_process(url: str, session: aiohttp.ClientSession, proxy: str):
    async with session.get(url, proxy=proxy) as response:
        print(await response.text())


class FreeProxyAbuser:
    _proxies_to_fetch_multiplier = 3
    _proxy_test_timeout = 5

    def __init__(
        self,
        session: aiohttp.ClientSession,
        proxies_needed: int
    ):
        self.session = session
        self.proxies_needed = proxies_needed
        self.proxies_to_fetch = proxies_needed * self._proxies_to_fetch_multiplier

        self.proxy_set = set()

        sem_value = proxies_needed if proxies_needed <= 5 else 5
        self.sem = asyncio.Semaphore(sem_value)

    def get_random_proxy(self) -> str:
        if not self.proxy_set:
            raise Exception("No proxies available")
        return f"http://{random.choice(list(self.proxy_set))}"

    async def init_working_proxies(self):
        untested_proxy_list = await self.fetch_proxies()

        tasks = [self.add_proxy(proxy) for proxy in untested_proxy_list]

        await asyncio.gather(*tasks)

    async def fetch_proxies(self) -> list[str]:
        async with self.session.get(PROXY_LIST_URL) as response:
            soup = BeautifulSoup(await response.text(), "html.parser")

            table_rows = soup.find("table").find_all("tr")

            return [
                f"http://{row.contents[0].text}:{row.contents[1].text}"
                for row in table_rows[1:self.proxies_to_fetch+1]
            ]

    async def add_proxy(self, proxy: str):
        async with self.sem:
            if len(self.proxy_set) >= self.proxies_needed:
                return

            try:
                async with self.session.get(
                    PROXY_TEST_URL,
                    proxy=proxy,
                    timeout=self._proxy_test_timeout,
                    raise_for_status=True
                ) as response:
                    response_json = await response.json()
                    logging.info(f"`{response_json['origin']}` proxy works")
            except aiohttp.ClientError:
                logging.info(f"`{proxy}` proxy is broken")
            except asyncio.exceptions.TimeoutError:
                logging.info(f"`{proxy}` proxy is slow/overloaded")
            else:
                if len(self.proxy_set) < self.proxies_needed:
                    self.proxy_set.add(proxy)


async def main():
    async with aiohttp.ClientSession() as session:
        abuser = FreeProxyAbuser(session, proxies_needed=5)
        await abuser.init_working_proxies()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
