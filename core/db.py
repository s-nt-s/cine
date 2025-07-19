import psycopg2
from psycopg2.extensions import connection as PGConnection
from typing import Optional, Any, Tuple, Union
from functools import cache
from os import environ
from datetime import datetime, timezone
import logging
from functools import update_wrapper
from psycopg2.extras import Json as DBJson
from atexit import register

logger = logging.getLogger()


class EmptyInsertException(psycopg2.OperationalError):
    pass


class Database:
    def __init__(self) -> None:
        self.__con: Optional[PGConnection] = None
        self.__atexit_registered = False

    @property
    def con(self) -> PGConnection:
        if self.__con is None or self.__con.closed:
            logger.info("Creating connection to database")
            self.__con = psycopg2.connect(
                host=environ["DB_HOST"],
                port=int(environ["DB_PORT"]),
                dbname=environ["DB_NAME"],
                user=environ["DB_USER"],
                password=environ["DB_PASSWORD"]
            )
            if not self.__atexit_registered:
                logger.info("Register database connection in atexit")
                register(self.close)
                self.__atexit_registered = True
        return self.__con

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.__con:
            if not self.__con.closed:
                logger.info("Closing connection to database")
                self.__con.close()
            self.__con = None

    @cache
    def get_cols(self, table: str) -> Tuple[str, ...]:
        return self.to_tuple('''
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        ''', table.lower())

    def to_tuple(self, query: str, *args):
        return tuple(self.iter(query, *args))

    def iter(self, query: str, *args):
        with self.con.cursor() as cur:
            cur.execute(query, args)
            for i in cur:
                if len(i) == 1:
                    yield i[0]
                else:
                    yield i

    def one(self, query: str, *args) -> Union[None, Any, Tuple[Any, ...]]:
        with self.con.cursor() as cur:
            cur.execute(query, args)
            r = cur.fetchone()
            if r is None or len(r) == 0:
                return None
            if len(r) == 1:
                return r[0]
            return r

    def insert(
        self,
        table: str,
        tail: str = None,
        **kwargs
    ):
        cols = self.get_cols(table)
        keys = []
        vals = []
        for k, v in kwargs.items():
            if k not in cols:
                continue
            if v is None or (isinstance(v, str) and len(v) == 0):
                continue
            keys.append(k)
            vals.append(v)
        if len(keys) == 0:
            raise EmptyInsertException(f"insert into {table} malformed: give {kwargs}")
        keys = ', '.join(keys)
        prm = ', '.join(['%s'] * len(vals))
        sql = f"insert into {table} ({keys}) values ({prm})"
        if tail:
            sql = sql+' '+tail
        self.execute(sql, vals)

    def update(
        self,
        table: str,
        id_field: str = 'id',
        **kwargs
    ):
        cols = self.get_cols(table)
        keys = []
        vals = []

        def set_default(field: str, val: Any):
            if field in cols and field not in kwargs:
                keys.append(f"{field} = %s")
                vals.append(val)

        id_value = None
        for k, v in kwargs.items():
            if k not in cols:
                continue
            if (isinstance(v, str) and len(v) == 0):
                v = None
            if k == id_field:
                id_value = v
                continue
            keys.append(f"{k} = %s")
            vals.append(v)
        set_default("updated", datetime.now(timezone.utc))
        if len(keys) == 0 or id_value is None:
            raise EmptyInsertException(f"update into {table} malformed: give {kwargs}")
        keys = ', '.join(keys)
        sql = f"update {table} set {keys} where {id_field} = %s"
        vals.append(id_value)
        self.execute(sql, vals)

    def execute(self, sql: str, vals: Tuple):
        try:
            with self.con.cursor() as cur:
                cur.execute(sql, vals)
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise


DB = Database()


class DBCache:
    def __init__(self, select: str, insert: str, kwself=None, loglevel=None):
        self.__select = select
        self.__insert = insert
        self.__func = None
        self.__loglevel = loglevel

    @property
    def insert(self):
        return self.__insert

    def read(self, *args):
        return DB.one(self.__select, *args)

    def save(self, data, *args):
        if isinstance(data, (list, dict)):
            data = DBJson(data)
        return DB.execute(self.__insert, args + (data, ))

    def log(self, txt):
        if self.__loglevel is not None:
            logger.log(self.__loglevel, txt)

    def callCache(self, slf, *args):
        data = self.read(*args)
        if data is not None:
            return data
        data = self.__func(slf, *args)
        if data is not None:
            self.save(data, *args)
        return data

    def __call__(self, func):
        def callCache(*args):
            return self.callCache(*args)

        update_wrapper(callCache, func)
        self.__func = func
        setattr(callCache, "__cache_obj__", self)
        return callCache
