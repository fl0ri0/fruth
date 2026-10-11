"""Small real-browser transport fixture; no Fruth runtime or production state.

Run with --output /absolute/isolated/evidence and --chrome /path/to/chrome.
The fixture uses the dashboard's actual Axios tag and transport interceptor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template_string, request
from werkzeug.serving import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
CDP_CLOSE = "const s=new WebSocket(process.argv[1]);let sent=false;s.addEventListener('open',()=>{s.send(JSON.stringify({id:1,method:'Browser.close'}));sent=true;});s.addEventListener('message',e=>console.log(e.data));s.addEventListener('close',()=>process.exit(sent?0:1));s.addEventListener('error',e=>{console.log(JSON.stringify({close_sent:sent,error:String(e.message)}));process.exit(sent?0:1);});setTimeout(()=>process.exit(2),5000);"


class QuietRequests(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


SCRIPT = r'''
const checks = [], blocked = [];
document.addEventListener('securitypolicyviolation', e => blocked.push(e.blockedURI));
function assert(value, message) { if (!value) throw new Error(message); }
async function check(name, fn) { await fn(); checks.push(name); }
(async () => {
  await check('official-version', async () => assert(axios.VERSION === '1.20.0', axios.VERSION));
  await check('json-and-action-header', async () => {
    const r = await axios.post('/api/fixture/echo', {text:'fixture JSON ä', n:7});
    assert(r.status === 200 && r.data.json.text === 'fixture JSON ä' && r.data.json.n === 7, 'JSON');
    assert(r.data.action === '1' && r.data.origin === location.origin, 'JSON action/origin');
  });
  await check('multipart-and-browser-boundary', async () => {
    const form = new FormData(); form.append('prompt', 'fixture multipart');
    form.append('files', new File(['fixture file ä'], 'fixture.txt', {type:'text/plain'}));
    const r = await axios.post('/api/fixture/echo', form, {headers:{'Content-Type':'multipart/form-data'}});
    assert(r.data.action === '1' && r.data.form.prompt === 'fixture multipart', 'multipart action/form');
    assert(r.data.files[0].name === 'fixture.txt' && r.data.files[0].text === 'fixture file ä', 'multipart bytes');
    assert(r.data.content_type.includes('boundary='), 'browser multipart boundary');
  });
  await check('query-parameters-passive-read', async () => {
    const r = await axios.get('/api/fixture/echo', {params:{q:'a & b/+ä', tags:['one','two']}});
    assert(r.data.args.q[0] === 'a & b/+ä' && r.data.args['tags[]'].join(',') === 'one,two', 'query');
    assert(r.data.action === null, 'passive read gained action');
  });
  await check('refresh-query-action', async () => {
    const r = await axios.get('/api/fixture/echo', {params:{refresh:true}});
    assert(r.data.action === '1' && r.data.args.refresh[0] === 'true', 'refresh');
  });
  await check('v1-and-delete-actions', async () => {
    const r = await axios.post('/v1/fixture/echo', {fixture:true});
    const d = await axios.delete('/api/fixture/echo', {params:{key:'delete-fixture'}});
    assert(r.data.action === '1' && d.data.action === '1' && d.data.args.key[0] === 'delete-fixture', 'aliases');
  });
  await check('error-status-and-body', async () => {
    try { await axios.post('/api/fixture/error', {fixture:true}); throw new Error('expected rejection'); }
    catch (e) { assert(axios.isAxiosError(e) && e.response.status === 422 && e.response.data.error_code === 'FIXTURE_REJECTED', 'error contract'); }
  });
  await check('missing-marker-rejected-before-effect', async () => {
    try { await axios.create().post('/api/fixture/echo', {fixture:'unmarked'}); throw new Error('expected rejection'); }
    catch (e) { assert(e.response.status === 403 && e.response.data.error_code === 'HTTP_ACTION_REQUIRED', 'admission'); }
  });
  await check('abort-controller-cancellation', async () => {
    const control = new AbortController();
    const pending = axios.get('/api/fixture/delay', {signal:control.signal});
    setTimeout(() => control.abort(), 20);
    try { await pending; throw new Error('expected cancellation'); }
    catch (e) { assert(axios.isCancel(e) && e.code === 'ERR_CANCELED', 'cancellation'); }
  });
  await check('timeout-error', async () => {
    try { await axios.get('/api/fixture/delay', {timeout:20}); throw new Error('expected timeout'); }
    catch (e) { assert(axios.isAxiosError(e) && e.code === 'ECONNABORTED', 'timeout'); }
  });
  await check('other-origin-does-not-receive-action', async () => {
    const r = await axios.post(FOREIGN + '/fixture/echo', {fixture:'other-origin'});
    assert(r.data.action === null && r.data.origin === location.origin, 'cross-origin marker leak');
  });
  await check('non-api-does-not-receive-action', async () => {
    const r = await axios.post('/fixture/echo', {fixture:'non-api'});
    assert(r.data.action === null, 'non-API marker leak');
  });
  const resources = performance.getEntriesByType('resource').map(r => r.name);
  const axiosLoads = resources.filter(url => new URL(url).pathname.endsWith('/axios.min.js'));
  assert(axiosLoads.length === 1 && new URL(axiosLoads[0]).origin === location.origin, 'local Axios loading');
  assert(!resources.some(url => new URL(url).origin !== location.origin && url.toLowerCase().includes('axios')), 'remote Axios request');
  assert(blocked.length === 0, 'blocked resource attempt');
  await fetch('/fixture/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
    ok:true, checks, resources, blocked, version:axios.VERSION, user_agent:navigator.userAgent, origin:location.origin
  })});
  document.querySelector('pre').textContent = JSON.stringify({ok:true,checks});
})().catch(async error => {
  const result = {ok:false, checks, blocked, error:String(error), stack:error.stack};
  document.querySelector('pre').textContent = JSON.stringify(result);
  await fetch('/fixture/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(result)});
});
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--chrome', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    events, effects, reports, violations = [], [], [], []
    report_ready = threading.Event()
    node = shutil.which('node')
    assert node, 'Existing Node.js runtime required for the local browser close command'
    protected = [ROOT / path for path in ('state','artifacts','logs','.fruth_archiv','model_ports.json')]
    assert not any(out == path or out.is_relative_to(path) for path in protected)

    def deny(event, detail):
        violations.append({'event':event, 'detail':str(detail)})
        raise PermissionError('Isolated browser fixture denied ' + event)

    def guard(event, values):
        if event in {'socket.connect','socket.connect_ex','os.system','os.posix_spawn'}:
            deny(event, values)
        if event == 'socket.bind' and values[1][0] != '127.0.0.1':
            deny(event, values)
        if event == 'subprocess.Popen':
            command = values[1]
            chrome = (Path(values[0]).resolve() == args.chrome.resolve()
                      and f'--user-data-dir={out / "profile"}' in command)
            local_close = (command[:3] == [node, '-e', CDP_CLOSE] and len(command) == 4
                           and command[3].startswith('ws://127.0.0.1:'))
            if not (chrome or local_close):
                deny(event, command)
        if event == 'open' and isinstance(values[0], (str,bytes,os.PathLike)):
            path = Path(os.fsdecode(values[0])).resolve(strict=False)
            if any(path == p or path.is_relative_to(p) for p in protected):
                deny(event, path)
            mode, flags = values[1:3]
            writing = (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
            if writing and path != Path(os.devnull) and not path.is_relative_to(out):
                deny(event, path)

    sys.addaudithook(guard)
    servers, threads = [], []
    app = Flask('axios-browser-fixture', static_folder=str(ROOT / 'static'))
    foreign = Flask('axios-other-origin-fixture', static_folder=None)
    app.before_request(lambda: events.append({'path':request.path, 'method':request.method,
        'action':request.headers.get('X-Fruth-Action'), 'origin':request.headers.get('Origin'),
        'host':request.host}) or None)
    from fruth_server.http_admission_runtime import admit_api_request, apply_api_cors
    app.before_request(admit_api_request)
    app.after_request(apply_api_cors)

    def echo():
        if request.method == 'OPTIONS':
            return '', 204
        effects.append({'path':request.path, 'method':request.method,
                        'action':request.headers.get('X-Fruth-Action')})
        return jsonify(action=request.headers.get('X-Fruth-Action'), origin=request.headers.get('Origin'),
            content_type=request.content_type, json=request.get_json(silent=True), form=dict(request.form),
            args=request.args.to_dict(flat=False), files=[{'name':f.filename,'text':f.read().decode('utf-8')}
                for f in request.files.getlist('files')])

    for path in ['/api/fixture/echo', '/v1/fixture/echo', '/fixture/echo']:
        app.add_url_rule(path, path, echo, methods=['GET','POST','PUT','DELETE','OPTIONS'])
    foreign.add_url_rule('/fixture/echo', 'echo', echo, methods=['POST','OPTIONS'])

    @app.post('/api/fixture/error')
    def error():
        return jsonify(error='Synthetic fixture rejection', error_code='FIXTURE_REJECTED'), 422

    @app.get('/api/fixture/delay')
    def delay():
        time.sleep(.15)
        return jsonify(fixture=True)

    @app.post('/fixture/report')
    def report():
        reports.append(request.get_json())
        report_ready.set()
        return jsonify(recorded=True)

    primary = make_server('127.0.0.1', 0, app, threaded=True, request_handler=QuietRequests)
    other = make_server('127.0.0.1', 0, foreign, threaded=True, request_handler=QuietRequests)
    origin = f'http://127.0.0.1:{primary.server_port}'
    other_origin = f'http://127.0.0.1:{other.server_port}'
    app.config['FRUTH_HTTP_ALLOWED_ORIGINS'] = [origin]

    @foreign.after_request
    def fixture_only_cors(response):
        if request.headers.get('Origin') == origin:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        return response

    @app.get('/fixture')
    def page():
        shell = (ROOT / 'fruth_webUI.html').read_text()
        tags = re.findall(r'<script\s+src="[^"]+"\s*></script>', shell)
        axios_tags = [tag for tag in tags if 'axios' in tag.lower()]
        assert len(axios_tags) == 1
        html = render_template_string(axios_tags[0])
        html += '<script src="/static/ui/request-transport.js"></script><pre>Running</pre>'
        html += '<script>const FOREIGN=' + json.dumps(other_origin) + ';' + SCRIPT + '</script>'
        response = app.make_response(html)
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; script-src 'self' 'unsafe-inline'; connect-src 'self' " + other_origin)
        return response

    for server in [primary, other]:
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start(); threads.append(thread)
    command = [str(args.chrome), '--headless', '--disable-background-networking',
        '--disable-component-update', '--disable-sync', '--disable-extensions',
        '--no-first-run', '--no-default-browser-check', '--no-proxy-server',
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
        f'--user-data-dir={out / "profile"}', f'--log-net-log={out / "network.json"}',
        '--remote-debugging-port=0', origin + '/fixture']
    started = time.monotonic()
    close_result = None
    process = None
    try:
        with (out / 'browser-stdout.log').open('w') as stdout, (out / 'browser-stderr.log').open('w') as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            ready = report_ready.wait(timeout=30)
            debug = (out / 'profile/DevToolsActivePort').read_text().splitlines()
            url = f'ws://127.0.0.1:{int(debug[0])}' + debug[1]
            close_result = subprocess.run([node,'-e',CDP_CLOSE,url], capture_output=True, text=True, timeout=7)
            process.wait(timeout=7)
            assert ready, 'Browser did not finish the fixture within 30 seconds'
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=7)
        for server in servers:
            server.shutdown(); server.server_close()
        for thread in threads: thread.join(timeout=2)
    network = json.loads((out / 'network.json').read_text())
    urls = sorted({e['params']['url'] for e in network['events']
                   if isinstance(e.get('params'), dict) and isinstance(e['params'].get('url'), str)})
    axios_urls = [url for url in urls if 'axios' in url.lower()]
    expected_url = origin + '/static/vendor/axios-1.20.0/axios.min.js'
    receipt = {'completed':True, 'command':command, 'pid':process.pid,
        'exit_code':process.returncode, 'close_exit_code':close_result.returncode,
        'close_diagnostics':close_result.stdout,
        'seconds':time.monotonic()-started, 'source_root':str(ROOT),
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [ROOT/'fruth_webUI.html', ROOT/'static/ui/request-transport.js',
             ROOT/'static/vendor/axios-1.20.0/axios.min.js', Path(__file__).resolve()]},
        'browser_results':reports, 'request_events':events, 'echo_effects':effects,
        'network_axios_urls':axios_urls, 'other_network_urls':[u for u in urls if not u.startswith((origin,other_origin))],
        'isolation':'Separate fixture app with actual admission/CORS owner; in-memory harmless endpoints only; two ephemeral loopback listeners, private browser profile, external DNS denied.',
        'production_operations':False, 'violations':violations}
    (out / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    assert process.returncode == 0 and close_result.returncode == 0 and len(reports) == 1 and reports[0]['ok'], receipt
    assert len(effects) == 8 and not any(e['path'].startswith('/api/') and e['method']=='POST'
                                        and e['action'] is None for e in effects), effects
    assert not violations, violations
    assert axios_urls == [expected_url], axios_urls
    assert len(reports[0]['checks']) == 12
    print(json.dumps({'passed':12,'seconds':receipt['seconds'],'receipt':str(out/'receipt.json')}))


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    main()
