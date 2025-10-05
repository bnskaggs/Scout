-- Canonical synonym → canonical mapping storage.
CREATE SEQUENCE IF NOT EXISTS canonical_map_id_seq START 1;

CREATE TABLE IF NOT EXISTS canonical_map (
    id BIGINT DEFAULT nextval('canonical_map_id_seq'),
    dim TEXT NOT NULL,
    synonym TEXT NOT NULL,
    canonical TEXT NOT NULL,
    score DOUBLE NOT NULL DEFAULT 1.0,
    promoted_by TEXT,
    promoted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_canonical_map_dim_syn
    ON canonical_map(dim, synonym);

CREATE TABLE IF NOT EXISTS canonical_meta (
    k TEXT PRIMARY KEY,
    v BIGINT NOT NULL
);

INSERT INTO canonical_meta(k, v)
    VALUES ('version', 1)
    ON CONFLICT (k) DO NOTHING;

