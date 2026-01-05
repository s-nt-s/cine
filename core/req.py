import requests
from requests.exceptions import RequestException, Timeout, HTTPError
from functools import cache
import logging
from time import sleep
from json.decoder import JSONDecodeError

logger = logging.getLogger(__name__)


def _get_http_code(x):
    if isinstance(x, HTTPError):
        x = x.response
    if isinstance(x, requests.Response):
        return x.status_code


class Req:
    def __init__(self):
        self.__S = requests.Session()

    def __get_response(self, url: str, headers: frozenset = None, data: bytes = None):
        hdrs = dict(headers or frozenset())
        if data:
            r = self.__S.post(url, headers=hdrs, data=data, timeout=15)
        else:
            r = self.__S.get(url, headers=hdrs, timeout=15)
        r.raise_for_status()
        return r

    @cache
    def __get_body(self, url: str, headers: frozenset = None, data: bytes = None) -> str:
        r = self.__get_response(url, headers=headers, data=data)
        body = r.text.strip()
        return body

    @cache
    def __get_json(self, url: str, headers: frozenset = None, data: bytes = None) -> str:
        r = self.__get_response(url, headers=headers, data=data)
        js = r.json()
        return js

    def get_json(
        self,
        url: str,
        headers: dict = None,
        data: bytes = None,
        wait_if_status: dict[int, int] = None
    ) -> list | dict:
        frz = frozenset(headers.items()) if headers else None
        try:
            js = self.__get_json(url, headers=frz, data=data)
            return js
        except HTTPError as e:
            wait = (wait_if_status or {}).get(_get_http_code(e), 0)
            if wait <= 0:
                raise
        sleep(wait)
        return self.get_json(url, headers, data, wait_if_status=tuple())

    def safe_get_json(self, url, *args, **kwargs):
        try:
            return self.get_json(url, *args, **kwargs)
        except (HTTPError, RequestException, UnicodeDecodeError, Timeout, JSONDecodeError) as e:
            if _get_http_code(e) != 404:
                logger.warning(f"{url} {str(e)}")
            return None

    @cache
    def safe_get_list_dict(self, url: str) -> list[dict]:
        js = self.safe_get_json(url)
        if not isinstance(js, list):
            logger.critical(url+" no es una lista")
            return []
        for i in js:
            if not isinstance(i, dict):
                logger.critical(url+" no es una lista de diccionarios")
                return []
        return js

    @cache
    def safe_get_dict(self, url: str) -> dict:
        js = self.safe_get_json(url)
        if not isinstance(js, dict):
            logger.critical(url+" no es un diccionario")
            return {}
        return js


R = Req()
