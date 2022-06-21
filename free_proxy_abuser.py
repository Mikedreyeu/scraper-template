import asyncio
import logging
import random
import re
from functools import cache

import aiohttp
from bs4 import BeautifulSoup

PROXY_LIST_URL = "https://free-proxy-list.net/"
HTTPS_PROXY_LIST_URL = "https://sslproxies.org/"
HTTPS_SPYS_PROXY_LIST_URL = "https://spys.one/en/https-ssl-proxy/"
PROXY_TEST_URL = "http://httpbin.org/ip"


@cache
def decipher_spys_vars(raw_vars: str, raw_formula: str) -> dict:
    """ Deciphers encoded vars of spys.one site needed to decode ports """
    # variable names are in this order, formula uses [a-zA-X] placeholders
    chars = [
        *(chr(num) for num in range(97, 123)),
        *(chr(num) for num in range(65, 89))
    ]
    variables = [var for var in raw_vars.split("^") if var]
    decipher_dict = {char: var for char, var in zip(chars, variables)}

    formula = re.sub(
        "|".join(decipher_dict.keys()),
        lambda match: decipher_dict[match.group()],
        raw_formula.strip(';')
    )

    # init variables to calc values
    exec(formula)

    # then grab them from locals()
    local_vars = locals()
    return {
        var.split("=")[0]: local_vars[var.split("=")[0]]
        for var in formula.split(";")
    }


def decode_spys_port(encoded_port: str, deciphered_vars: dict) -> str:
    partly_decoded_port = re.sub(
        "|".join(sorted(deciphered_vars.keys(), key=len, reverse=True)),
        lambda match: str(deciphered_vars[match.group()]),
        encoded_port
    )

    return "".join(
        [str(eval(number)) for number in partly_decoded_port.split("+")]
    )


def parse_and_decode_spys_proxies(html_data: str) -> list:
    soup = BeautifulSoup(html_data, "html.parser")
    # grab js that sets variables, decode it
    encoding_js = soup.find("script", {"type": "text/javascript"}).text

    result = re.findall("'(.*?)'", encoding_js)
    raw_vars, raw_formula = result[-2], result[-3]

    deciphered_vars = decipher_spys_vars(raw_vars, raw_formula)

    # grab ip with encoded port
    table_rows = soup.find_all("tr", {"class": ["spy1xx", "spy1x"]})[1:]

    proxy_list = []

    for row in table_rows:
        proxy_text = row.contents[0].contents[0].contents
        ip = proxy_text[0]
        encoded_port = str(proxy_text[1].contents[0])[44:-1]

        decoded_port = decode_spys_port(encoded_port, deciphered_vars)

        proxy_list.append(f"http://{ip}:{decoded_port}")

    return proxy_list


def parse_fpl_proxies(html_data: str) -> list:
    soup = BeautifulSoup(html_data, "html.parser")

    table_rows = soup.find("table").find_all("tr")

    return [
        f"http://{row.contents[0].text}:{row.contents[1].text}"
        for row in table_rows[1:]
    ]


class FreeProxyAbuser:
    _max_proxies = 30
    _proxy_test_timeout = 5

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_agent: str,
        proxies_needed: int
    ):
        if proxies_needed > self._max_proxies:
            raise Exception("Too many proxies")

        self.session = session
        self.user_agent = user_agent
        self.proxies_needed = proxies_needed

        self.proxy_set = set()

        sem_value = proxies_needed * 2 if proxies_needed < 3 else 6
        self.sem = asyncio.Semaphore(sem_value)

    def get_random_proxy(self) -> str:
        if not self.proxy_set:
            raise Exception("No proxies available")
        return random.choice(list(self.proxy_set))

    async def init_working_proxies(self, https_support: bool = True):
        untested_proxy_list = await self.fetch_proxies(https_support)

        tasks = [
            self.check_and_add_proxy(proxy) for proxy in untested_proxy_list
        ]

        await asyncio.gather(*tasks)
        logging.info(f"Managed to gather {len(self.proxy_set)} proxies")

    async def fetch_proxies(self, https_support: bool = True) -> list[str]:
        resulting_proxy_list = []
        if https_support:
            # fetch https proxies from two sources since they are less reliable
            # and less common
            async with self.session.get(
                HTTPS_SPYS_PROXY_LIST_URL,
                headers={"User-Agent": self.user_agent}
            ) as response:
                proxy_list = parse_and_decode_spys_proxies(await response.text())

                resulting_proxy_list = (
                    proxy_list[:5] + resulting_proxy_list + proxy_list[5:]
                )

            async with self.session.get(HTTPS_PROXY_LIST_URL) as response:
                parse_fpl_proxies(await response.text())

                resulting_proxy_list = (
                    proxy_list[:5] + resulting_proxy_list + proxy_list[5:]
                )
        else:
            async with self.session.get(PROXY_LIST_URL) as response:
                resulting_proxy_list = parse_fpl_proxies(await response.text())

        return resulting_proxy_list

    async def check_and_add_proxy(self, proxy: str):
        async with self.sem:
            if len(self.proxy_set) >= self.proxies_needed:
                return

            # give it 3 tries since they tend to be laggy
            for _ in range(3):
                try:
                    async with self.session.get(
                        PROXY_TEST_URL,
                        proxy=proxy,
                        timeout=self._proxy_test_timeout,
                        raise_for_status=True
                    ) as response:
                        await response.json()
                except aiohttp.ClientError:
                    resulting_info_msg = f"`{proxy}` proxy is broken"
                except asyncio.exceptions.TimeoutError:
                    resulting_info_msg = f"`{proxy}` proxy is slow/overloaded"
                else:
                    resulting_info_msg = f"`{proxy}` proxy works"
                    if len(self.proxy_set) < self.proxies_needed:
                        self.proxy_set.add(proxy)
                    break

            logging.info(resulting_info_msg)
