"""Zentrale Konfiguration: Browser-, Veröffentlichungs- und Archivierungsregressionen."""
import copy
import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_fixtures import ROOT,CHROMIUM,TOKEN,Server,open_page,ready,enter_key,complete,no_key_stored,fixture_weather

def plant_state(c):
    return {'locationName':c['location']['name'],'lat':c['location']['latitude'],'lon':c['location']['longitude'],'roofHeight':c['location']['roofHeightM'],
            'losses':c['systemLossesPercent'],'albedo':c['albedo'],'panels':[{k:v for k,v in p.items() if k!='geo'} for p in c['panels']],
            'panelGeometry':[p['geo'] for p in c['panels']],'inverters':c['inverters']}

def run_regressions():
    original_config=(ROOT/'anlagenkonfiguration.json').read_text()
    config=json.loads(original_config);expected_hash=hashlib.sha256(original_config.encode()).hexdigest()
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path=CHROMIUM,args=['--no-sandbox'])
        server=Server()
        # Dieselben veröffentlichten Parameter wie vor der Umstellung: numerisch identische Physik.
        baseline=subprocess.check_output(['git','show','e94f948943a1d7593bcec1e7d777cec29b853763:index.html'],cwd=ROOT,text=True)
        old_context,old,errors=open_page(b,server,legacy=plant_state(config),html=baseline)
        old.wait_for_function('SolarApp?.getCalculated().length>1900')
        old_rows=old.evaluate('SolarApp.getCalculated().map(r=>[r.ts,r.power,r.base])')
        assert not errors,errors;old_context.close()
        a,pa,ea=open_page(b,server,legacy={'locationName':'Veraltet A','lat':0,'lon':0,'losses':50,'albedo':.9,'panels':[]})
        z,pz,ez=open_page(b,server,width=390,legacy={'locationName':'Veraltet B','lat':1,'lon':1,'losses':0,'panels':[{'name':'Falsch','kwp':1000}]})
        ready(pa);ready(pz)
        for page in [pa,pz]:
            assert page.evaluate('SolarApp.getCentralConfiguration().configurationHash')==expected_hash
            assert page.evaluate('SolarApp.getState().panels.length')==len(config['panels'])
        assert pa.evaluate('JSON.stringify(SolarApp.getState())')==pz.evaluate('JSON.stringify(SolarApp.getState())')
        new_rows=pa.evaluate('SolarApp.getCalculated().map(r=>[r.ts,r.power,r.base])')
        assert len(new_rows)==len(old_rows)
        assert all(abs(x-y)<1e-8 for new,old in zip(new_rows,old_rows) for x,y in zip(new,old))
        assert not ea+ez,ea+ez
        # Frische Browserkopie darf keine eigenständige lokale Anlagenkonfiguration erzeugen.
        assert json.loads(pa.evaluate('localStorage.getItem("schliersee-settings-v1")'))['lat']==0
        cache=a.storage_state();a.close();z.close()
        server.offline=True
        c,offline,errors=open_page(b,server,storage=cache);ready(offline)
        assert not offline.evaluate('SolarApp.getCentralConfiguration().online')
        assert offline.evaluate('SolarApp.getCentralConfiguration().configurationHash')==expected_hash
        assert 'nicht aktuell bestätigt' in offline.locator('#centralSource').inner_text()
        assert not errors,errors;c.close()
        c,empty,errors=open_page(b,server,legacy=plant_state(config))
        empty.wait_for_function('document.getElementById("startupNotice").classList.contains("warning")')
        assert not empty.evaluate('SolarApp.getCentralConfiguration().ready')
        assert empty.evaluate('SolarApp.getCalculated().length')==0
        assert empty.locator('#openPanels').is_disabled()
        server.offline=False;empty.locator('#refresh').click();ready(empty)
        assert empty.locator('#openPanels').is_enabled();c.close();server.offline=True
        # Auch ein manipulierter Cache ist kein gültiger Ersatz für einen zentralen Stand.
        tampered=copy.deepcopy(cache)
        for origin in tampered['origins']:
            for item in origin['localStorage']:
                if item['name']=='solar-central-bundle-v1':
                    raw=json.loads(item['value']);changed=json.loads(raw['configText']);changed['systemLossesPercent']=49
                    raw['configText']=json.dumps(changed);item['value']=json.dumps(raw)
        c,broken,errors=open_page(b,server,storage=tampered)
        broken.wait_for_function('document.getElementById("startupNotice").classList.contains("warning")')
        assert not broken.evaluate('SolarApp.getCentralConfiguration().ready');c.close()
        print('OK: gleiche Parameter auf unabhängigen Browsern, alte lokale Einstellungen ignoriert, Offline-Cache und Sperre ohne gültiges Paket.')
        print('OK: Leistungsberechnung numerisch unverändert gegenüber V12.7.2 bei identischen veröffentlichten Parametern.')
        for kind,provider in [(True,'dwd'),('cached','cached')]:
            fallback_server=Server();fallback_server.weather_fail=kind
            c,page,errors=open_page(b,fallback_server)
            # MOSMIX beginnt im Test am Nachmittag: der erste Tag ist nur teilweise enthalten.
            page.wait_for_function('SolarApp?.getCentralConfiguration()?.ready&&SolarApp.getCalculated().length>1700')
            assert page.evaluate('SolarApp.getWeatherDiagnostics().source')==provider
            assert not errors,errors;c.close()
        print('OK: Open-Meteo, DWD-MOSMIX und GitHub-Wettercache bleiben nutzbar.')
        b.close()
    run_archive_regression()

def run_archive_regression():
    # Vollständige reale App, aber alle Dateien und Schreibvorgänge in einem temporären Verzeichnis.
    html=(ROOT/'index.html').read_text()
    resources={p:json.loads((ROOT/p).read_text()) for p in ['anlagenkonfiguration.json','horizontprofil.json','nahverschattung.json','prognosen/dwd_wetterstand.json']}
    weather=fixture_weather('prognosen/letzter_wetterstand.json')['weather']
    raw={p:(ROOT/p).read_text() for p in resources}
    prefix=r'''<script>(()=>{
    window.__fakeStore={};Object.defineProperty(window,'localStorage',{value:{getItem:k=>window.__fakeStore[k]??null,setItem:(k,v)=>window.__fakeStore[k]=String(v),removeItem:k=>delete window.__fakeStore[k]}});
    const RealDate=Date;window.Date=class extends RealDate {constructor(...a){super(...(a.length?a:[1793901600000]))}static now(){return 1793901600000}};
    const files=%s,weather=%s;window.fetch=async url=>{
      const key=String(url).replace(/^\.\//,'').split('?')[0],doc=String(url).includes('api.open-meteo.com')?JSON.stringify(weather):files[key];
      return {ok:doc!==undefined,status:doc===undefined?404:200,json:async()=>JSON.parse(doc),text:async()=>doc};};
    })();</script><!-- BEFORE_APP -->'''%(json.dumps(raw),json.dumps(weather))
    html=html.replace('<script src="./inverters.js?v=12.7"></script>',prefix+'<script>'+(ROOT/'inverters.js').read_text()+'</script>')
    html=html.replace('<script src="./central-config.js?v=12.8.2"></script>','<script>'+(ROOT/'central-config.js').read_text()+'</script>')
    # localhost ist ein Secure Context und bietet die echte WebCrypto-Prüfung auch ohne Internet.
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);(root/'scripts').mkdir();shutil.copy(ROOT/'scripts/archiviere_prognose.py',root/'scripts/archiviere_prognose.py')
        shutil.copy(ROOT/'anlagenkonfiguration.json',root/'anlagenkonfiguration.json')
        shutil.copytree(ROOT/'prognosen',root/'prognosen')
        protected={p:p.read_bytes() for p in (root/'prognosen').rglob('*.json') if p.name not in ['letzter_wetterstand.json','browser_prognosezustand_v12_8.json']}
        (root/'fixture.html').write_text(html)
        runner='''import importlib.util,datetime,sys,os
spec=importlib.util.spec_from_file_location('archive',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Clock(datetime.datetime):
    @classmethod
    def now(cls,tz=None):return datetime.datetime.fromtimestamp(1793901600,tz)
m.datetime=Clock
if os.getenv('TEST_CENTRAL_MISMATCH'):
    from playwright.sync_api import Page
    original_wait=Page.wait_for_function
    def bounded_wait(self,*args,**kwargs):
        kwargs['timeout']=3000
        return original_wait(self,*args,**kwargs)
    Page.wait_for_function=bounded_wait
sys.exit(m.main())
'''
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(root)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        env={**os.environ,'PV_SITE_URL':f'http://127.0.0.1:{server.server_port}/fixture.html','PW_CHROMIUM_PATH':CHROMIUM,'GITHUB_EVENT_NAME':'workflow_dispatch'}
        env.pop('PV_TEST_HTML_FILE',None)
        try:
            subprocess.run(['python','-u','-c',runner,str(root/'scripts/archiviere_prognose.py')],env=env,check=True,timeout=150)
            assert all(p.read_bytes()==data for p,data in protected.items())
            new=next(p for p in (root/'prognosen').glob('*/*.json') if p not in protected)
            d=json.loads(new.read_text());expected=hashlib.sha256(raw['anlagenkonfiguration.json'].encode()).hexdigest()
            assert d['modelVersion']=='V12.8.3'
            assert d['centralConfiguration']['configurationHash']==expected
            assert d['centralConfiguration']['online']
            assert d['centralConfiguration']['configuration']==resources['anlagenkonfiguration.json']
            assert (root/'prognosen/browser_prognosezustand_v12_8.json').is_file()
            # Ein neuer GitHub-Stand mit noch alter Pages-Datei darf keinen Snapshot erzeugen.
            new.unlink();(root/'anlagenkonfiguration.json').write_text(raw['anlagenkonfiguration.json']+' ')
            blocked=subprocess.run(['python','-u','-c',runner,str(root/'scripts/archiviere_prognose.py')],env={**env,'TEST_CENTRAL_MISMATCH':'1'},capture_output=True,text=True,timeout=20)
            assert blocked.returncode!=0,blocked.stdout
            assert expected in blocked.stdout and "'online': True" in blocked.stdout,blocked.stdout
            assert not new.exists()
            assert all(p.read_bytes()==data for p,data in protected.items())
        finally:server.shutdown();server.server_close();thread.join()
    print('OK: Archivierung verwendet den zentralen Hash und die vollständige Konfiguration; alte Pages-Stände werden blockiert und alle bisherigen Prognosedateien bleiben unverändert.')

def run_publication_tests():
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path=CHROMIUM,args=['--no-sandbox'])
        server=Server();server.auto_publish=False
        a,pa,ea=open_page(b,server);z,pz,ez=open_page(b,server,width=390);ready(pa);ready(pz)
        before=pa.evaluate('JSON.stringify(SolarApp.getState())');initial=json.loads(server.files['anlagenkonfiguration.json']);old_revision=initial['revision']
        old_power=initial['panels'][0]['kwp'];changed=round(old_power+.025,3)
        pa.locator('#openPanels').click();pa.locator('[data-p="kwp"]').first.fill(str(changed));pa.locator('#applyPanels').click()
        assert pa.evaluate('JSON.stringify(SolarApp.getState())')==before
        enter_key(pa);pa.wait_for_function('publishJob?.result?.commitSha')
        no_key_stored(pa)
        assert pa.evaluate('JSON.stringify(SolarApp.getState())')==before
        assert [f['path'] for f in server.trees[-1]]==['anlagenkonfiguration.json']
        server.release();pa.clock.fast_forward(5000);complete(pa)
        assert pa.evaluate('SolarApp.getState().panels[0].kwp')==changed
        assert pa.evaluate('SolarApp.getCentralConfiguration().revision')==old_revision+1
        # Zweites Gerät ist veraltet: ein Schreibversuch darf die neue GitHub-Version nicht ersetzen.
        trees=len(server.trees)
        pz.locator('#openPanels').click();pz.locator('[data-p="kwp"]').first.fill(str(changed+.1));pz.locator('#applyPanels').click();enter_key(pz)
        pz.wait_for_function('document.getElementById("centralPublishStatus").textContent.includes("anderes Gerät")')
        assert len(server.trees)==trees;no_key_stored(pz)
        assert pz.evaluate('SolarApp.getState().panels[0].kwp')==old_power
        pz.locator('#cancelCentralPublish').click();pz.locator('#cancelPanels').click();pz.reload();ready(pz)
        assert pz.evaluate('SolarApp.getCentralConfiguration().configurationHash')==pa.evaluate('SolarApp.getCentralConfiguration().configurationHash')
        assert pz.evaluate('JSON.stringify(SolarApp.getState())')==pa.evaluate('JSON.stringify(SolarApp.getState())')
        assert not ea+ez,ea+ez;a.close();z.close()
        print('OK: tatsächlicher zentraler Speicherweg, Wartezustand vor Pages, identische Geräte nach Reload, Konfliktschutz und kein gespeicherter Zugriffsschlüssel.')

        server=Server();server.auto_publish=False
        c,page,errors=open_page(b,server);ready(page);old=page.evaluate('JSON.stringify(SolarApp.getState())')
        page.locator('#openPanels').click();page.locator('#addPanel').click()
        i=len(initial['panels'])
        for field,value in [('name','Zusatzfeld'),('kwp','1'),('az','165'),('tilt','30')]:page.locator(f'[data-i="{i}"][data-p="{field}"]').fill(value)
        page.locator(f'[data-i="{i}"][data-p="inverterId"]').select_option(initial['inverters'][0]['id'])
        for field,value in initial['panels'][0]['geo'].items():
            if field in ['latitude','longitude','width_m','depth_m','lower_edge_height_m','upper_edge_height_m']:page.locator(f'[data-i="{i}"][data-geo="{field}"]').fill(str(value))
        page.locator('#applyPanels').click();assert page.locator('#profileWizard').is_visible()
        page.evaluate('''()=>{
          const near=CENTRAL.clone(centralBundle.near),far=CENTRAL.clone(centralBundle.horizon);
          near.id='central-profile-test';near.panelProfiles.push(CENTRAL.clone(near.panelProfiles[0]));
          near.config={panels:pendingPlant.panels.map((p,i)=>({...p,geo:pendingPlant.panelGeometry[i]})),inverters:pendingPlant.inverters};
          far.generatedAt=new Date().toISOString();generatedFiles={doc:near,horizonDoc:far};
          document.getElementById('verifyProfiles').classList.remove('hidden');
        }''')
        page.locator('#verifyProfiles').click();enter_key(page);page.wait_for_function('publishJob?.result?.commitSha')
        assert sorted(f['path'] for f in server.trees[-1])==['anlagenkonfiguration.json','horizontprofil.json','nahverschattung.json']
        server.pages['anlagenkonfiguration.json']=server.files['anlagenkonfiguration.json']
        page.clock.fast_forward(5000)
        assert page.evaluate('JSON.stringify(SolarApp.getState())')==old
        server.release();page.clock.fast_forward(5000);complete(page)
        assert not page.locator('#profileWizard').is_visible()
        assert page.evaluate('SolarApp.getState().panels.length')==len(initial['panels'])+1
        no_key_stored(page);assert not errors,errors;c.close()
        print('OK: Konfiguration und neue Profile werden in einem Commit gespeichert; unvollständige Pages-Veröffentlichung wird nicht aktiviert.')

        server=Server();server.auto_publish=False
        c,page,errors=open_page(b,server);ready(page)
        before=page.evaluate('JSON.stringify(SolarApp.getState())')
        page.locator('#openPanels').click();page.locator('[data-p="kwp"]').first.fill(str(changed));page.locator('#applyPanels').click();enter_key(page)
        page.wait_for_function('publishJob?.waitController')
        page.clock.fast_forward(301000)
        page.wait_for_function('document.getElementById("confirmCentralPublish").textContent.includes("erneut prüfen")')
        assert 'auf der Website' not in page.locator('#centralSource').inner_text()
        assert page.evaluate('JSON.stringify(SolarApp.getState())')==before
        trees=len(server.trees);server.release();page.locator('#confirmCentralPublish').click();complete(page)
        assert len(server.trees)==trees
        assert page.evaluate('SolarApp.getState().panels[0].kwp')==changed
        # Warten beenden lässt die bestätigte GitHub-Veröffentlichung bestehen, aktiviert sie aber nicht lokal.
        server.auto_publish=False
        page.locator('#openPanels').click();page.locator('[data-p="kwp"]').first.fill(str(changed+.01));page.locator('#applyPanels').click();enter_key(page)
        page.wait_for_function('publishJob?.waitController');page.locator('#cancelCentralPublish').click();complete(page)
        assert page.evaluate('SolarApp.getState().panels[0].kwp')==changed
        assert 'Veröffentlichung auf der Website steht noch aus' in page.locator('#centralSource').inner_text()
        server.release();page.reload();ready(page)
        assert page.evaluate('SolarApp.getState().panels[0].kwp')==changed+.01
        no_key_stored(page);assert not errors,errors;c.close()
        print('OK: fünfminütiges Warten, Wiederholungsprüfung ohne zweiten Commit und Abbruch mit ehrlichem Veröffentlichungsstatus.')

        server=Server();server.denied=True
        c,page,errors=open_page(b,server,width=390);ready(page)
        before=page.evaluate('JSON.stringify(SolarApp.getState())')
        page.locator('#openPanels').click();page.locator('[data-p="kwp"]').first.fill(str(changed));page.locator('#applyPanels').click();enter_key(page)
        page.wait_for_function('document.getElementById("centralPublishStatus").textContent.includes("keinen Schreibzugriff")')
        assert page.evaluate('JSON.stringify(SolarApp.getState())')==before
        assert page.evaluate('document.getElementById("centralPublishDialog").scrollWidth<=document.getElementById("centralPublishDialog").clientWidth+1')
        no_key_stored(page);assert not errors,errors;c.close();b.close()
        print('OK: fehlende Berechtigung wird verständlich angezeigt; keine lokale Aktivierung und kein Token im Speicher.')

if __name__=='__main__':
    run_regressions();run_publication_tests()
