"""Isolierte Browser/GitHub-Antworten. Schreibt niemals in das echte Repository."""
import base64
import copy
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
CHROMIUM=os.getenv('PW_CHROMIUM_PATH','/usr/bin/chromium')
TOKEN='t'*40
REPO='SolarBergler/solarprognose_1'
# Feste Wetterdaten: Tests bleiben unabhängig von täglichen Archiv-Commits reproduzierbar.
def fixture_weather(path):
    return json.loads(subprocess.check_output(['git','show','e94f948943a1d7593bcec1e7d777cec29b853763:'+path],cwd=ROOT,text=True))


class Server:
    def __init__(self):
        self.files={p:(ROOT/p).read_text() for p in ['anlagenkonfiguration.json','horizontprofil.json','nahverschattung.json']}
        self.pages=self.files.copy();self.head='a'*40;self.requests=[];self.trees=[];self.stage=[]
        self.weather=fixture_weather('prognosen/letzter_wetterstand.json')['weather']
        self.auto_publish=True;self.offline=False;self.weather_fail=False;self.denied=False;self.errors=[]
    def release(self):self.pages=self.files.copy()
    def route(self,route):
        req=route.request;url=urlsplit(req.url);path=url.path.lstrip('/') or 'index.html'
        self.requests.append({'url':req.url,'method':req.method})
        headers={'Access-Control-Allow-Origin':'https://solar.test','Access-Control-Allow-Headers':'Authorization,Content-Type,Accept,X-GitHub-Api-Version','Access-Control-Allow-Methods':'GET,POST,PATCH,OPTIONS'}
        def respond(value,status=200):
            route.fulfill(status=status,content_type='application/json',headers=headers,body=value if isinstance(value,str) else json.dumps(value))
        if req.method=='OPTIONS':respond('',204);return
        if url.netloc=='api.github.com':
            assert req.headers.get('authorization')=='Bearer '+TOKEN
            if self.denied:respond({},403);return
            p=url.path.replace('/repos/'+REPO,'');body=json.loads(req.post_data or '{}')
            if p=='/git/ref/heads/main':respond({'object':{'sha':self.head}})
            elif p.startswith('/contents/'):
                name=p[len('/contents/'):];respond({'encoding':'base64','content':base64.b64encode(self.files[name].encode()).decode()})
            elif p.startswith('/git/commits/') and req.method=='GET':respond({'tree':{'sha':'b'*40}})
            elif p=='/git/trees':
                self.stage=body['tree'];self.trees.append(body['tree']);respond({'sha':'c'*40})
            elif p=='/git/commits':
                self.parent=body['parents'];respond({'sha':hashlib.sha1(req.post_data.encode()).hexdigest()})
            elif p=='/git/refs/heads/main':
                assert body['force'] is False
                if self.parent!=[self.head]:respond({},422);return
                self.files.update({f['path']:f['content'] for f in self.stage});self.head=body['sha']
                if self.auto_publish:self.release()
                respond({'object':{'sha':self.head}})
            else:raise AssertionError('Unexpected GitHub route '+p)
            return
        if url.netloc=='api.open-meteo.com':
            if self.offline or self.weather_fail:respond({'error':True,'reason':'test unavailable'},400)
            else:respond(self.weather)
        elif path in self.pages:
            if self.offline:route.abort()
            else:respond(self.pages[path])
        elif path=='prognosen/dwd_wetterstand.json' and (self.offline or self.weather_fail=='cached'):respond({},404)
        elif path in ['prognosen/dwd_wetterstand.json','prognosen/letzter_wetterstand.json']:
            doc=fixture_weather(path);doc['capturedAt']='2026-11-05T17:55:00+00:00'
            if 'issueTime' in doc:doc['issueTime']='2026-11-05T15:00:00.000Z'
            respond(doc)
        elif (ROOT/path).is_file():route.fulfill(path=str(ROOT/path))
        else:respond({},404)

def open_page(browser,server,width=1365,legacy=None,storage=None,html=None,at=None):
    context=browser.new_context(timezone_id='Europe/Berlin',locale='de-DE',viewport={'width':width,'height':1000},**({'storage_state':storage} if storage else {}))
    page=context.new_page();page.clock.install(time=at or datetime(2026,11,5,18,tzinfo=timezone.utc));errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    if legacy is not None:context.add_init_script('localStorage.setItem("schliersee-settings-v1",'+json.dumps(json.dumps(legacy))+');')
    def handler(route):
        if html and urlsplit(route.request.url).path=='/index.html':route.fulfill(content_type='text/html',body=html)
        else:server.route(route)
    page.route('**/*',handler);page.goto('https://solar.test/index.html')
    return context,page,errors

def ready(page):page.wait_for_function('SolarApp?.getCentralConfiguration()?.ready&&SolarApp.getCalculated().length>1900')
def enter_key(page):
    page.wait_for_function('document.getElementById("centralPublishDialog").open')
    page.locator('#githubWriteKey').fill(TOKEN);page.locator('#confirmCentralPublish').click()
def complete(page):page.wait_for_function('!document.getElementById("centralPublishDialog").open')
def no_key_stored(page):
    assert page.locator('#githubWriteKey').input_value()==''
    assert not page.evaluate('(token)=>Object.values(localStorage).some(v=>v.includes(token))',TOKEN)
    assert TOKEN not in page.evaluate('JSON.stringify(SolarApp.getState())')
