import importlib.util, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('bridge',Path(__file__).parents[1]/'server/server.py'); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)

class Fake:
    capabilities=(b'IMAP4rev1',b'MOVE')
    def __init__(self,seen=True): self.seen=seen; self.calls=[]
    def list(self): return 'OK',[b'(\\HasNoChildren) "/" "Work"',b'(\\Sent) "/" "Sent"',b'(\\HasNoChildren) "/" "INBOX"']
    def select(self,*a,**kw): return 'OK',[b'1']
    def response(self,*a): return 'UIDVALIDITY',[b'42']
    def uid(self,*args):
        self.calls.append(args)
        if args[0]=='FETCH' and args[2]=='(RFC822.SIZE)': return 'OK',[b'1 (RFC822.SIZE 150)']
        if args[0]=='FETCH': return 'OK',[(b'1 (UID 7 FLAGS ('+(b'\\Seen \\Flagged' if self.seen else b'\\Flagged')+b') BODY[] {100}',b'From: sender@example.org\r\nSubject: Test\r\n\r\nhello')]
        if args[0]=='SEARCH': return 'OK',[b'7']
        return 'OK',[b'done']
    def logout(self): pass

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.env=patch.dict(os.environ,{'NAVER_USER':'owner','NAVER_HANDLE_KEY':'unit-secret','NAVER_CLASSIFICATION_FOLDERS':'["Work","Sent","INBOX"]','NAVER_ALLOW_MOVE':'true','NAVER_AUDIT_DB':self.tmp.name+'/audit.sqlite3'}); self.env.start()
    def tearDown(self): self.env.stop(); self.tmp.cleanup()
    def handle(self,kind='candidate'): return s.signed('INBOX' if kind=='candidate' else 'Work','7','42',kind)
    def test_folder_codec(self):
        for t in ['보안·계정','A&B','Work']: self.assertEqual(s.decode_folder(s.encode_folder(t)),t)
    def test_tamper(self):
        with self.assertRaises(ValueError): s.unpack(self.handle()[:-1]+'x')
    def test_excludes_system(self): self.assertEqual(s.folders(Fake()),['Work'])
    def test_unread_refused(self):
        f=Fake(False)
        with patch.object(s,'connect',return_value=f),self.assertRaises(ValueError): s.dispatch('naver_move_read_inbox',{'handle':self.handle(),'destination':'Work'})
        self.assertFalse(any(c[0]=='MOVE' for c in f.calls))
    def test_reference_refused(self):
        with patch.object(s,'connect',return_value=Fake()),self.assertRaises(ValueError): s.dispatch('naver_move_read_inbox',{'handle':self.handle('reference'),'destination':'Work'})
    def test_wrong_destination(self):
        with patch.object(s,'connect',return_value=Fake()),self.assertRaises(ValueError): s.dispatch('naver_move_read_inbox',{'handle':self.handle(),'destination':'Sent'})
    def test_disabled(self):
        with patch.dict(os.environ,{'NAVER_ALLOW_MOVE':'false'}),patch.object(s,'connect',return_value=Fake()),self.assertRaises(ValueError): s.dispatch('naver_move_read_inbox',{'handle':self.handle(),'destination':'Work'})
    def test_move_idempotent_and_flags_untouched(self):
        f=Fake()
        with patch.object(s,'connect',return_value=f):
            a=s.dispatch('naver_move_read_inbox',{'handle':self.handle(),'destination':'Work'})
            b=s.dispatch('naver_move_read_inbox',{'handle':self.handle(),'destination':'Work'})
        self.assertEqual(a['status'],'moved'); self.assertEqual(b['status'],'already_moved')
        self.assertEqual(sum(c[0]=='MOVE' for c in f.calls),1)
        self.assertFalse(any(c[0] in ['STORE','EXPUNGE','COPY'] for c in f.calls))
    def test_peek(self):
        f=Fake()
        with patch.object(s,'connect',return_value=f): s.dispatch('naver_read_message',{'handle':self.handle()})
        self.assertIn('BODY.PEEK[]',f.calls[1][2])
    def test_unsupported_move(self):
        f=Fake(); f.capabilities=(b'IMAP4rev1',)
        with patch.object(s,'connect',return_value=f),self.assertRaises(ValueError): s.dispatch('naver_move_read_inbox',{'handle':self.handle(),'destination':'Work'})
    def test_pagination(self):
        with patch.object(s,'connect',return_value=Fake()):
            self.assertEqual(s.dispatch('naver_list_read_inbox',{'after_uid':7})['messages'],[])
    def test_large_body_is_not_downloaded(self):
        f=Fake()
        with patch.dict(os.environ,{'NAVER_MAX_MESSAGE_BYTES':'10'}),patch.object(s,'connect',return_value=f),self.assertRaises(ValueError):
            s.dispatch('naver_read_message',{'handle':self.handle()})
        self.assertFalse(any('BODY.PEEK[]' in str(c) for c in f.calls))
    def test_invalid_rpc(self):
        self.assertEqual(s.rpc([])['error']['code'],-32600)
    def test_tools(self):
        tools=s.rpc({'id':1,'method':'tools/list'})['result']['tools']
        self.assertEqual(len(tools),6)
        self.assertTrue(all(t['inputSchema']['additionalProperties'] is False for t in tools))

if __name__=='__main__': unittest.main()
