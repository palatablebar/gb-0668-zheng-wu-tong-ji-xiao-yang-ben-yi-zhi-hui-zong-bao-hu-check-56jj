import os
import json
import sqlite3
from pathlib import Path
from app.errors import DomainError

# 更正版本链所需的附加列；旧库通过 ALTER TABLE 就地补齐。
_EXTRA = [
    ('lineage', 'TEXT'),
    ('parent', 'TEXT'),
    ('version', 'INTEGER NOT NULL DEFAULT 1'),
    ('status', "TEXT NOT NULL DEFAULT 'active'"),
    ('superseded_by', 'TEXT'),
    ('superseded_at', 'TEXT'),
]

def connect():
    path=Path(os.getenv('DB_PATH','state.sqlite'))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=15,isolation_level=None)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, reviewed INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP)')
    _migrate(db)
    return db

def _migrate(db):
    cols={row['name'] for row in db.execute('PRAGMA table_info(runs)')}
    added=False
    for name,ddl in _EXTRA:
        if name not in cols:
            db.execute(f'ALTER TABLE runs ADD COLUMN {name} {ddl}')
            added=True
    if added or db.execute('SELECT 1 FROM runs WHERE lineage IS NULL LIMIT 1').fetchone():
        db.execute('UPDATE runs SET lineage=id WHERE lineage IS NULL')
    if added or db.execute("SELECT 1 FROM runs WHERE status IS NULL OR status='' LIMIT 1").fetchone():
        db.execute("UPDATE runs SET status='active' WHERE status IS NULL OR status=''")
    db.execute('CREATE INDEX IF NOT EXISTS runs_lineage ON runs(lineage,version,created)')

def _decorate(row):
    item=json.loads(row['payload'])
    item.update({
        'revision':row['revision'],'reviewed':bool(row['reviewed']),'created_at':row['created'],
        'lineage':row['lineage'] or row['id'],'parent':row['parent'],'version':row['version'],
        'status':row['status'] or 'active','superseded_by':row['superseded_by'],'superseded_at':row['superseded_at'],
    })
    return item

def _fetch(db,rid):
    return db.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone()

def _tx(db,work):
    db.execute('BEGIN IMMEDIATE')
    try:
        out=work()
        db.execute('COMMIT')
        return out
    except BaseException:
        if db.in_transaction:db.execute('ROLLBACK')
        raise

def save(result):
    rid=result['manifest']['run_id']
    db=connect()
    try:
        def work():
            cur=db.execute("INSERT OR IGNORE INTO runs(id,payload,lineage,version,status) VALUES(?,?,?,1,'active')",(rid,json.dumps(result,ensure_ascii=False),rid))
            return cur.rowcount==1
        created=_tx(db,work)
    finally:
        db.close()
    return read(rid)|{'created':created}

def read(rid):
    db=connect()
    try:
        row=_fetch(db,rid)
        if not row:raise DomainError('RUN_MISSING','批次不存在',404)
        return _decorate(row)
    finally:
        db.close()

def history():
    db=connect()
    try:
        rows=db.execute('SELECT id,revision,reviewed,created,version,status,lineage,parent FROM runs ORDER BY created DESC,id DESC LIMIT 100').fetchall()
        return [dict(row) for row in rows]
    finally:
        db.close()

def family(rid):
    db=connect()
    try:
        row=_fetch(db,rid)
        if not row:raise DomainError('RUN_MISSING','批次不存在',404)
        root=row['lineage'] or row['id']
        rows=db.execute('SELECT * FROM runs WHERE id=? OR lineage=? ORDER BY version ASC,created ASC,id ASC',(root,root)).fetchall()
        return [_decorate(r) for r in rows]
    finally:
        db.close()

def head_of(rid):
    versions=family(rid)
    active=[item for item in versions if item['status']=='active']
    return active[-1] if active else versions[-1]

def review(rid,revision):
    db=connect()
    try:
        def work():
            row=db.execute('SELECT payload,revision,status FROM runs WHERE id=?',(rid,)).fetchone()
            if not row:raise DomainError('RUN_MISSING','批次不存在',404)
            if (row['status'] or 'active')=='superseded':
                raise DomainError('SUPERSEDED','该版本已被更正版取代，仅供回看，不再签章',409)
            if not json.loads(row['payload'])['reconcile']['balanced']:raise DomainError('UNBALANCED','对账未通过，先处理差异',409)
            cur=db.execute('UPDATE runs SET reviewed=1,revision=revision+1 WHERE id=? AND revision=?',(rid,revision))
            if cur.rowcount!=1:raise DomainError('STALE_VERSION','版本已变更，请重新加载',409)
        _tx(db,work)
    finally:
        db.close()
    return read(rid)

def correct(base_id,result):
    """在单个事务内把 result 置为 base 的继任有效版；失败则回滚，base 保持有效。"""
    rid=result['manifest']['run_id']
    db=connect()
    try:
        def work():
            base=_fetch(db,base_id)
            if not base:raise DomainError('RUN_MISSING','基准批次不存在',404)
            # 相同更正重试：目标批次已存在，原样返回，不新增版本、不重复切换。
            existing=_fetch(db,rid)
            if existing:
                return _decorate(existing)|{'created':False,'idempotent':True}
            if (base['status'] or 'active')!='active':
                raise DomainError('BASE_STALE','基准版本已停用，请在当前有效版上签发更正',409)
            current=json.loads(base['payload'])['manifest']
            incoming=result['manifest']
            if current['sha256']==incoming['sha256'] and current['params']==incoming['params']:
                return _decorate(base)|{'created':False,'unchanged':True}
            cur=db.execute("UPDATE runs SET status='superseded',superseded_by=?,superseded_at=CURRENT_TIMESTAMP WHERE id=? AND status='active'",(rid,base_id))
            if cur.rowcount!=1:raise DomainError('BASE_STALE','基准版本已变更，请重新加载',409)
            db.execute("INSERT INTO runs(id,payload,lineage,parent,version,status) VALUES(?,?,?,?,?,'active')",
                (rid,json.dumps(result,ensure_ascii=False),base['lineage'] or base['id'],base_id,(base['version'] or 1)+1))
            return _decorate(_fetch(db,rid))|{'created':True}
        saved=_tx(db,work)
    finally:
        db.close()
    return saved
