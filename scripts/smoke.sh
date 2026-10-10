#!/usr/bin/env bash
# Local smoke uses only a temporary database; BASE_URL targets an existing deployment.
set -euo pipefail
cd "$(dirname "$0")/.."
TASK_TMP=$(mktemp -d "${TMPDIR:-/tmp}/decision-layer-smoke.XXXXXX")
SERVER_PID=''
cleanup() { if [[ -n "$SERVER_PID" ]]; then kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; fi; rm -rf "$TASK_TMP"; }
trap cleanup EXIT
trap 'echo "FAIL smoke step at line $LINENO" >&2; if [[ -f "$TASK_TMP/server.log" ]]; then cat "$TASK_TMP/server.log" >&2; fi' ERR
if [[ -z "${BASE_URL:-}" ]]; then
  BASE_URL=http://127.0.0.1:8018
  export PROOFPATH_DATA_DIR="$TASK_TMP/data" PROOFPATH_ENABLE_LLM=0 PROOFPATH_OPERATOR_TOKEN=smoke-local-token PROOFPATH_DEMO_MODE=local
  uv run python -m uvicorn sv.proofpath.app:app --host 127.0.0.1 --port 8018 >"$TASK_TMP/server.log" 2>&1 &
  SERVER_PID=$!
fi
export BASE_URL TASK_TMP
for i in {1..200}; do if curl -fsS "$BASE_URL/health" >"$TASK_TMP/health.json" 2>/dev/null 2>/dev/null; then break; fi; if [[ -n "$SERVER_PID" ]] && ! kill -0 "$SERVER_PID" 2>/dev/null; then cat "$TASK_TMP/server.log" >&2; exit 1; fi; sleep .1; done
uv run python - <<'PY'
import json, os, subprocess, time
from pathlib import Path
base=os.environ['BASE_URL'].rstrip('/')
tmp=Path(os.environ['TASK_TMP']); cookie=tmp/'cookies'
def request(path, payload=None, operator=False, outsider=False):
    cmd=['curl','--fail-with-body','-sS','-b',str(tmp/'outsider' if outsider else cookie),'-c',str(tmp/'outsider' if outsider else cookie),base+path]
    if payload is not None: cmd += ['-H','Content-Type: application/json','-d',json.dumps(payload)]
    if operator: cmd += ['-H','x-operator-token: '+os.environ.get('PROOFPATH_OPERATOR_TOKEN','')]
    response=json.loads(subprocess.check_output(cmd))
    assert not response.get('stub'), 'stub response: '+path
    return response['data']
health=request('/health'); assert health['ready']; print('PASS health')
created=request('/api/v1/evaluations',{'preset_id':'eu_technical'})
eid=created['evaluation_id']; bid=created['brief']['id']; prefix='/api/v1/evaluations/'+eid
before=request(prefix+'/confirm',{'brief_version_id':bid})
assert next(p for p in before['comparison']['products'] if p['product_id']=='flowbridge')['decision']=='needs_verification'
print('PASS create and confirm')
payload={'brief_version_id':bid,'idempotency_key':'smoke-once'}
run=request(prefix+'/runs',payload); assert request(prefix+'/runs',payload)['id']==run['id']
conflict=subprocess.check_output(['curl','-sS','-b',str(cookie),'-o',os.devnull,'-w','%{http_code}','-H','Content-Type: application/json','-d',json.dumps({**payload,'brief_version_id':'different'}),base+prefix+'/runs']).decode()
assert conflict=='409'; print('PASS idempotency and payload conflict')
for _ in range(200):
    result=request('/api/v1/runs/'+run['id'])
    if result['run']['state']=='closed': break
    time.sleep(.05)
assert result['run']['state']=='closed' and result['run']['outcome']=='passed'
assert len(result['results'])==4 and all(t['status']=='pass' for t in result['results']); print('PASS four live tests')
workspace=request(prefix+'/workspace'); fb=next(p for p in workspace['comparison']['products'] if p['product_id']=='flowbridge')
assert fb['decision']=='needs_verification'
assert next(f for f in fb['findings'] if f['requirement_key']=='recovery_demonstrated')['basis']=='demonstrated'
report=request(prefix+'/reports',{'brief_version_id':bid,'comparison_snapshot_id':workspace['comparison']['id']}); print('PASS demonstrated recovery and report')
if os.environ.get('PROOFPATH_OPERATOR_TOKEN'):
    update=request('/api/v1/demo/source-update',{},True)
    assert request(prefix+'/workspace')['comparison']['products']==workspace['comparison']['products']
    request('/api/v1/sources/'+update['source_version']['id']+'/review',{'decision':'approved'},True)
    assert request('/api/v1/reports/'+report['id'])==report
    assert any(e['type']=='comparison_updated' for e in request(prefix+'/events')); print('PASS approved update and frozen history')
else: print('SKIP operator update: set PROOFPATH_OPERATOR_TOKEN for deployed checks')
for path in [prefix+'/workspace','/api/v1/reports/'+report['id'],'/api/v1/runs/'+run['id'],'/api/v1/artifacts/'+result['artifacts'][0]['id']]:
    code=subprocess.check_output(['curl','-sS','-o',os.devnull,'-w','%{http_code}',base+path]).decode()
    assert code=='404',(path,code)
assert subprocess.check_output(['curl','-sS','-o',os.devnull,'-w','%{http_code}','-H','Content-Type: application/json','-d','{}',base+'/api/v1/demo/source-update']).decode()=='403'
print('PASS isolation and operator authorization')
if os.environ.get('PROOFPATH_DATA_DIR'):
    import sqlite3
    db=sqlite3.connect(Path(os.environ['PROOFPATH_DATA_DIR'])/'proofpath.db')
    (tmp/'counts.json').write_text(json.dumps({table: db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ['sources','claims','evaluations','events']}))
(tmp/'state.json').write_text(json.dumps({'eid':eid,'report':report,'cookies':str(cookie)}))
PY
if [[ -n "$SERVER_PID" ]]; then
  kill "$SERVER_PID"; wait "$SERVER_PID" || true
  uv run python -m uvicorn sv.proofpath.app:app --host 127.0.0.1 --port 8018 >"$TASK_TMP/restart.log" 2>&1 &
  SERVER_PID=$!
  for i in {1..200}; do if curl -fsS "$BASE_URL/health" >/dev/null 2>/dev/null; then break; fi; if [[ -n "$SERVER_PID" ]] && ! kill -0 "$SERVER_PID" 2>/dev/null; then cat "$TASK_TMP/server.log" >&2; exit 1; fi; sleep .1; done
  uv run python - <<'PY'
import json, os, subprocess, sqlite3
from pathlib import Path
p=Path(os.environ['TASK_TMP']); state=json.loads((p/'state.json').read_text())
url=os.environ['BASE_URL']+'/api/v1/reports/'+state['report']['id']
response=json.loads(subprocess.check_output(['curl','-fsS','-b',state['cookies'],url]))
assert response['data']==state['report']
# Approved and superseded versions retain unique ids across restart.
db=sqlite3.connect(Path(os.environ['PROOFPATH_DATA_DIR'])/'proofpath.db')
counts=json.loads((p/'counts.json').read_text())
assert {table: db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in counts}==counts
print('PASS restart preserves report/history and does not duplicate fixtures')
PY
fi
