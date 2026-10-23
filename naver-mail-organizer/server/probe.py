"""Read-only local diagnostics. verify reads {\"handles\":[...]} JSON from stdin."""
import json
import os
import sys
import urllib.request

mode = sys.argv[1] if len(sys.argv) > 1 else 'status'
if mode not in ('status', 'tools', 'history', 'verify'):
    raise SystemExit('Usage: python /app/probe.py [status|tools|history|verify]')
if mode == 'tools':
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
else:
    names = {'status': 'naver_status', 'history': 'naver_get_move_results', 'verify': 'naver_verify_moves'}
    arguments = json.load(sys.stdin) if mode == 'verify' else ({'needs_attention': True} if mode == 'history' else {})
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': names[mode], 'arguments': arguments}}
request = urllib.request.Request('http://127.0.0.1:8080/mcp', data=json.dumps(payload).encode(), headers={
    'Authorization': 'Bearer ' + os.environ['MCP_API_TOKEN'], 'Content-Type': 'application/json', 'Accept': 'application/json'})
try:
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response)
except Exception as exc:
    raise SystemExit('Diagnostic failed: ' + type(exc).__name__)
print(json.dumps(result, ensure_ascii=False, indent=2))
if result.get('error') or result.get('result', {}).get('isError'):
    raise SystemExit(1)
