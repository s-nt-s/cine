import functools
import os
import time
import logging
import hashlib
from datetime import datetime
import re
from core.req import R

from .filemanager import FM

logger = logging.getLogger(__name__)


def myhash(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def to_timestamp(s):
    if not isinstance(s, str):
        return None
    return datetime(*map(int, re.findall(r"\d+", s))).timestamp()


class Cache:
    def __init__(self, file: str, *args, kwself=None, reload: bool = False, skip: bool = False, maxOld=1, loglevel=None, **kwargs):
        self.file = file
        self.func = None
        self.reload = reload
        self.maxOld = maxOld
        self.loglevel = loglevel
        self.kwself = kwself
        if maxOld is not None:
            self.maxOld = time.time() - (maxOld * 86400)
        self._kwargs = kwargs
        self.skip = skip

    def parse_file_name(self, *args, slf=None, **kwargs):
        if args or kwargs:
            return self.file.format(*args, **kwargs)
        return self.file

    def read(self, file, *args, **kwargs):
        return FM.load(file, **self._kwargs)

    def save(self, file, data, *args, **kwargs):
        if file is None:
            return
        FM.dump(file, data, **self._kwargs)

    def tooOld(self, fl: str):
        if fl is None:
            return True
        if not os.path.isfile(fl):
            return True
        if self.reload:
            return True
        if self.maxOld is None:
            return False
        if os.stat(fl).st_mtime < self.maxOld:
            return True
        return False

    def log(self, txt):
        if self.loglevel is not None:
            logger.log(self.loglevel, txt)

    def callCache(self, slf, *args, **kwargs):
        flkwargs = dict(kwargs)
        if isinstance(self.kwself, str):
            flkwargs[self.kwself] = slf
        fl = self.parse_file_name(*args, **flkwargs)
        if not self.tooOld(fl):
            self.log(f"Cache.read({fl})")
            data = self.read(fl, *args, **kwargs)
            if data is not None:
                return data
        data = self.func(slf, *args, **kwargs)
        if data is not None:
            self.log(f"Cache.save({fl})")
            self.save(fl, data, *args, **kwargs)
        return data

    def __call__(self, func):
        if self.skip:
            return func

        def callCache(*args, **kwargs):
            return self.callCache(*args, **kwargs)
        functools.update_wrapper(callCache, func)
        self.func = func
        setattr(callCache, "__cache_obj__", self)
        return callCache


class StaticCache(Cache):
    def callCache(self, *args, **kwargs):
        flkwargs = dict(kwargs)
        fl = self.parse_file_name(*args, **flkwargs)
        if not self.tooOld(fl):
            self.log(f"Cache.read({fl})")
            data = self.read(fl, *args, **kwargs)
            if data is not None:
                return data
        data = self.func(*args, **kwargs)
        if data is not None:
            self.log(f"Cache.save({fl})")
            self.save(fl, data, *args, **kwargs)
        return data

    def parse_file_name(self, *args, **kwargs):
        if args or kwargs:
            return self.file.format(*args, **kwargs)
        return self.file


class TupleCache(Cache):
    def __init__(self, *args, builder=None, **kwargs):
        if not callable(builder):
            raise ValueError('builder is None')
        self.builder = builder
        super().__init__(*args, **kwargs)

    def read(self, file, *args, **kwargs):
        data = super().read(file, *args, **kwargs)
        if isinstance(data, dict):
            return self.builder(data)
        return tuple((self.builder(d) for d in data))


class HashCache(Cache):
    def parse_file_name(self, *args, slf=None, **kwargs):
        args = tuple(myhash(a) for a in args)
        kwargs = {k: myhash(v) for k, v in kwargs.items()}
        if args or kwargs:
            return self.file.format(*args, **kwargs)
        return self.file


class DictCache(Cache):
    def __init__(self, *args, mirror: tuple[str, ...], **kwargs):
        super().__init__(*args, **kwargs)
        self.__mirror = tuple()
        if isinstance(mirror, str):
            self.__mirror = tuple(mirror.strip().split())
        elif isinstance(mirror, tuple):
            self.__mirror = mirror

    def __find_in_mirror(self, name: str) -> tuple[str, dict] | tuple[None, None]:
        u, d = None, {}
        for m in self.__mirror:
            url = m + name
            data = R.safe_get_json(url)
            if isinstance(data, dict):
                new_time = to_timestamp(data.get('__time__')) or -1
                old_time = d.get('__time__')
                if old_time is None or (new_time > old_time):
                    u, d = url, data
        if u is not None:
            return u, d
        return None, None

    def tooOld(self, fl: str):
        if fl is None:
            return True
        path = FM.resolve_path(fl)
        if not path.is_file():
            url, data = self.__find_in_mirror(path.name)
            if isinstance(data, dict):
                ts_time = to_timestamp(data.get('__time__'))
                logger.info(f"{url} (__time__={ts_time}) -> {fl}")
                self.save(fl, data)
                if ts_time is not None:
                    os.utime(path, (ts_time, ts_time))
        if not path.is_file():
            return True
        if self.reload:
            return True
        if self.maxOld is None:
            return False
        if os.stat(fl).st_mtime < self.maxOld:
            return True
        return False

    def save(self, file, data, *args, **kwargs):
        if isinstance(data, dict):
            data['__time__'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        return super().save(file, data, *args, **kwargs)
