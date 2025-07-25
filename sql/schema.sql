CREATE TABLE M3U8 (
    url TEXT PRIMARY KEY,
    m3u8 TEXT NOT NULL,
    updated TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE OMBDAPI (
    id TEXT PRIMARY KEY,
    json JSONB NOT NULL,
    updated TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IMDB_WIKI (
    id TEXT PRIMARY KEY,
    filmaffinity INT,
    wiki TEXT,
    countries TEXT[],
    updated TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE URL_TXT (
    url TEXT PRIMARY KEY,
    txt TEXT NOT NULL,
    updated TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE KEY_INT (
    name TEXT NOT NULL,
    id TEXT NOT NULL,
    val INTEGER NOT NULL,
    updated TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (name, id)
);

