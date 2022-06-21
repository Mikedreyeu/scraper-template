import asyncio
import json
import os
from datetime import datetime, timedelta
from itertools import chain
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

USER_AGENTS_URL = "https://www.whatismybrowser.com/guides/the-latest-user-agent/"
USER_AGENTS_FILE = "user_agents.json"

browsers = [
    "chrome",
    "firefox",
    "safari",
    "edge",
    "opera",
    "vivaldi",
    "yandex-browser"
]

to_ignore_keywords = [
    "Mobile",
    "Xbox"
]


async def fetch_user_agents(browser: str, session: aiohttp.ClientSession,):
    async with session.get(
        f"{USER_AGENTS_URL}{browser}",
        raise_for_status=True
    ) as response:
        soup = BeautifulSoup(await response.text(), "html.parser")

        code_text_boxes = soup.find_all("span", {"class": "code"})

        return [text_box.text for text_box in code_text_boxes]


def is_file_old(filename: str):
    return datetime.now() > datetime.fromtimestamp(os.path.getmtime(filename)) + timedelta(days=10)


async def get_user_agents():
    if (
        not Path(USER_AGENTS_FILE).exists()
        or Path(USER_AGENTS_FILE).exists() and is_file_old(USER_AGENTS_FILE)
    ):
        async with aiohttp.ClientSession() as session:
            tasks = [
                fetch_user_agents(browser, session) for browser in browsers
            ]
            lists_of_agent_lists = await asyncio.gather(*tasks)

            user_agent_list = [
                record
                for record in chain(*lists_of_agent_lists)
                if all([keyword not in record for keyword in to_ignore_keywords])
            ]

            with open(USER_AGENTS_FILE, "w") as file:
                json.dump(user_agent_list, file, indent=4)
    else:
        with open(USER_AGENTS_FILE) as file:
            user_agent_list = json.load(file)

    return user_agent_list
