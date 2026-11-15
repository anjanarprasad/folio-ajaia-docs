"""Folio: a small full-stack collaborative document editor.

Runs with Python's standard library + SQLite. Set DATABASE_URL=postgresql://...
for PostgreSQL (requires the psycopg2-binary optional deployment dependency).
Demo accounts are deliberately selectable, not a production authentication system.
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default as email_policy
from html.parser import HTMLParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
MAX_JSON = 500_000
MAX_UPLOAD = 1_100_000
USERS = [
    (1, 'Anjana Prasad', 'anjana@example.com'),
    (2, 'Alex Morgan', 'alex@example.com'),
    (3, 'Priya Shah', 'priya@example.com'),
]


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SafeHTML(HTMLParser):
    """Allow a small, attribute-free rich-text subset; reject executable HTML."""
    allowed = {'p', 'div', 'br', 'b', 'strong', 'i', 'em', 'u', 'h1', 'h2', 'h3',
               'ul', 'ol', 'li', 'blockquote'}
    void = {'br'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.result = []
        self.stack = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'iframe', 'svg', 'math'}:
            self.suppressed += 1
        elif not self.suppressed and tag in self.allowed:
            self.result.append(f'<{tag}>')
            if tag not in self.void:
                self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag == 'br' and not self.suppressed:
            self.result.append('<br>')

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'iframe', 'svg', 'math'} and self.suppressed:
            self.suppressed -= 1
        elif not self.suppressed and tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.result.append(f'</{current}>')
                if current == tag:
                    break

    def handle_data(self, data):
        if not self.suppressed:
            self.result.append(html.escape(data, quote=False))

    def get_html(self):
        while self.stack:
            self.result.append(f'</{self.stack.pop()}>')
        return ''.join(self.result)


def sanitize(value):
    parser = SafeHTML()
    parser.feed(value)
    parser.close()
    return parser.get_html()


def text_to_html(text):
    return ''.join('<p>' + (html.escape(line) if line else '<br>') + '</p>'
                   for line in text.splitlines()) or '<p><br></p>'


class Store:
    def __init__(self, url):
        self.url = url
        self.pg = url.startswith(('postgresql://', 'postgres://'))
        self.lock = threading.RLock()
        if not self.pg:
            self.path = url.removeprefix('sqlite:///')
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        if self.pg:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            return psycopg2.connect(self.url.replace('postgres://', 'postgresql://', 1), cursor_factory=RealDictCursor)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=15000')
        return connection

    def query(self, sql, args=(), mode='all'):
        with self.lock:
            connection = self.connect()
            try:
                cur = connection.cursor()
                cur.execute(sql.replace('?', '%s') if self.pg else sql, args)
                if mode == 'one':
                    row = cur.fetchone()
                    result = dict(row) if row else None
                elif mode == 'all':
                    result = [dict(r) for r in cur.fetchall()]
                elif mode == 'insert':
                    if self.pg:
                        result = cur.fetchone()['id']
                    else:
                        result = cur.lastrowid
                else:
                    result = cur.rowcount
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def initialize(self):
        pk = 'SERIAL PRIMARY KEY' if self.pg else 'INTEGER PRIMARY KEY AUTOINCREMENT'
        stmts = [
            '''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL)''',
            f'''CREATE TABLE IF NOT EXISTS documents (
                id {pk}, owner_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
                revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS shares (
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                role TEXT NOT NULL CHECK(role IN ('view', 'edit')),
                PRIMARY KEY (document_id, user_id))''',
            '''CREATE INDEX IF NOT EXISTS idx_doc_owner ON documents(owner_id)''',
            '''CREATE INDEX IF NOT EXISTS idx_share_user ON shares(user_id)''',
        ]
        for stmt in stmts:
            self.query(stmt, mode='write')
        for account in USERS:
            self.query('INSERT INTO users (id, name, email) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING',
                       account, mode='write')

    def users(self):
        return self.query('SELECT id,name,email FROM users ORDER BY id')

    def list_docs(self, user_id):
        return self.query('''SELECT d.id,d.title,d.owner_id,d.updated_at,d.revision,u.name AS owner_name,
                   CASE WHEN d.owner_id=? THEN 'owner' ELSE s.role END AS permission
                   FROM documents d JOIN users u ON u.id=d.owner_id
                   LEFT JOIN shares s ON s.document_id=d.id AND s.user_id=?
                   WHERE d.owner_id=? OR s.user_id=? ORDER BY d.updated_at DESC, d.id DESC''',
                          (user_id, user_id, user_id, user_id))

    def get_doc(self, doc_id, user_id):
        doc = self.query('''SELECT d.*,u.name AS owner_name,
                 CASE WHEN d.owner_id=? THEN 'owner' ELSE s.role END AS permission
                 FROM documents d JOIN users u ON u.id=d.owner_id
                 LEFT JOIN shares s ON s.document_id=d.id AND s.user_id=?
                 WHERE d.id=? AND (d.owner_id=? OR s.user_id=?)''',
                         (user_id, user_id, doc_id, user_id, user_id), mode='one')
        if doc:
            doc['collaborators'] = self.query('''SELECT u.id,u.name,u.email,s.role FROM shares s
                                              JOIN users u ON u.id=s.user_id WHERE s.document_id=? ORDER BY u.id''',
                                              (doc_id,))
        return doc

    def create_doc(self, owner_id, title='Untitled document', content='<p><br></p>'):
        now = utc_now()
        statement = '''INSERT INTO documents (owner_id,title,content,created_at,updated_at)
                       VALUES (?,?,?,?,?)'''
        if self.pg:
            statement += ' RETURNING id'
        return self.query(statement, (owner_id, title, content, now, now), mode='insert')

    def update_doc(self, doc_id, user_id, revision, title=None, content=None):
        doc = self.get_doc(doc_id, user_id)
        if not doc:
            raise ApiError(404, 'Document not found or not shared with you')
        if doc['permission'] == 'view':
            raise ApiError(403, 'View-only access: editing is not allowed')
        if revision != doc['revision']:
            raise ApiError(409, 'This document changed elsewhere. Reopen it before editing again.')
        title = doc['title'] if title is None else title
        content = doc['content'] if content is None else content
        count = self.query('''UPDATE documents SET title=?,content=?,updated_at=?,revision=revision+1
                             WHERE id=? AND revision=?''',
                           (title, content, utc_now(), doc_id, revision), mode='write')
        if not count:
            raise ApiError(409, 'Save conflict: another edit was saved first')
        return self.get_doc(doc_id, user_id)

    def grant(self, doc_id, owner_id, target_id, role):
        doc = self.get_doc(doc_id, owner_id)
        if not doc:
            raise ApiError(404, 'Document not found')
        if doc['owner_id'] != owner_id:
            raise ApiError(403, 'Only the owner can change sharing permissions')
        if target_id == owner_id:
            raise ApiError(400, 'You already own this document')
        self.query('''INSERT INTO shares(document_id,user_id,role) VALUES(?,?,?)
                      ON CONFLICT(document_id,user_id) DO UPDATE SET role=excluded.role''',
                   (doc_id, target_id, role), mode='write')

    def revoke(self, doc_id, owner_id, target_id):
        doc = self.get_doc(doc_id, owner_id)
        if not doc:
            raise ApiError(404, 'Document not found')
        if doc['owner_id'] != owner_id:
            raise ApiError(403, 'Only the owner can change sharing permissions')
        self.query('DELETE FROM shares WHERE document_id=? AND user_id=?', (doc_id, target_id), mode='write')


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def make_handler(store, secret):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'Folio/1.0'

        def log_message(self, fmt, *args):
            if os.getenv('QUIET') != '1':
                super().log_message(fmt, *args)

        def respond(self, status, body, mime='application/json', cookies=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; object-src 'none'; frame-ancestors 'none'")
            if cookies:
                self.send_header('Set-Cookie', cookies)
            self.end_headers()
            self.wfile.write(body)

        def auth(self):
            raw = self.headers.get('Cookie', '')
            match = re.search(r'(?:^|;\s*)folio_session=(\d+)\.([0-9a-f]{64})', raw)
            if match:
                uid = int(match.group(1))
                digest = hmac.new(secret.encode(), str(uid).encode(), hashlib.sha256).hexdigest()
                if hmac.compare_digest(digest, match.group(2)) and uid in [a[0] for a in USERS]:
                    return uid
            return 1

        def cookie(self, uid):
            sig = hmac.new(secret.encode(), str(uid).encode(), hashlib.sha256).hexdigest()
            secure = '; Secure' if self.headers.get('X-Forwarded-Proto', '') == 'https' else ''
            return f'folio_session={uid}.{sig}; Path=/; HttpOnly; SameSite=Lax{secure}'

        def csrf(self, uid):
            return hmac.new(secret.encode(), f'csrf:{uid}'.encode(), hashlib.sha256).hexdigest()

        def body_json(self):
            n = int(self.headers.get('Content-Length', '0'))
            if n < 0 or n > MAX_JSON:
                raise ApiError(413, 'Request body too large')
            try:
                data = json.loads(self.rfile.read(n))
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, 'Invalid JSON')
            if not isinstance(data, dict):
                raise ApiError(400, 'Expected a JSON object')
            return data

        def route(self, method):
            path = urlparse(self.path).path
            uid = self.auth()
            if method == 'GET' and path == '/health':
                return self.respond(200, {'status':'ok'})
            if method == 'GET' and path == '/':
                return self.respond(200, (ROOT/'static/index.html').read_bytes(), 'text/html; charset=utf-8', self.cookie(uid))
            if method == 'GET' and path in ('/static/app.css', '/static/app.js'):
                mime = 'text/css; charset=utf-8' if path.endswith('.css') else 'text/javascript; charset=utf-8'
                return self.respond(200, (ROOT/path.lstrip('/')).read_bytes(), mime)
            if not path.startswith('/api/'):
                raise ApiError(404, 'Not found')
            if method != 'GET' and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), self.csrf(uid)):
                raise ApiError(403, 'CSRF token missing or invalid. Refresh and try again.')
            if method == 'GET' and path == '/api/bootstrap':
                return self.respond(200, {'me': next(dict(id=u[0],name=u[1],email=u[2]) for u in USERS if u[0]==uid),
                                          'users': store.users(), 'documents': store.list_docs(uid), 'csrf': self.csrf(uid) },
                                    cookies=self.cookie(uid))
            if method == 'POST' and path == '/api/switch':
                data = self.body_json()
                target = data.get('user_id')
                if type(target) is not int or target not in [u[0] for u in USERS]:
                    raise ApiError(400, 'Choose a valid demo user')
                return self.respond(200, {'ok': True}, cookies=self.cookie(target))
            if method == 'GET' and path == '/api/documents':
                return self.respond(200, {'documents':store.list_docs(uid)})
            if method == 'POST' and path == '/api/documents':
                data = self.body_json()
                title = data.get('title', 'Untitled document')
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
                    raise ApiError(400, 'Title must be between 1 and 100 characters')
                did = store.create_doc(uid, title.strip())
                return self.respond(201, {'document':store.get_doc(did, uid)})
            if method == 'POST' and path == '/api/import':
                ctype = self.headers.get('Content-Type', '')
                n = int(self.headers.get('Content-Length', '0'))
                if not ctype.startswith('multipart/form-data') or 'boundary=' not in ctype:
                    raise ApiError(400, 'Expected a multipart file upload')
                if n < 1 or n > MAX_UPLOAD:
                    raise ApiError(413, 'File limit is 1 MB')
                multipart = BytesParser(policy=email_policy).parsebytes(
                    f'MIME-Version: 1.0\r\nContent-Type: {ctype}\r\n\r\n'.encode() + self.rfile.read(n))
                files = [p for p in multipart.iter_parts() if p.get_param('name', header='content-disposition') == 'file']
                if len(files) != 1:
                    raise ApiError(400, 'Select one .txt file')
                f = files[0]
                filename = f.get_filename() or ''
                if not filename.lower().endswith('.txt'):
                    raise ApiError(400, 'Only .txt imports are supported')
                content = f.get_payload(decode=True)
                if not content or len(content) > 1_000_000:
                    raise ApiError(400, 'Choose a nonempty UTF-8 file under 1 MB')
                try:
                    txt = content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    raise ApiError(400, 'The file must be UTF-8 encoded')
                title = Path(filename.replace('\\','/').split('/')[-1]).stem[:100].strip() or 'Imported document'
                did = store.create_doc(uid, title, text_to_html(txt))
                return self.respond(201, {'document':store.get_doc(did, uid)})
            match = re.fullmatch(r'/api/documents/(\d+)', path)
            if match:
                did = int(match.group(1))
                if method == 'GET':
                    doc = store.get_doc(did, uid)
                    if not doc:
                        raise ApiError(404, 'Document not found or not shared with you')
                    return self.respond(200, {'document':doc})
                if method == 'PATCH':
                    data = self.body_json()
                    revision = data.get('revision')
                    if type(revision) is not int or revision < 1:
                        raise ApiError(400, 'Valid revision is required')
                    title, content = data.get('title'), data.get('content')
                    if title is None and content is None:
                        raise ApiError(400, 'Provide title and/or content')
                    if title is not None and (not isinstance(title,str) or not 1 <= len(title.strip()) <= 100):
                        raise ApiError(400, 'Title must be between 1 and 100 characters')
                    if content is not None and (not isinstance(content,str) or len(content)>200_000):
                        raise ApiError(400, 'Content must be a string under 200 KB')
                    doc = store.update_doc(did, uid, revision, title.strip() if title is not None else None,
                                           sanitize(content) if content is not None else None)
                    return self.respond(200, {'document':doc})
            match = re.fullmatch(r'/api/documents/(\d+)/share', path)
            if match and method == 'POST':
                did = int(match.group(1))
                data = self.body_json()
                email = data.get('email')
                role = data.get('role')
                if not isinstance(email,str) or role not in ('view','edit'):
                    raise ApiError(400, 'Select a demo user and a valid role')
                other = next((a for a in USERS if a[2].lower() == email.strip().lower()),None)
                if not other:
                    raise ApiError(400, 'Only seeded demo accounts can be shared with')
                store.grant(did, uid, other[0], role)
                return self.respond(200, {'document':store.get_doc(did,uid)})
            match = re.fullmatch(r'/api/documents/(\d+)/share/(\d+)', path)
            if match and method == 'DELETE':
                did, target = int(match.group(1)), int(match.group(2))
                store.revoke(did,uid,target)
                return self.respond(200, {'document':store.get_doc(did,uid)})
            raise ApiError(404,'Not found')

        def handle_request(self, method):
            try:
                self.route(method)
            except ApiError as exc:
                self.respond(exc.status, {'error':exc.message})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                print(f'Internal error: {type(exc).__name__}: {exc}', flush=True)
                self.respond(500, {'error':'Internal server error'})

        def do_GET(self): self.handle_request('GET')
        def do_POST(self): self.handle_request('POST')
        def do_PATCH(self): self.handle_request('PATCH')
        def do_DELETE(self): self.handle_request('DELETE')
    return Handler


def create_server(host='0.0.0.0', port=None, db_url=None, secret=None):
    db_url = db_url or os.getenv('DATABASE_URL') or f'sqlite:///{ROOT / "data" / "folio.db"}'
    secret = secret or os.getenv('SECRET_KEY', 'local-demo-key-only-change-in-production')
    store = Store(db_url)
    return ThreadingHTTPServer((host, int(port if port is not None else os.getenv('PORT', '8000'))),
                               make_handler(store, secret))


if __name__ == '__main__':
    web = create_server()
    print(f'Folio running on http://localhost:{web.server_port}',flush=True)
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        web.shutdown()
