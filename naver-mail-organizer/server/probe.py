"""Read-only diagnostics from inside the running container. Never prints credentials."""
import json,os,sys,urllib.request,urllib.error
mode=sys.argv[1] if len(sys.argv)>1 else 'status'
if mode not in ('status','tools'): raise SystemExit('Usage: python /app/probe.py [status|tools]')
reqdata={'jsonrpc':'2.0','id':1,'method':'tools/list'} if mode=='tools' else {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'naver_status','arguments':{}}}
req=urllib.request.Request('http://127.0.0.1:8080/mcp',data=json.dumps(reqdata).encode(),headers={'Authorization':'Bearer '+os.environ['MCP_API_TOKEN'],'Content-Type':'application/json','Accept':'application/json'})
try:
    with urllib.request.urlopen(req,timeout=90) as r: result=json.load(r)
except Exception as exc:
    raise SystemExit('Diagnostic failed: '+type(exc).__name__)
print(json.dumps(result,ensure_ascii=False,indent=2))
if result.get('error') or result.get('result',{}).get('isError'): raise SystemExit(1)
