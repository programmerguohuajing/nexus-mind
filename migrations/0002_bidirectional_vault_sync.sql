CREATE TABLE IF NOT EXISTS sync_tombstones (
  path TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  deleted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_tombstones_deleted_at
  ON sync_tombstones(deleted_at);
