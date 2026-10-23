"""Run only after deploying the bridge. Probe the real endpoint before packaging it."""
import json, os, sys, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
endpoint=input('Deployed HTTPS MCP endpoint: ').strip()
u=urlsplit(endpoint)
if u.scheme!='https' or not u.netloc or u.username or u.password or u.fragment or u.query:
    raise SystemExit('An HTTPS endpoint without embedded credentials/query is required')
token=os.environ.get('MCP_API_TOKEN')
if not token: raise SystemExit('Set MCP_API_TOKEN in this process environment; do not pass it as an argument')
req=urllib.request.Request(endpoint,data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json'})
try:
    with urllib.request.urlopen(req,timeout=30) as r: obj=json.load(r)
    names={x['name'] for x in obj['result']['tools']}
    if not {'naver_status','naver_move_read_inbox','naver_sample_folder','naver_list_read_inbox','naver_read_message','naver_list_folders','naver_read_messages','naver_move_read_inbox_batch','naver_verify_moves','naver_get_move_results'}<=names: raise ValueError('Expected tools missing')
except Exception:
    raise SystemExit('Endpoint verification failed. No MCP configuration was written.')
config={'$schema':'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json','mcpServers':{'naver-mail':{'type':'streamable-http','url':endpoint,'extensions':{'com.openai':{'auth':{'type':'api_key','headerScheme':'bearer'}}}}}}
(Path(__file__).resolve().parents[1]/'mcp.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Verified tools/list; wrote mcp.json without credentials. IMAP login and move still require a real-account test.')
