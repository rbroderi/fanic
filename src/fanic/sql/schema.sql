PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS works (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    rating TEXT NOT NULL DEFAULT 'Not Rated',
    warnings TEXT NOT NULL DEFAULT 'No Archive Warnings Apply',
    language TEXT NOT NULL DEFAULT 'en',
    status TEXT NOT NULL DEFAULT 'in_progress',
    creators TEXT NOT NULL DEFAULT '[]',
    series_name TEXT,
    series_index INTEGER,
    published_at TEXT,
    cover_page_index INTEGER NOT NULL DEFAULT 1,
    page_count INTEGER NOT NULL DEFAULT 0,
    cbz_path TEXT NOT NULL,
    uploader_username TEXT,
    last_metadata_editor TEXT,
    last_metadata_edited_at TEXT,
    last_metadata_edited_by_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN (
        'rating',
        'archive_warning',
        'fandom',
        'category',
        'relationship',
        'character',
        'freeform'
    ))
);

CREATE TABLE IF NOT EXISTS tag_synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_slug TEXT NOT NULL UNIQUE,
    alias_name TEXT NOT NULL,
    canonical_tag_id INTEGER NOT NULL,
    FOREIGN KEY (canonical_tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS work_tags (
    work_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (work_id, tag_id),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    image_filename TEXT NOT NULL,
    thumb_filename TEXT,
    width INTEGER,
    height INTEGER,
    UNIQUE (work_id, page_index),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fanart_items (
    id TEXT PRIMARY KEY,
    uploader_username TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    fandom TEXT NOT NULL DEFAULT '',
    rating TEXT NOT NULL DEFAULT 'Not Rated',
    image_filename TEXT NOT NULL,
    thumb_filename TEXT,
    width INTEGER,
    height INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fanart_galleries (
    id TEXT PRIMARY KEY,
    uploader_username TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (uploader_username, slug)
);

CREATE TABLE IF NOT EXISTS fanart_gallery_items (
    gallery_id TEXT NOT NULL,
    fanart_item_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (gallery_id, fanart_item_id),
    FOREIGN KEY (gallery_id) REFERENCES fanart_galleries(id) ON DELETE CASCADE,
    FOREIGN KEY (fanart_item_id) REFERENCES fanart_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reading_progress (
    work_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (work_id, user_id),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_bookmarks (
    username TEXT NOT NULL,
    work_id TEXT NOT NULL,
    page_index INTEGER NOT NULL DEFAULT 1,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (username, work_id),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    actor_username TEXT NOT NULL,
    work_id TEXT,
    kind TEXT NOT NULL DEFAULT 'generic',
    message TEXT NOT NULL,
    href TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    email TEXT,
    is_over_18 INTEGER,
    age_gate_completed INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_identities (
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    username TEXT NOT NULL,
    email TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, subject),
    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preferences (
    username TEXT PRIMARY KEY,
    view_mature_rated INTEGER NOT NULL DEFAULT 0,
    view_explicit_rated INTEGER NOT NULL DEFAULT 0,
    custom_theme_enabled INTEGER NOT NULL DEFAULT 0,
    custom_theme_toml TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    username TEXT NOT NULL,
    chapter_number INTEGER,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS work_kudos (
    work_id TEXT NOT NULL,
    username TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (work_id, username),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS work_chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT NOT NULL,
    chapter_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_page INTEGER NOT NULL,
    end_page INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
    UNIQUE (work_id, chapter_index)
);

CREATE TABLE IF NOT EXISTS work_chapter_pages (
    chapter_id INTEGER NOT NULL,
    page_image_filename TEXT NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (chapter_id, page_image_filename),
    FOREIGN KEY (chapter_id) REFERENCES work_chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dmca_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id TEXT,
    work_title TEXT NOT NULL DEFAULT '',
    issue_type TEXT NOT NULL DEFAULT 'copyright-dmca',
    status TEXT NOT NULL DEFAULT 'open',
    reporter_name TEXT NOT NULL,
    reporter_email TEXT NOT NULL,
    reason TEXT NOT NULL,
    claimed_url TEXT NOT NULL,
    evidence_url TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL,
    reporter_username TEXT,
    source_path TEXT NOT NULL DEFAULT '/dmca',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_works_slug ON works(slug);
CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(type);
CREATE INDEX IF NOT EXISTS idx_work_tags_work ON work_tags(work_id);
CREATE INDEX IF NOT EXISTS idx_work_tags_tag ON work_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_pages_work ON pages(work_id);
CREATE INDEX IF NOT EXISTS idx_fanart_items_uploader_created_at ON fanart_items(uploader_username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fanart_galleries_uploader_created_at ON fanart_galleries(uploader_username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fanart_gallery_items_gallery_position ON fanart_gallery_items(gallery_id, position ASC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_fanart_gallery_items_fanart_item ON fanart_gallery_items(fanart_item_id);
CREATE INDEX IF NOT EXISTS idx_work_comments_work ON work_comments(work_id);
CREATE INDEX IF NOT EXISTS idx_work_chapters_work ON work_chapters(work_id);
CREATE INDEX IF NOT EXISTS idx_work_chapter_pages_chapter ON work_chapter_pages(chapter_id);
CREATE INDEX IF NOT EXISTS idx_dmca_reports_created_at ON dmca_reports(created_at);
CREATE INDEX IF NOT EXISTS idx_dmca_reports_work_id ON dmca_reports(work_id);
CREATE INDEX IF NOT EXISTS idx_user_bookmarks_username_updated_at ON user_bookmarks(username, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_username_created_at ON notifications(username, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_username_is_read ON notifications(username, is_read);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_display_name_unique
ON users(lower(display_name))
WHERE trim(display_name) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
ON users(lower(email))
WHERE email IS NOT NULL AND trim(email) <> '';
CREATE INDEX IF NOT EXISTS idx_auth_identities_username ON auth_identities(username);
CREATE INDEX IF NOT EXISTS idx_auth_identities_email ON auth_identities(email);
