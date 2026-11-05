"""Regressionen mit Chromium: python tests/test_browser.py (playwright erforderlich).

Keine Live-Wetterabfragen und keine Änderungen an Repository-Archivdateien.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEATHER = json.loads((ROOT / 'prognosen/letzter_wetterstand.json').read_text())['weather']
HTML = (ROOT / 'index.html').read_text()
CHROMIUM = os.getenv('PW_CHROMIUM_PATH', '/usr/bin/chromium')
LEGACY_KEY = 'schliersee-forecast-progressive-v11'
NEW_KEY = 'schliersee-forecast-progressive-v12.7'
LEGACY = '{"version":2,"days":{"original":{"unchanged":true}}}'
fixed_now = 1793901600000  # 2026-11-05 18:00 UTC; vollständig vorhandener Wetter-Teststand.


def browser_page(browser, html=HTML, settings=None, viewport=None, failure=None):
    context = browser.new_context(timezone_id='Europe/Berlin', locale='de-DE',
                                  viewport=viewport or {'width': 1365, 'height': 1100})
    context.add_init_script('''window.__now=%d; const RealDate=Date;
      window.Date=class extends RealDate {constructor(...a){super(...(a.length?a:[window.__now]))} static now(){return window.__now}};
      localStorage.setItem(%s,%s);
    ''' % (fixed_now, json.dumps(LEGACY_KEY), json.dumps(LEGACY)))
    if settings is not None:
        context.add_init_script('localStorage.setItem("schliersee-settings-v1",'+json.dumps(json.dumps(settings))+');')
    requests, errors = [], []
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))

    def route(request_route):
        url = request_route.request.url
        requests.append(url)
        path = urlsplit(url).path.lstrip('/') or 'index.html'
        if 'api.open-meteo.com' in url:
            if failure:
                request_route.fulfill(status=400, content_type='application/json', body='{"error":true,"reason":"test unavailable"}')
            else:
                request_route.fulfill(content_type='application/json', body=json.dumps(WEATHER))
        elif path == 'index.html':
            request_route.fulfill(content_type='text/html', body=html)
        elif failure == 'github' and path == 'prognosen/dwd_wetterstand.json':
            request_route.fulfill(status=404, body='not found')
        elif (ROOT / path).is_file():
            request_route.fulfill(path=str(ROOT / path))
        else:
            request_route.fulfill(status=404, body='not found')

    page.route('**/*', route)
    page.goto('https://solar.test/index.html')
    page.wait_for_function("window.SolarApp?.getHorizon()?.length===720 && window.SolarApp?.getNearData() && window.SolarApp.groupDays().length>=7")
    assert not errors, errors
    return context, page, requests, errors


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROMIUM, args=['--no-sandbox'])
    # Altmodell direkt aus Git für den numerischen Vergleich; keine Ersatz-Formeln im Test.
    baseline_html = subprocess.check_output(['git', 'show', 'c2b2e5e197c93cd2eacbd6ea9852bf38d5a5ccf9:index.html'], cwd=ROOT, text=True)
    baseline_context, baseline, _, _ = browser_page(browser, baseline_html)
    old_rows = baseline.evaluate('SolarApp.getCalculated().map(r=>[r.ts,r.power,r.base])')
    baseline_context.close()

    context, page, requests, errors = browser_page(browser)
    initial_settings=page.evaluate('SolarApp.getState()')
    rows = page.evaluate('SolarApp.getCalculated().map(r=>[r.ts,r.power,r.base])')
    assert len(rows) == len(old_rows)
    assert all(abs(a-b)<1e-8 for row, old in zip(rows, old_rows) for a,b in zip(row,old))
    assert 'Noch nicht konfiguriert' in page.locator('#inverterInfo').inner_text()
    original_model = page.evaluate('SolarApp.archiveModelId()')
    profile = page.evaluate('({key:SolarApp.profileKey(),near:SolarApp.getNearData().id})')
    before_requests = len(requests)
    page.locator('#openPanels').click()
    assert page.locator('.inverter-card').count() == 4
    assert page.locator('[data-p="inverterId"]').count() == 4
    assert page.locator('[data-p="kwp"]').evaluate_all('els=>els.map(e=>Number(e.value))') == [14.225, 5.28, 9.9, 1.9]
    for i, cap in enumerate([8, 6, 7, 1]):
        page.locator(f'[data-w="{i}"][data-field="maxAcKw"]').fill(str(cap))
    for i, value in enumerate(['wr-1', 'wr-2', 'wr-3', 'wr-2']):
        page.locator(f'[data-i="{i}"][data-p="inverterId"]').select_option(value)
    assert page.locator('[data-remove-inverter="wr-2"]').is_disabled()
    assert '7,180 kWp' in page.locator('[data-id="wr-2"] .inverter-summary').inner_text()
    page.locator('[data-w="0"][data-field="name"]').fill('Hauswechselrichter')
    page.locator('[data-i="0"][data-p="name"]').fill('Mein Haus')
    page.locator('#addInverter').click()
    assert page.locator('.inverter-card').count() == 5
    page.locator('.inverter-card').last.locator('[data-remove-inverter]').click()
    assert page.locator('.inverter-card').count() == 4
    page.locator('#applyPanels').click()
    assert not page.locator('#profileWizard').is_visible()
    assert len(requests) == before_requests, 'Elektrische Änderung löste Profil-/Wetterabruf aus'
    assert page.evaluate('({key:SolarApp.profileKey(),near:SolarApp.getNearData().id})') == profile
    result = page.evaluate('''() => ({cfg:SolarApp.getInverterConfiguration(),
      rows:SolarApp.getCalculated().map(r=>[r.power,r.base,r.clipping,r.byPanel.map(p=>[p.power,p.base])]),
      hash:SolarApp.archiveModelId(),archive:SolarApp.getArchive(),legacy:localStorage.getItem('schliersee-forecast-progressive-v11')})''')
    assert result['cfg']['configured']
    assert result['hash'] != original_model
    assert result['legacy'] == LEGACY
    assert original_model in result['archive']['previousModels']
    assert any(row[2] > 0 for row in result['rows'])
    displayed=page.evaluate('SolarApp.groupDays().flatMap(d=>d.rows).map(r=>[r.power,r.base,r.clipping,r.byPanel.map(p=>[p.power,p.base])])')
    for row in result['rows']+displayed:
        powers = row[3]
        for index, cap in [(0,8),(2,7)]:
            assert powers[index][0] <= cap+1e-9 and powers[index][1] <= cap+1e-9
        for column in (0,1):
            assert powers[1][column]+powers[3][column] <= 6+1e-9
    assert 'Clipping-Verlust:' in page.locator('#daySummary').inner_text()
    active_hash = result['hash']
    original = page.evaluate('SolarApp.archiveRecord("2026-11-05").original')
    # AC-Modellwechsel und Rückwechsel behalten das erste Original desselben Modells.
    page.evaluate('''() => {window.__now+=60000;SolarApp.getState().inverters[0].maxAcKw=9;SolarApp.calculate();SolarApp.saveForecastSnapshots();
      window.__now+=60000;SolarApp.getState().inverters[0].maxAcKw=8;SolarApp.calculate();SolarApp.saveForecastSnapshots();}''')
    assert page.evaluate('SolarApp.archiveRecord("2026-11-05").original') == original
    frozen = page.evaluate('SolarApp.archiveRecord("2026-11-05").current')
    page.evaluate('''() => {const w=SolarApp.getWeatherData();w.hourly.direct_normal_irradiance=w.hourly.direct_normal_irradiance.map(v=>v*1.2);
      w.minutely_15.direct_normal_irradiance=w.minutely_15.direct_normal_irradiance.map(v=>v*1.2);
      SolarApp.calculate();SolarApp.saveForecastSnapshots();}''')
    assert page.evaluate('SolarApp.archiveRecord("2026-11-05").current') == frozen
    page.reload()
    page.wait_for_function('SolarApp?.getNearData() && SolarApp.getCalculated().length>1900')
    assert page.evaluate('SolarApp.getState().panels[0].name') == 'Mein Haus'
    assert page.evaluate('SolarApp.getState().inverters[0].name') == 'Hauswechselrichter'
    assert page.evaluate('SolarApp.archiveModelId()') == active_hash
    assert page.evaluate('SolarApp.getState().losses') == 12
    page.locator('#openPanels').click()
    page.locator('#addPanel').click()
    page.locator('[data-remove-panel]').last.click()
    page.locator('[data-row="0"] .geometry summary').click()
    page.locator('[data-i="0"][data-geo="width_m"]').fill('17.1')
    page.locator('#applyPanels').click()
    assert page.locator('#profileWizard').is_visible(), 'Geometrische Änderungen müssen im Profilverfahren bleiben'
    assert not errors, errors
    context.close()
    print('OK: Altmodell unverändert, WR-Bedienung, Clipping, Profiltrennung, Reload und Originalschutz.')

    legacy_settings={'locationName':'Mein Standort','lat':47.69784444,'lon':11.88009722,'losses':17,'albedo':.31,'roofHeight':5,
                     'panels':[{'name':name,'kwp':kwp,'az':az,'tilt':tilt} for name,kwp,az,tilt in
                               [('Alt Haus',14.225,165,37),('Alt Garage',5.28,165,30),('Alt Carport',9.9,165,20),('Alt Hütte',1.9,254,20)]]}
    c, mobile, _, errors = browser_page(browser, settings=legacy_settings, viewport={'width':390,'height':844})
    mobile.locator('#openPanels').click()
    assert mobile.evaluate('SolarApp.getState().losses') == 17
    assert mobile.evaluate('SolarApp.getState().albedo') == .31
    assert mobile.evaluate('SolarApp.getState().panels[0].name') == 'Alt Haus'
    assert mobile.evaluate('document.getElementById("panelsDialog").scrollWidth<=document.getElementById("panelsDialog").clientWidth+1')
    mobile.locator('[data-w="0"][data-field="maxAcKw"]').fill('10')
    mobile.locator('[data-i="0"][data-p="inverterId"]').select_option('wr-1')
    assert 'Noch nicht konfiguriert' in mobile.locator('#inverterDraftStatus').inner_text()
    mobile.locator('#applyPanels').click()
    assert not mobile.evaluate('SolarApp.getInverterConfiguration().configured')
    assert not errors, errors
    c.close()
    for failure, expected in [('dwd','dwd'), ('github','cached')]:
        c, fallback, _, errors = browser_page(browser, failure=failure)
        assert fallback.evaluate('SolarApp.getWeatherDiagnostics().source') == expected
        assert not errors, errors
        c.close()
    print('OK: iPhone-Breite, Übernahme alter Einstellungen, DWD- und GitHub-Wetter-Fallback.')
    browser.close()

# Echte Archivierungsroutine mit der vollständigen App und kontrollierten Wetterdaten.
resources={p:json.loads((ROOT/p).read_text()) for p in ['horizontprofil.json','nahverschattung.json','prognosen/dwd_wetterstand.json']}
resources['weather']=WEATHER
prefix=r'''<script>window.__fakeStore={};Object.defineProperty(window,'localStorage',{value:{
getItem:k=>window.__fakeStore[k]??null,setItem:(k,v)=>window.__fakeStore[k]=String(v),removeItem:k=>delete window.__fakeStore[k]}});
const resources=%s;window.fetch=async url=>{const key=String(url).includes('api.open-meteo.com')?'weather':String(url).replace(/^\.\//,'').split('?')[0];
const doc=resources[key];return {ok:!!doc,status:doc?200:404,json:async()=>doc,text:async()=>JSON.stringify(doc)}};</script><!-- BEFORE_APP -->''' % json.dumps(resources)
prefix=prefix.replace('<script>','<script>const RealDate=Date;window.Date=class extends RealDate {constructor(...a){super(...(a.length?a:['+str(fixed_now)+']))}static now(){return '+str(fixed_now)+'}};',1)
fixture=HTML.replace('<script src="./inverters.js?v=12.7"></script>',prefix+'<script>'+(ROOT/'inverters.js').read_text()+'</script>')
with tempfile.TemporaryDirectory() as temp:
    target=Path(temp)
    (target/'scripts').mkdir()
    shutil.copy(ROOT/'scripts/archiviere_prognose.py',target/'scripts/archiviere_prognose.py')
    shutil.copytree(ROOT/'prognosen',target/'prognosen')
    protected={p:p.read_bytes() for p in (target/'prognosen').glob('*/*.json')}
    legacy_state=target/'prognosen/browser_prognosezustand_v11.json'
    protected[legacy_state]=legacy_state.read_bytes()
    fixture_file=target/'fixture.html'
    fixture_file.write_text(fixture)
    env={**os.environ,'PV_TEST_HTML_FILE':str(fixture_file),'PW_CHROMIUM_PATH':CHROMIUM,'GITHUB_EVENT_NAME':'workflow_dispatch'}
    runner='''import importlib.util,datetime,sys
spec=importlib.util.spec_from_file_location('archive',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Clock(datetime.datetime):
    @classmethod
    def now(cls,tz=None):return datetime.datetime.fromtimestamp(float(sys.argv[2]),tz)
m.datetime=Clock
sys.exit(m.main())
'''
    command=['python','-c',runner,str(target/'scripts/archiviere_prognose.py')]
    subprocess.run(command+[str(fixed_now/1000)],env=env,check=True)
    assert all(p.read_bytes()==content for p,content in protected.items())
    new_files=[p for p in (target/'prognosen').glob('*/*.json') if p not in protected]
    assert len(new_files)==1
    data=json.loads(new_files[0].read_text())
    assert data['modelVersion']=='V12.7.1'
    assert data['inverterConfiguration']['model']=='v12.7-ac-limit-1'
    assert data['inverterConfiguration']['configured'] is False
    assert data['clippingKWh']==0
    assert data['slot']=='test'
    assert (target/'prognosen/browser_prognosezustand_v12_7.json').is_file()
    protected[new_files[0]]=new_files[0].read_bytes()
    configured={**initial_settings,'panels':[{**p,'inverterId':'wr-1'} for p in initial_settings['panels']],
                'inverters':[{'id':'wr-1','name':'Test WR','maxAcKw':3}]}
    seed='<script>window.__fakeStore["schliersee-settings-v1"]='+json.dumps(json.dumps(configured))+';</script>'
    fixture_file.write_text(fixture.replace('<!-- BEFORE_APP -->',seed+'<!-- BEFORE_APP -->'))
    subprocess.run(command+[str(fixed_now/1000+1)],env=env,check=True)
    assert all(p.read_bytes()==content for p,content in protected.items())
    next_file=next(p for p in (target/'prognosen').glob('*/*.json') if p not in protected)
    next_data=json.loads(next_file.read_text())
    assert next_data['inverterConfiguration']['configured']
    assert next_data['clippingKWh']>0
    assert all(row[1]<=3+1e-9 for row in next_data['progressiveCurrent'])
    print('OK: Vollständige Archivierungsroutine, Zustandsimport, neue WR-Metadaten; alle alten Originaldateien unverändert.')
