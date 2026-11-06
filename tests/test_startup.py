"""Normaler Browserstart, Netz-/Pages-Ausfälle und unveränderte historische Originale."""
import copy
import json
import subprocess
from datetime import datetime,timezone
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from browser_fixtures import ROOT,CHROMIUM,Server,open_page,ready
from test_central_browser import plant_state

OLD_KEY='schliersee-forecast-progressive-v12.7'
KEY='schliersee-forecast-progressive-v12.8'
DAY='2026-11-06'

def at(minute):return datetime(2026,11,5,18,minute,tzinfo=timezone.utc)
def seven(page):
    page.wait_for_function('window.SolarApp?.groupDays().length===7&&document.querySelectorAll("#days .day").length===7')
    page.wait_for_function('document.getElementById("startupNotice").classList.contains("hidden")')
def weather_change(server):
    for group in ['hourly','minutely_15']:
        for field in ['direct_normal_irradiance','diffuse_radiation','shortwave_radiation']:
            values=server.weather.get(group,{}).get(field,[])
            server.weather[group][field]=[None if v is None else v*.5 for v in values]

def upgrade(browser,*,original_coordinates=False,changed_model=False):
    server=Server();config=json.loads(server.files['anlagenkonfiguration.json'])
    legacy=plant_state(config)
    if original_coordinates:legacy.update(lat=47.69784444,lon=11.88009722)
    if changed_model:legacy['inverters'][0]['maxAcKw']+=1
    old_html=subprocess.check_output(['git','show','e94f948943a1d7593bcec1e7d777cec29b853763:index.html'],cwd=ROOT,text=True)
    c,old,errors=open_page(browser,server,legacy=legacy,html=old_html,at=at(0))
    old.wait_for_function('SolarApp?.getArchive().days["2026-11-06"]?.original?.values.length>200')
    before=old.evaluate('localStorage.getItem('+json.dumps(OLD_KEY)+')');source=json.loads(before)['days'][DAY]
    storage=c.storage_state();assert not errors,errors;c.close()
    weather_change(server)
    # V12.8.1 erzeugte bereits neue, deckungsgleiche Referenzen: genau der gemeldete Fall.
    broken_html=subprocess.check_output(['git','show','36e0008619a54f61515a14dc894e118dffdc43bc:index.html'],cwd=ROOT,text=True)
    c,broken,errors=open_page(browser,server,storage=storage,html=broken_html,at=at(10));ready(broken)
    broken.wait_for_function('SolarApp.getArchive().days["2026-11-06"]?.original?.values.length>200')
    generated=broken.evaluate('SolarApp.getArchive().days["2026-11-06"].original')
    assert generated['values']!=source['original']['values']
    # Ein serialisierter RAM-Lookup darf den nächsten Browserstart nicht blockieren.
    broken.evaluate('''key=>{const a=JSON.parse(localStorage.getItem(key));for(const r of Object.values(a.days)){r._lookup={};r._lookupVersion=r.updatedAt;}localStorage.setItem(key,JSON.stringify(a));}''',KEY)
    storage=c.storage_state();assert not errors,errors;c.close()
    c,page,errors=open_page(browser,server,storage=storage,at=at(20));seven(page)
    after=page.evaluate('SolarApp.getArchive().days["2026-11-06"]')
    assert page.evaluate('localStorage.getItem('+json.dumps(OLD_KEY)+')')==before
    copies=page.evaluate('SolarApp.getArchive().previousModels')
    assert any(DAY in days and days[DAY]['original']==source['original'] for name,days in copies.items() if name.startswith('legacy:'))
    if changed_model:
        assert after['original']['values']==generated['values']
        assert 'sourceArchiveKey' not in after['original']
        assert 'getrennt erhalten' in page.locator('#historyMigration').inner_text()
    else:
        assert after['original']['values']==source['original']['values']
        assert after['original']['at']==source['original']['at']
        assert after['original']['sourceModel']==source['model']
        assert after['original']['values']!=[[r[0],r[1]] for r in after['current']]
        assert generated in after['referenceHistory']
        assert 'V12.7.2' in page.locator('#historyInfo').inner_text()
        if original_coordinates:assert after['original']['compatibility']=='published-location-precision-v12.8'
        # Wiederholtes Laden bleibt idempotent und ersetzt das Original weiterhin nicht.
        data=c.storage_state();c.close();c,page,errors=open_page(browser,server,storage=data,at=at(25));seven(page)
        again=page.evaluate('SolarApp.getArchive().days["2026-11-06"]')
        assert again['original']==after['original']
        assert again['referenceHistory']==after['referenceHistory']
    assert not errors,errors;c.close()

def run():
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path=CHROMIUM,args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
        server=Server();c,page,errors=open_page(b,server);seven(page)
        assert page.evaluate('navigator.webdriver') is False
        assert page.evaluate('localStorage.getItem("schliersee-settings-v1")') is None
        assert not errors,errors;c.close()
        print('OK: normaler Browser, frischer Speicher, sieben Prognosen ohne vorbereitete Daten.')
        upgrade(b);upgrade(b,original_coordinates=True);upgrade(b,changed_model=True)
        print('OK: echter Versionswechsel V12.7.2 → V12.8.1 → Korrektur: alte Originale, Zeitstempel und vorherige Kurven erhalten; abweichende WR-Modelle getrennt.')
        for fault in ['central-config.js','anlagenkonfiguration.json','horizontprofil.json','nahverschattung.json']:
            server=Server();normal=server.route;count=[0]
            def route(r):
                if fault in r.request.url:
                    count[0]+=1
                    if count[0]==1:r.fulfill(status=503,body='temporary deployment');return
                normal(r)
            server.route=route
            c,page,errors=open_page(b,server);seven(page)
            assert count[0]>=2,(fault,count)
            assert not errors,errors;c.close()
        print('OK: vorübergehend fehlende Programm-, Konfigurations- und Profildateien werden automatisch neu geladen.')
        server=Server();normal=server.route;count=[0]
        def partial(r):
            if urlsplit(r.request.url).path=='/nahverschattung.json':
                count[0]+=1
                if count[0]==1:r.fulfill(content_type='application/json',body=server.pages['nahverschattung.json']+' ');return
            normal(r)
        server.route=partial
        c,page,errors=open_page(b,server);seven(page)
        assert count[0]>=2;assert not errors,errors;c.close()
        print('OK: veraltetes Profil während Pages-Veröffentlichung wird verworfen; danach nur vollständiges verifiziertes Paket aktiv.')
        for fault in ['central-config.js','anlagenkonfiguration.json','horizontprofil.json','nahverschattung.json']:
            server=Server();normal=server.route;blocked=[True]
            def permanent(r):
                if blocked[0] and fault in r.request.url:r.fulfill(status=503,body='unavailable');return
                normal(r)
            server.route=permanent
            c,page,errors=open_page(b,server)
            page.wait_for_function('document.getElementById("startupNotice").classList.contains("warning")&&!document.getElementById("retryStartup").disabled')
            assert fault in page.locator('#startupMessage').inner_text()
            assert page.evaluate('SolarApp.getCalculated().length')==0
            blocked[0]=False;page.locator('#retryStartup').click();seven(page)
            assert not errors,errors;c.close()
        print('OK: konkrete Fehlermeldung für jede fehlende Datei, keine Berechnung ungeprüfter Profile, Wiederholen repariert den Start ohne Löschen von Browserdaten.')
        server=Server();server.weather_fail=True;normal=server.route;blocked=[True]
        def weather_unavailable(r):
            if blocked[0] and 'wetterstand.json' in r.request.url:r.fulfill(status=503,body='unavailable');return
            normal(r)
        server.route=weather_unavailable
        c,page,errors=open_page(b,server)
        page.wait_for_function('document.getElementById("startupNotice").classList.contains("warning")&&!document.getElementById("retryStartup").disabled')
        assert 'DWD' in page.locator('#startupMessage').inner_text()
        assert page.evaluate('SolarApp.getCentralConfiguration().ready')
        assert page.evaluate('SolarApp.getCalculated().length')==0
        blocked[0]=False;server.weather_fail=False;page.locator('#retryStartup').click();seven(page)
        assert not errors,errors;c.close()
        print('OK: auch Wetterausfälle nennen die fehlgeschlagenen Quellen; Wiederholen liefert anschließend sieben Tage.')
        b.close()

if __name__=='__main__':run()
