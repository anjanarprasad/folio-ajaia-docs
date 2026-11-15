"""End-to-end HTTP/API tests, no third-party test runner required."""
import http.cookiejar
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_server, sanitize


class FolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        dbpath = Path(cls.tmp.name) / 'docs.db'
        cls.srv = create_server('127.0.0.1', 0, f'sqlite:///{dbpath}', 'test-secret')
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.srv.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        bootstrap = self.call('GET', '/api/bootstrap')
        self.csrf = bootstrap['csrf']

    def call(self, method, route, body=None, headers=None):
        headers = dict(headers or {})
        payload = None
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                payload = body
            else:
                payload = json.dumps(body).encode()
                headers.setdefault('Content-Type', 'application/json')
        if method != 'GET' and hasattr(self, 'csrf'):
            headers['X-CSRF-Token'] = self.csrf
        req = urllib.request.Request(self.base+route, data=payload, method=method, headers=headers)
        try:
            with self.opener.open(req) as resp:
                return json.loads(resp.read()) if resp.headers.get('Content-Type','').startswith('application/json') else resp.read()
        except urllib.error.HTTPError as e:
            return {'status':e.code, **json.loads(e.read())}

    def switch(self, id):
        self.call('POST','/api/switch',{'user_id':id})
        self.csrf = self.call('GET','/api/bootstrap')['csrf']

    def test_create_save_and_reopen_after_refresh(self):
        doc = self.call('POST','/api/documents', {'title':'Research plan'})['document']
        saved = self.call('PATCH',f'/api/documents/{doc["id"]}',
                         {'revision':doc['revision'],'title':'Renamed plan','content':'<h2>Agenda</h2><ul><li><b>First</b></li></ul>'})['document']
        self.assertIn('<b>First</b>',saved['content'])
        self.assertEqual(saved['revision'],2)
        fresh_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with fresh_opener.open(self.base+f'/api/documents/{doc["id"]}') as resp:
            fresh=json.loads(resp.read())['document']
        self.assertEqual(fresh['title'],'Renamed plan')
        self.assertIn('<h2>Agenda</h2>',fresh['content'])

    def test_sharing_editor_and_viewer_permissions(self):
        doc=self.call('POST','/api/documents',{'title':'Share me'})['document']
        self.call('POST',f'/api/documents/{doc["id"]}/share',{'email':'alex@example.com','role':'edit'})
        self.call('POST',f'/api/documents/{doc["id"]}/share',{'email':'priya@example.com','role':'view'})
        self.switch(2)
        self.assertTrue(any(x['id']==doc['id'] and x['permission']=='edit' for x in self.call('GET','/api/documents')['documents']))
        self.call('PATCH',f'/api/documents/{doc["id"]}',{'revision':1,'content':'<p>Edited by Alex</p>'})
        self.switch(3)
        self.assertEqual(self.call('GET',f'/api/documents/{doc["id"]}')['document']['permission'],'view')
        denied=self.call('PATCH',f'/api/documents/{doc["id"]}',{'revision':2,'content':'<p>not allowed</p>'})
        self.assertEqual(denied['status'],403)
        self.assertEqual(self.call('POST',f'/api/documents/{doc["id"]}/share',{'email':'alex@example.com','role':'view'})['status'],403)

    def test_unshared_user_cannot_read(self):
        doc=self.call('POST','/api/documents',{'title':'Private'})['document']
        self.switch(2)
        self.assertEqual(self.call('GET',f'/api/documents/{doc["id"]}')['status'],404)

    def test_stale_revision_rejected(self):
        doc=self.call('POST','/api/documents',{'title':'Revisions'})['document']
        self.call('PATCH',f'/api/documents/{doc["id"]}',{'revision':1,'content':'<p>first edit</p>'})
        result=self.call('PATCH',f'/api/documents/{doc["id"]}',{'revision':1,'content':'<p>stale edit</p>'})
        self.assertEqual(result['status'],409)
        self.assertIn('first edit',self.call('GET',f'/api/documents/{doc["id"]}')['document']['content'])

    def test_file_upload(self):
        boundary='BOUNDARY123'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="meeting.txt"\r\n'
              f'Content-Type: text/plain\r\n\r\nHello team\nNext steps\r\n--{boundary}--\r\n').encode()
        result=self.call('POST','/api/import',body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
        self.assertEqual(result['document']['title'],'meeting')
        self.assertIn('<p>Next steps</p>',result['document']['content'])

    def test_xss_stripped_and_csrf_enforced(self):
        self.assertEqual(sanitize('<p onclick="evil()">Hi <b>team</b><script>alert(1)</script></p>'),'<p>Hi <b>team</b></p>')
        result=self.call('POST','/api/documents',{'title':'<img onerror=alert(1)>'})
        self.assertEqual(result['status'] if 'status' in result else 201, 201)
        # Missing header must not allow mutations.
        req=urllib.request.Request(self.base+'/api/documents',data=b'{"title":"bad"}',method='POST',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:self.opener.open(req)
        self.assertEqual(ctx.exception.code,403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
