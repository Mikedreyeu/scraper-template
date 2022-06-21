"""
Basic template for scraping

Resources:
    Proxies:
        - https://free-proxy-list.net/
        - https://spys.one/en/https-ssl-proxy/ (decoding needed/ headless browser)
    User-Agents:
        - https://www.whatismybrowser.com/guides/the-latest-user-agent/
    Test rotation:
        - http://httpbin.org/
"""

import asyncio
import csv
import logging
import random
from functools import wraps
from itertools import chain

import aiohttp
from bs4 import BeautifulSoup

from free_proxy_abuser import FreeProxyAbuser
from request_headers_mocking import get_user_agents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(module)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

SEM_VAL = 5
PROXY_COUNT = 10
REQUEST_TIMEOUT = 15

request_sem = asyncio.Semaphore(SEM_VAL)


def retry(num=1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempts = 0
            while True:
                try:
                    result = await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.exceptions.TimeoutError):
                    attempts += 1
                    if attempts <= num:
                        logging.info(
                            f"Failed to fetch {kwargs.get('url') or args[0]}, "
                            f"retrying({attempts})..."
                        )
                        continue
                    else:
                        raise
                return result
        return wrapper
    return decorator


@retry(5)
async def fetch_and_process(
    url: str,
    session: aiohttp.ClientSession,
    abuser: FreeProxyAbuser = None,
    user_agent: str = None,
) -> list[dict]:
    # passing the whole abuser to avoid making proper retry/task functionality
    proxy = abuser.get_random_proxy() if abuser else None
    headers = {"User-Agent": user_agent} if user_agent else {}

    async with request_sem:
        logging.info(f"Fetching {url}")
        async with session.get(
            url,
            proxy=proxy,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            raise_for_status=True
        ) as response:

            records = parse_response(await response.text())

            logging.info(f"`{url}` fetched and processed successfully")
            return records


def parse_response(html_data: str) -> list:
    soup = BeautifulSoup(html_data, "html.parser")

    records = []

    ...  # TODO do whatever

    return records


async def main():
    user_agent_list = await get_user_agents()

    async with aiohttp.ClientSession() as session:
        abuser = FreeProxyAbuser(
            session,
            user_agent=random.choice(user_agent_list),
            proxies_needed=PROXY_COUNT
        )
        await abuser.init_working_proxies()

        tasks = [
            fetch_and_process(
                f"url{num}",  # TODO url pattern
                session,
                abuser,
                random.choice(user_agent_list)
            )
            for num in range(...)  # TODO value range
        ]
        results = await asyncio.gather(*tasks)

        with open("data.csv", "w", newline="", encoding="UTF-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=[...])  # TODO fieldnames
            writer.writeheader()
            for row in chain(*results):
                writer.writerow(row)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
