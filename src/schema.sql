CREATE TABLE IF NOT EXISTS films (
    id          TEXT PRIMARY KEY,
    name        TEXT,
    year        TEXT,
    director    TEXT,
    tagline     TEXT,
    synopsis    TEXT,
    poster      TEXT,
    casts       TEXT,
    genres      TEXT,
    themes      TEXT,
    duration    TEXT,
    rating      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS diary_entries (
    user_id     TEXT NOT NULL,
    film_id     TEXT NOT NULL,
    rating      REAL,
    liked       BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, film_id)
);
