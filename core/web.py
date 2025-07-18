import os
import re
import time
from urllib.parse import parse_qsl, urljoin, urlsplit
from typing import List, Tuple, Dict
import json
from functools import cache

import requests
from bs4 import BeautifulSoup, Tag
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.chrome import ChromeType
from webdriver_manager.core.utils import read_version_from_cmd
from webdriver_manager.core.os_manager import PATTERN
from selenium import webdriver
from selenium.common.exceptions import (ElementNotInteractableException,
                                        ElementNotVisibleException,
                                        StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options as CMoptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.firefox.options import Options as FFoptions
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
import logging
from typing import Union
from requests import RequestException

logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")
re_emb = re.compile(r"^image/[^;]+;base64,.*", re.IGNORECASE)
is_s5h = os.environ.get('http_proxy', "").startswith("socks5h://")
if is_s5h:
    proxy_ip, proxy_port = os.environ['http_proxy'].split(
        "//", 1)[-1].split(":")
    proxy_port = int(proxy_port)

default_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Expires": "Thu, 01 Jan 1970 00:00:00 GMT",
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def find_by_text(soup: Tag, tag: str, text: str):
    re_text = r"\s+".join(map(re.escape, text.split()))
    return soup.find(tag, string=re.compile(r"\s*"+re_text+"\s*", flags=re.I))


def get_query(url):
    q = urlsplit(url)
    q = parse_qsl(q.query)
    q = dict(q)
    return q


def iterhref(soup: BeautifulSoup):
    """Recorre los atributos href o src de los tags"""
    n: Tag
    for n in soup.findAll(["img", "form", "a", "iframe", "frame", "link", "script", "input"]):
        attrs = ("href", ) if n.name in ("a", "link") else ("src", "data-src")
        if n.name == "form":
            attrs = ("action", )
        for attr in attrs:
            val = n.attrs.get(attr)
            if val is None or re_emb.search(val):
                continue
            if not (val.startswith("#") or val.startswith("javascript:")):
                yield n, attr, val


def buildSoup(root: str, source: str, parser="lxml"):
    soup = BeautifulSoup(source, parser)
    for n, attr, val in iterhref(soup):
        val = urljoin(root, val)
        n.attrs[attr] = val
    return soup


def get_text(node: Tag, default: str = None):
    if node is None:
        return default
    txt = None
    if node.name == "input":
        txt = node.attrs.get("value")
        if txt is None:
            txt = node.attrs.get("src")
    else:
        txt = node.get_text()
    if txt is None:
        return default
    txt = re_sp.sub(" ", txt).strip()
    if len(txt) == 0:
        return default
    return txt


def refind(tag: Tag, slc: str, rgx: str) -> Tuple[Tag]:
    arr: List[Tag] = []
    for n in tag.select(slc):
        txt = n.get_text().strip()
        if re.match(rgx, txt):
            arr.append(n)
    return tuple(arr)


class WebException(Exception):
    pass


class Web:
    def __init__(self, refer=None, verify=True):
        self.s = requests.Session()
        self.s.headers = default_headers
        self.response = None
        self.soup = None
        self.form = None
        self.refer = refer
        self.verify = verify

    def _get(self, url, allow_redirects=True, auth=None, **kwargs):
        if kwargs:
            return self.s.post(url, data=kwargs, allow_redirects=allow_redirects, verify=self.verify, auth=auth)
        return self.s.get(url, allow_redirects=allow_redirects, verify=self.verify, auth=auth)

    def get_soup(self, url, auth=None, parser="lxml", **kwargs):
        r = self._get(url, auth=auth, **kwargs)
        return buildSoup(url, r.content, parser=parser)

    def get(self, url, auth=None, parser="lxml", **kwargs):
        if self.refer:
            self.s.headers.update({'referer': self.refer})
        self.response = self._get(url, auth=auth, **kwargs)
        self.refer = self.response.url
        self.soup = buildSoup(url, self.response.content, parser=parser)
        return self.soup

    def prepare_submit(self, slc, silent_in_fail=False, **kwargs):
        data: Dict[str, Union[str, int, float, None]] = {}
        self.form = self.soup.select_one(slc)
        if silent_in_fail and self.form is None:
            return None, None
        for i in self.form.select("input[name]"):
            name = i.attrs["name"]
            data[name] = i.attrs.get("value")
        for i in self.form.select("select[name]"):
            name = i.attrs["name"]
            slc = i.select_one("option[selected]")
            slc = slc.attrs.get("value") if slc else None
            data[name] = slc
        data = {**data, **kwargs}
        action: str = self.form.attrs.get("action")
        action = action.rstrip() if action else None
        if action is None:
            action = self.response.url
        return action, data

    def submit(self, slc, silent_in_fail=False, **kwargs):
        action, data = self.prepare_submit(
            slc, silent_in_fail=silent_in_fail, **kwargs)
        if silent_in_fail and not action:
            return None
        return self.get(action, **data)

    def val(self, slc):
        n = self.soup.select_one(slc)
        if n is None:
            return None
        v = n.attrs.get("value", n.get_text())
        v = v.strip()
        return v if v else None

    @property
    def url(self):
        if self.response is None:
            return None
        return self.response.url

    def json(self, url, **kwargs):
        r = self._get(url, **kwargs)
        return r.json()

    def resolve(self, url, **kwargs):
        if self.refer:
            self.s.headers.update({'referer': self.refer})
        r = self._get(url, allow_redirects=False, **kwargs)
        if r.status_code in (302, 301):
            return r.headers['location']

    def select_one(self, slc: str):
        n = self.soup.select_one(slc)
        if n is None:
            raise WebException(f"{slc} NOT FOUND in {self.url}")
        return n

    def select_one_attr(self, slc: str, attr: str):
        n = self.select_one(slc)
        if attr not in n.attrs:
            raise WebException(f"{slc} has not {attr} in {self.url}")
        val = n.attrs[attr]
        if not isinstance(val, str):
            raise WebException(f"{slc} {attr}!=str in {self.url}")
        val = val.strip()
        if len(val) == 0:
            raise WebException(f"{slc} {attr} IS EMPTY in {self.url}")
        return val

    def select_one_txt(self, slc: str):
        n = self.select_one(slc)
        txt = get_text(n)
        if txt is None:
            raise WebException(f"{slc} IS EMPTY in {self.url}")
        return txt

    def select_one_json(self, slc: str) -> Union[Dict, List]:
        txt = self.select_one_txt(slc)
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            raise WebException(f"{slc} no json in {self.url}")

    @cache
    def __cached_get(self, url: str):
        r = self._get(url)
        return r.content

    def get_cached_soup(self, url: str, parser="lxml"):
        content = self.__cached_get(url)
        soup = buildSoup(url, content, parser=parser)
        return soup

    @cache
    def expand(self, url: str):
        try:
            r = self.s.head(url, allow_redirects=True, timeout=5)
            return r.url
        except RequestException as e:
            logger.warning(f"Error al expandir {url} : {e}")
            return url


class MyTag:
    def __init__(self, url: str, node: Tag):
        self.__url = url
        self.__node = node

    def select_one(self, slc: str, warning: bool = False):
        n = self.__node.select_one(slc)
        if n is None:
            ex = WebException(f"{slc} NOT FOUND in {self.__url}")
            if warning:
                logger.warning(str(ex))
                return None
            raise ex
        return n

    def select_one_txt(self, slc: str, warning: bool = False):
        n = self.select_one(slc, warning=warning)
        if n is None and warning:
            return None
        txt = get_text(n)
        if txt is None:
            ex = WebException(f"{slc} EMPTY in {self.__url}")
            if warning:
                logger.warning(str(ex))
                return None
            raise ex
        return txt

    def select_one_attr(self, slc: str, attr: str, warning: bool = False):
        n = self.select_one(slc, warning=warning)
        if n is None and warning:
            return None
        if attr not in n.attrs:
            ex = WebException(f"{slc} has not {attr} in {self.__url}")
            if warning:
                logger.warning(str(ex))
                return None
            raise ex
        txt = n.attrs[attr]
        if txt is None:
            ex = WebException(f"{slc}[{attr}] EMPTY in {self.__url}")
            if warning:
                logger.warning(str(ex))
                return None
            raise ex
        return txt

    def select_one_json(self, slc: str) -> Union[Dict, List]:
        txt = self.select_one_txt(slc)
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            raise WebException(f"{slc} no json in {self.__url}")

    def select(self, slc: str):
        nds = self.__node.select(slc)
        if len(nds) == 0:
            raise WebException(f"{slc} NOT FOUND in {self.__url}")
        return nds

    def select_txt(self, slc: str):
        arr: List[str] = []
        for txt in map(get_text, self.select(slc)):
            if txt:
                arr.append(txt)
        if len(arr) == 0:
            raise WebException(f"{slc} EMPTY in {self.__url}")
        return tuple(arr)

    @property
    def url(self):
        return self.__url

    @property
    def node(self):
        return self.__node

FF_DEFAULT_PROFILE = {
    "browser.tabs.drawInTitlebar": True,
    "browser.uidensity": 1,
    "dom.webdriver.enabled": False
}


class Driver:
    DRIVER_PATH = None

    @staticmethod
    def find_driver_path():
        if Driver.DRIVER_PATH is None:
            def get_version(path):
                if os.path.isfile(path):
                    return read_version_from_cmd(
                        path+" --version",
                        PATTERN[ChromeType.CHROMIUM]
                    )
            Driver.DRIVER_PATH = ChromeDriverManager(
                driver_version=get_version("/usr/bin/chromium"),
                chrome_type=ChromeType.CHROMIUM
            ).install()
        return Driver.DRIVER_PATH

    def __init__(self, browser=None, wait=60, useragent=None):
        # Driver.find_driver_path()
        self._driver: WebDriver = None
        self.visible = (os.environ.get("DRIVER_VISIBLE") == "1")
        self._wait = wait
        self.useragent = useragent
        self.browser = browser

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def _create_firefox(self):
        options = FFoptions()
        options.headless = not self.visible
        profile = webdriver.FirefoxProfile()
        if self.useragent:
            profile.set_preference(
                "general.useragent.override", self.useragent)
        for k, v in FF_DEFAULT_PROFILE.items():
            profile.set_preference(k, v)
            profile.DEFAULT_PREFERENCES['frozen'][k] = v
        profile.update_preferences()
        driver = webdriver.Firefox(
            options=options, firefox_profile=profile)
        driver.maximize_window()
        driver.implicitly_wait(5)
        return driver

    def _create_chrome(self):
        options = CMoptions()
        if not self.visible:
            options.add_argument('headless')
        if self.useragent:
            options.add_argument('user-agent=' + self.useragent)
        options.add_argument("start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("--lang=es-ES")
        options.add_experimental_option(
            'excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

        if is_s5h:
            prox = Proxy()
            prox.proxy_type = ProxyType.MANUAL
            prox.socks_proxy = "{}:{}".format(proxy_ip, proxy_port)
            prox.socksVersion = 5
            capabilities = webdriver.DesiredCapabilities.CHROME
            prox.add_to_capabilities(capabilities)
            driver = webdriver.Chrome(
                Driver.find_driver_path(),
                options=options,
                desired_capabilities=capabilities
            )
        else:
            driver = webdriver.Chrome(
                Driver.find_driver_path(),
                options=options
            )
        driver.maximize_window()
        driver.implicitly_wait(5)
        return driver

    def get_dirver(self):
        if self._driver is None:
            crt = getattr(self, "_create_" + str(self.browser), None)
            if crt is None:
                raise Exception("Not implemented yet: %s" % self.browser)
            self._driver = crt()
        return self._driver

    @property
    def driver(self):
        return self.get_dirver()

    def close(self, *windows):
        if self._driver:
            sz = len(self._driver.window_handles)
            if len(windows) in (0, sz):
                self._driver.quit()
                self._driver = None
                return
            for w in reversed(windows):
                self._driver.switch_to.window(w)
                self._driver.close()
            self._driver.switch_to.window(self._driver.window_handles[0])

    def close_others(self, current=None):
        if self._driver:
            if current is None:
                current = self._driver.current_window_handle
            elif isinstance(current, int):
                current = self._driver.window_handles[current]
            windows = [w for w in self._driver.window_handles if w != current]
            if windows:
                self.close(*windows)

    def switch(self, window):
        if isinstance(window, int):
            window = self._driver.window_handles[window]
        self._driver.switch_to.window(window)

    def reintentar(self, intentos, sleep=1):
        if intentos > 50:
            return False, sleep
        if intentos % 3 == 0:
            sleep = int(sleep / 3)
            self.close()
        else:
            sleep = sleep*2
        if intentos > 20:
            time.sleep(10)
        time.sleep(2 * (int(intentos/10)+1))
        return True, sleep

    def get(self, url: str):
        logger.debug(url)
        self.driver.get(url)

    def get_soup(self, root=None):
        if self._driver is None:
            return None
        if root is None:
            root = self._driver.current_url
        return buildSoup(root, self._driver.page_source)

    @property
    def current_url(self):
        if self._driver is None:
            return None
        return self._driver.current_url

    @property
    def source(self):
        if self._driver is None:
            return None
        return self._driver.page_source

    def wait(self, id: Union[int, float, str], seconds=None, presence=False, by=None) -> WebElement:
        if isinstance(id, (int, float)):
            time.sleep(id)
            return
        if seconds is None:
            seconds = self._wait
        if by is None:
            by = By.ID
            if id.startswith("//"):
                by = By.XPATH
            if id.startswith("."):
                by = By.CSS_SELECTOR
        wait = WebDriverWait(self._driver, seconds)
        if presence:
            wait.until(ec.presence_of_element_located((by, id)))
        else:
            wait.until(ec.visibility_of_element_located((by, id)))
        if by == By.CLASS_NAME:
            return self._driver.find_element_by_class_name(id)
        if by == By.CSS_SELECTOR:
            return self._driver.find_element_by_css_selector(id)
        if by == By.XPATH:
            return self._driver.find_element_by_xpath(id)
        return self._driver.find_element_by_id(id)

    def waitjs(self, js: str, val=True, seconds=None):
        if seconds is None:
            seconds = self._wait
        js = js.strip()

        if not js.startswith("return "):
            js = 'return '+js

        def do_js(w: WebDriver):
            rt = w.execute_script(js)
            if callable(val):
                return val(rt)
            return rt == val

        wait = WebDriverWait(self._driver, seconds)
        wait.until(do_js)

    def safe_wait(self, *ids, **kvarg):
        for id in ids:
            if isinstance(id, WebElement):
                return id
            try:
                return self.wait(id, **kvarg)
            except TimeoutException:
                pass
        return None

    def val(self, n, val=None, **kwargs):
        if n is None or self._driver is None:
            return None
        if isinstance(n, str):
            n = self.wait(n, **kwargs)
        if val is not None:
            n.clear()
            n.send_keys(val)
        return n.text

    def click(self, n, **kvarg):
        if n is None or self._driver is None:
            return None
        if isinstance(n, str):
            n = self.wait(n, **kvarg)
        if n.is_displayed():
            ActionChains(self._driver).move_to_element(n).click(n).perform()
            # n.click()
        else:
            n.send_keys(Keys.RETURN)
        return True

    def safe_click(self, *ids, after=None, force_return=False, **kvarg):
        if len(ids) == 1 and not isinstance(ids[0], str):
            n = ids[0]
        else:
            n = self.safe_wait(*ids, **kvarg)
        if n is None:
            return -1
        try:
            if n.is_displayed() and not force_return:
                n.click()
            else:
                n.send_keys(Keys.RETURN)
        except (
                ElementNotInteractableException,
                StaleElementReferenceException,
                ElementNotVisibleException,
                WebDriverException
        ):
            return 0
        if after is not None:
            time.sleep(after)
        return 1

    def execute_script(self, *args, **kwargs):
        return self.driver.execute_script(*args, **kwargs)

    def pass_cookies(self, session: requests.Session = None):
        if self._driver is None:
            return session
        if session is None:
            session = requests.Session()
        for cookie in self._driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        return session

    def wait_ready(self):
        self.waitjs('window.document.readyState === "complete"')

    def to_web(self):
        w = Web()
        self.pass_cookies(w.s)
        return w

    def run_script(self, file: str):
        with open(file, "r") as f:
            js = f.read()
        return self.execute_script(js)


WEB = Web()