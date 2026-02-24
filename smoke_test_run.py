import subprocess, json, sys, time

# Helpers
def run_cmd(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

# 1) Get container app JSON
ret, out, err = run_cmd('az containerapp show -g theogen-rg-eastus -n theogen-backend -o json')
if ret != 0:
    print('FAILED: az containerapp.show', err)
    sys.exit(2)
app = json.loads(out)
fqdn = app.get('properties', {}).get('latestRevisionFqdn')
if not fqdn:
    print('No FQDN found in containerapp output')
    sys.exit(2)
print('FQDN=', fqdn)

# 2) try to find AZURE_AD_CLIENT_ID in env
env_list = []
try:
    env_list = app['properties']['template']['containers'][0].get('env', [])
except Exception:
    env_list = []
client_id = None
for e in env_list:
    if e.get('name') == 'AZURE_AD_CLIENT_ID':
        client_id = e.get('value')
        break
if not client_id:
    print('AZURE_AD_CLIENT_ID not found in containerapp env; aborting')
    sys.exit(3)
print('AZURE_AD_CLIENT_ID=', client_id)

# 3) Try to get an access token for the app using az cli
for resource in (client_id, f'api://{client_id}'):
    print('Trying az account get-access-token --resource', resource)
    ret, out, err = run_cmd(f'az account get-access-token --resource {resource} --query accessToken -o tsv')
    if ret == 0 and out:
        token = out.strip()
        print('Acquired token via resource', resource)
        break
else:
    print('Failed to obtain access token via az CLI for the app')
    sys.exit(4)

# 4) Run smoke test sequence using requests
try:
    import requests
except Exception as e:
    print('requests not installed in environment:', e)
    sys.exit(5)

base = f'https://{fqdn}/api'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# List projects
r = requests.get(f'{base}/projects', headers=headers, timeout=30)
if r.status_code != 200:
    print('Failed to list projects:', r.status_code, r.text[:500])
    sys.exit(6)
projects = r.json()
if not projects:
    print('No projects found for the authenticated user')
    sys.exit(7)
project_id = projects[0]['id']
print('Using project_id=', project_id)

# POST generate-theory
payload = {}
r = requests.post(f'{base}/projects/{project_id}/generate-theory', json=payload, headers=headers, timeout=30)
print('POST generate-theory ->', r.status_code, r.text[:400])
if r.status_code not in (200,202):
    print('generate-theory failed to enqueue')
    sys.exit(8)
if r.status_code == 200:
    data = r.json()
else:
    data = r.json()

task_id = data.get('task_id')
if not task_id:
    print('No task_id returned:', data)
    sys.exit(9)
print('Task enqueued:', task_id)

# Poll status
status = None
for _ in range(120):
    r = requests.get(f'{base}/projects/{project_id}/generate-theory/status/{task_id}', headers=headers, timeout=30)
    if r.status_code != 200:
        print('Status check failed:', r.status_code, r.text[:300])
        sys.exit(10)
    st = r.json()
    status = st.get('status')
    step = st.get('step')
    print('Status=', status, 'step=', step)
    if status in ('completed','failed'):
        break
    wait = st.get('next_poll_seconds', 5)
    time.sleep(min(10, max(2, wait)))

if status != 'completed':
    print('Task did not complete within timeout, final status=', status)
    sys.exit(11)

# List theories and pick latest
r = requests.get(f'{base}/projects/{project_id}/theories', headers=headers, timeout=30)
if r.status_code != 200:
    print('Failed to list theories:', r.status_code, r.text[:300])
    sys.exit(12)
theories = r.json()
if not theories:
    print('No theories found after task completion')
    sys.exit(13)
# pick newest by created_at
theories_sorted = sorted(theories, key=lambda t: t.get('created_at') or '', reverse=True)
theory_id = theories_sorted[0]['id']
print('Found theory_id=', theory_id)

# Export formats
formats = ['pdf','pptx','xlsx','png']
for fmt in formats:
    print('Requesting export format=', fmt)
    r = requests.post(f'{base}/projects/{project_id}/theories/{theory_id}/export', params={'format':fmt}, headers=headers, timeout=60)
    print(fmt, '->', r.status_code, r.text[:400])
    if r.status_code == 200:
        print(fmt, 'export success')
    else:
        print(fmt, 'export failed')

print('SMOKE TEST COMPLETED')
