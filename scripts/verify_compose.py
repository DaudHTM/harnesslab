"""Real Compose API/worker/grading smoke test, without browser automation.

Uses a unique project namespace and removes only its own test containers and
volumes. This does not prove visual rendering or browser interaction.
"""
import json
import os
import subprocess
import sys
import time
import uuid
import argparse
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def verify():
    project="harnesslab-smoke-"+uuid.uuid4().hex[:10]
    env={**os.environ,"HARNESSLAB_HTTP_PORT":"18080"}
    compose=["docker","compose","-f",str(ROOT/"compose.yaml"),"-p",project]
    started=time.monotonic()
    output=ROOT/"docs/evidence/compose.json"
    try:
        subprocess.run(compose+["up","-d","--build"],cwd=ROOT,env=env,check=True)
        # Talk to the API inside the isolated test container; do not access or
        # automate the user's browser or the running desktop dashboard.
        code="""import json,time,urllib.request
base='http://127.0.0.1:8000'
def get(path):
    with urllib.request.urlopen(base+path,timeout=10) as r:return json.load(r)
request=urllib.request.Request(base+'/api/experiments',data=json.dumps({'name':'Compose smoke','tasks':['tag-normalization'],'configs':[{'name':'baseline'}]}).encode(),headers={'Content-Type':'application/json'},method='POST')
with urllib.request.urlopen(request,timeout=10) as r:exp=json.load(r)['id']
for attempt in range(90):
    detail=get('/api/experiments/'+exp)
    run=detail['runs'][0]
    if run['status'] not in ['queued','running']:break
    time.sleep(1)
assert run['status']=='solved',run
events=get('/api/runs/'+run['id']+'/events')
assert {'tools_discovered','grading','attempt_finished'} <= {e['kind'] for e in events}
assert all(e['schema_version']==1 for e in events)
patch=get('/api/runs/'+run['id']+'/patch')['patch']
assert '.strip().lower()' in patch
with urllib.request.urlopen(base+'/',timeout=10) as r:html=r.read().decode()
assert 'HarnessLab' in html and '/assets/' in html
print(json.dumps({'experiment':exp,'run':run['id'],'outcome':run['status'],'events':len(events),'static_bundle_served':True,'browser_verified':False}))
"""
        result=subprocess.run(compose+["exec","-T","api","python","-c",code],cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=120)
        evidence=json.loads(result.stdout.strip().splitlines()[-1])
        output.write_text(json.dumps({"created":datetime.now(timezone.utc).isoformat(),"project":project,"duration_seconds":time.monotonic()-started,**evidence},indent=2)+"\n")
        print(output,flush=True)
    except subprocess.CalledProcessError:
        subprocess.run(compose+["logs","--tail","80"],cwd=ROOT,env=env)
        raise
    finally:
        subprocess.run(compose+["down","--volumes","--remove-orphans"],cwd=ROOT,env=env,check=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--private-engine",action="store_true",help="Use the project-local Lima engine without changing global Docker contexts.")
    args=parser.parse_args()
    if args.private_engine:
        from scripts.local_containers import environment
        os.environ.update(environment())
    verify()
