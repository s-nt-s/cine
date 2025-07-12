#!/usr/bin/env python3

import yt_dlp
from yt_dlp.utils import YoutubeDLError
from functools import cache
import logging
import requests
from os import environ
import re
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


@cache
def get_m3u8(url):
    with yt_dlp.YoutubeDL(dict(
            quiet=True,
            skip_download=True,
            force_generic_extractor=False,
            noplaylist=True,
            extract_flat=False,
            format='best',
    )) as ydl:
        info = ydl.extract_info(url, download=False)
        for f in info.get("formats", []):
            url = f.get("url")
            if not url:
                continue
            ext = f.get("ext")
            if ext == "m3u8":
                return f["url"]
            if ext == "mp4" and "m3u8" in url:
                return f["url"]


def safe_get_m3u8(*urls):
    r = dict()
    tries: dict[str, int] = dict()
    urls = list(urls)
    while urls:
        url = urls.pop()
        try:
            m3u8 = get_m3u8(url)
            if m3u8 is None:
                logger.warning(f"[¿?] {url}")
                continue
            r[url] = m3u8
            logger.info(f"[OK] {url}")
        except YoutubeDLError as e:
            tries[url] = tries.get(url, 0) + 1
            if tries[url] < 2:
                urls.append(url)
                continue
            logger.warning(f"[KO] {url} {e}")
    return r


if __name__ == "__main__":
    from core.db import Database
    r = requests.get(environ['PAGE_URL'])
    urls = re.findall(re.escape('https://www.rtve.es/play/')+r'[^"]+?/\d+/', r.text)
    with Database() as db:
        done = db.to_tuple("SELECT url FROM M3U8 WHERE updated > NOW() - INTERVAL '2 days'")
        urls = sorted(set(urls).difference(done))
        for k, v in safe_get_m3u8(*urls).items():
            db.insert("M3U8", url=k, m3u8=v, tail='ON CONFLICT (url) DO UPDATE SET m3u8 = EXCLUDED.m3u8, updated=now()')
