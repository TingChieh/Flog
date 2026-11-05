"""Rebuildable SQLite trigram index; source-of-truth remains the post table."""
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError


TRIGGERS = {
    'post_search_insert': '''CREATE TRIGGER IF NOT EXISTS post_search_insert AFTER INSERT ON post BEGIN
        INSERT INTO post_search(rowid, title, body) VALUES (new.id, new.title, new.body); END''',
    'post_search_update': '''CREATE TRIGGER IF NOT EXISTS post_search_update AFTER UPDATE OF title, body, is_published ON post BEGIN
        DELETE FROM post_search WHERE rowid = old.id;
        INSERT INTO post_search(rowid, title, body) VALUES (new.id, new.title, new.body); END''',
    'post_search_delete': '''CREATE TRIGGER IF NOT EXISTS post_search_delete AFTER DELETE ON post BEGIN
        DELETE FROM post_search WHERE rowid = old.id; END''',
}


def _index_objects(connection):
    return connection.execute(sa.text(
        "SELECT lower(name), sql FROM sqlite_master WHERE lower(name) IN "
        "('post_search', 'post_search_insert', 'post_search_update', 'post_search_delete')"
    )).all()


def _compatible(name, sql):
    normalized = ' '.join((sql or '').lower().split()).replace('if not exists ', '')
    if name == 'post_search':
        return (normalized.startswith('create virtual table post_search using fts5(')
                and "tokenize='trigram'" in normalized)
    return normalized == ' '.join(TRIGGERS[name].lower().split()).replace('if not exists ', '')


def search_index_available(connection):
    if connection.dialect.name != 'sqlite':
        return False
    objects = _index_objects(connection)
    return len(objects) == 4 and all(_compatible(name, sql) for name, sql in objects)


def rebuild_search_index(connection):
    """Create or repopulate the disposable index. Return False if unsupported."""
    if connection.dialect.name != 'sqlite':
        return False
    if not all(_compatible(name, sql) for name, sql in _index_objects(connection)):
        return False
    try:
        connection.execute(sa.text("CREATE VIRTUAL TABLE IF NOT EXISTS post_search USING fts5(title, body, tokenize='trigram')"))
    except OperationalError:
        return False
    for statement in TRIGGERS.values():
        connection.execute(sa.text(statement))
    connection.execute(sa.text('DELETE FROM post_search'))
    connection.execute(sa.text('INSERT INTO post_search(rowid, title, body) SELECT id, title, body FROM post'))
    return True
