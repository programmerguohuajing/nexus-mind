CREATE TABLE IF NOT EXISTS notes (
  path TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  version TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repositories (
  name TEXT PRIMARY KEY,
  branch TEXT NOT NULL DEFAULT '',
  remote TEXT NOT NULL DEFAULT '',
  current_user_name TEXT NOT NULL DEFAULT '',
  current_user_email TEXT NOT NULL DEFAULT '',
  last_sync TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS git_commits (
  repository TEXT NOT NULL,
  hash TEXT NOT NULL,
  short_hash TEXT NOT NULL DEFAULT '',
  authored_at TEXT NOT NULL DEFAULT '',
  author_name TEXT NOT NULL DEFAULT '',
  author_email TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '',
  branch TEXT NOT NULL DEFAULT '',
  collected_day TEXT NOT NULL,
  PRIMARY KEY (repository, hash)
);

CREATE INDEX IF NOT EXISTS idx_git_commits_day
  ON git_commits(collected_day);
CREATE INDEX IF NOT EXISTS idx_git_commits_author
  ON git_commits(author_email);

CREATE TABLE IF NOT EXISTS git_tags (
  repository TEXT NOT NULL,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT '',
  target_author_email TEXT NOT NULL DEFAULT '',
  collected_day TEXT NOT NULL,
  PRIMARY KEY (repository, name)
);

CREATE INDEX IF NOT EXISTS idx_git_tags_day
  ON git_tags(collected_day);

CREATE TABLE IF NOT EXISTS cloud_files (
  object_key TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  bytes INTEGER NOT NULL DEFAULT 0,
  source_type TEXT NOT NULL DEFAULT '',
  markdown_path TEXT NOT NULL DEFAULT '',
  uploaded_at TEXT NOT NULL
);
