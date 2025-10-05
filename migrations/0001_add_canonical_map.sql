-- Create canonical_map table for synonym → canonical mappings.
CREATE TABLE IF NOT EXISTS canonical_map (
    dim TEXT NOT NULL,
    synonym TEXT NOT NULL,
    canonical TEXT NOT NULL,
    score DOUBLE,
    promoted_by TEXT,
    promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL
);

