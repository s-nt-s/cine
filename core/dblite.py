
from sqlite3 import OperationalError, connect, Cursor
from atexit import register
import logging
from functools import cache
from core.film import IMDb

logger = logging.getLogger(__name__)


def dict_factory(cursor: Cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def gW(tp: tuple):
    if len(tp) == 0:
        return None
    if len(tp) == 1:
        return "= ?"
    prm = ", ".join(['?'] * len(tp))
    return f"in ({prm})"


def escape_fts5(text: str) -> str:
    text = text.replace('"', '""')
    return f'"{text}"'


class DBlite:
    def __init__(self, file: str):
        self.__file = file
        self.__con = None
        register(self.close)

    @property
    def file(self):
        return self.__file

    @property
    def con(self):
        if self.__con is None:
            logger.info(f"Connecting to {self.__file}")
            self.__con = connect(
                f"file:{self.__file}?mode=ro&immutable=1",
                uri=True
            )
        return self.__con

    def select(self, sql: str, *args, row_factory=None, **kwargs):
        self.con.row_factory = row_factory
        cursor = self.con.cursor()
        try:
            if len(args):
                cursor.execute(sql, args)
            else:
                cursor.execute(sql)
        except OperationalError:
            logger.critical(sql)
            raise
        for r in cursor:
            yield r
        cursor.close()
        self.con.row_factory = None

    def one(self, sql: str, *args, **kwargs):
        for r in self.select(sql, *args, **kwargs):
            return r[0] if len(r) == 1 else r

    def to_tuple(self, *args, **kwargs):
        arr = []
        for i in self.select(*args, **kwargs):
            if isinstance(i, (tuple, list)) and len(i) == 1:
                i = i[0]
            arr.append(i)
        return tuple(arr)

    def get_dict(self, *args, **kwargs):
        obj = dict()
        for k, v in self.select(*args, **kwargs):
            obj[k] = v
        return obj

    def close(self):
        if self.__con is None:
            return
        logger.info(f"Closing {self.__file}")
        self.__con.close()
        self.__con = None

    @cache
    def __search_person(self, name: str, category: str = None) -> tuple[str, ...]:
        if not isinstance(name, str):
            return tuple()
        name = name.strip().lower()
        if len(name) == 0:
            return tuple()
        sql = "select id from {t} where {w}"
        if category:
            sql = sql + f" and id in (select person from worker where category='{category}')"
        for t, w in (
            ('PERSON', "lower(name) = ? COLLATE NOCASE"),
            ('PERSON_FTS', "name MATCH ?"),
            #('', "lower(name) like ('%' || ? || '%')")
        ):
            n = escape_fts5(name) if t.endswith("_FTS") else name
            ids = self.to_tuple(sql.format(t=t, w=w), n)
            if len(ids):
                return ids
        return tuple()

    def search_person(self, *names: str, category: str = None):
        p: set[str] = set()
        for n in names:
            p = p.union(self.__search_person(n, category=category))
        return tuple(sorted(p))

    @cache
    def get_imdb_info(self, id: str):
        if not isinstance(id, str):
            return None
        row = self.one("""
            select
                type,
                year,
                duration,
                rating,
                votes,
                filmaffinity,
                wikipedia,
                countries
            from
                movie m left join
                extra e on m.id=e.movie
            where id = ?
        """, id)
        if row is None:
            return None
        return IMDb(
            id=id,
            rate=row[3],
            votes=row[4]
        )

    def search_imdb_id(self, title: str, year: int, director: tuple[str, ...] = None) -> int | None:
        if not isinstance(year, int):
            return None
        years = [year]
        for i in range(1, 2):
            years.append(year-i)
            years.append(year+i)
        for y in years:
            id = self.__search_imdb(title, y, director)
            if id is not None:
                return id
        return None

    @cache
    def __search_title(self, title: str) -> tuple[tuple[str, ...], ...]:
        if not isinstance(title, str):
            return tuple()
        title = title.strip().lower()
        if len(title) == 0:
            return tuple()
        arr = []
        for t, w in (
            ('TITLE', "title = ? COLLATE NOCASE"),
            ('TITLE_FTS', "title MATCH ?"),
            #"lower(title) like ('%' || ? || '%')"
        ):
            tt = escape_fts5(title) if t.endswith("_FTS") else title
            ids = self.to_tuple(f"select movie from {t} where {w}", tt)
            if len(ids):
                arr.append(ids)
        return tuple(arr)

    def __search_imdb(self, title: str, year: int, director: tuple[str, ...] = None) -> int | None:
        id_title = tuple()
        titles = list(self.__search_title(title))
        while len(id_title) == 0 and titles:
            tt = titles.pop(0)
            id_title = self.to_tuple(f"""
                select id from movie
                where
                    year = ? and
                    id {gW(tt)}
            """, year, *tt)
        if len(id_title) == 1:
            return id_title[0]
        directos = self.search_person(*(director or tuple()), category='director')
        if len(directos) == 0:
            return None
        id_dir = self.to_tuple(f"""
            select id from movie
            where
                year = ? and
                id in (
                      select movie
                      from
                        worker
                      where
                        category = 'director' and
                        person {gW(directos)}
                )
        """, year, *directos)
        if len(id_dir) == 1:
            return id_dir[0]
        ok = set(id_dir).intersection(id_title)
        if len(ok) == 1:
            return ok.pop()


DB = DBlite("imdb.sqlite")


if __name__ == "__main__":
    pass
