"""Automatisches Warten/Aktivieren: python tests/test_profile_publication.py.

Chromium + Playwright; virtuelle Uhr und lokale Antworten, keine Live-Uploads.
"""
import copy
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, Error as PlaywrightError

ROOT=Path(__file__).resolve().parents[1]
BASELINE='c2b2e5e197c93cd2eacbd6ea9852bf38d5a5ccf9'
def fixture(path):
    return json.loads(subprocess.check_output(['git','show',BASELINE+':'+path],cwd=ROOT,text=True))
OLD_NEAR=fixture('nahverschattung.json')
OLD_HORIZON=fixture('horizontprofil.json')
WEATHER=fixture('prognosen/letzter_wetterstand.json')['weather']
HTML=(ROOT/'index.html').read_text()
PANELS=[{'id':'panel-'+str(i+1),'name':name,'kwp':kwp,'az':az,'tilt':tilt,'inverterId':wr,'geo':geo}
        for i,(name,kwp,az,tilt,wr,geo) in enumerate([
            ('Haus',14.225,165,37,'wr-1',{'latitude':47.697785941129744,'longitude':11.880120223346184,'width_m':17,'depth_m':6,'lower_edge_height_m':3,'upper_edge_height_m':7}),
            ('Garage',5.28,165,30,'wr-2',{'latitude':47.69792646402266,'longitude':11.880227171529725,'width_m':8,'depth_m':5,'lower_edge_height_m':3,'upper_edge_height_m':6}),
            ('Carport',9.9,165,20,'wr-3',{'latitude':47.69786343561308,'longitude':11.879849604421532,'width_m':11,'depth_m':6,'lower_edge_height_m':3,'upper_edge_height_m':7}),
            ('Hütte',1.9,254,20,'wr-2',{'latitude':47.698012109923496,'longitude':11.880217099312013,'width_m':5.5,'depth_m':1.8,'lower_edge_height_m':2.5,'upper_edge_height_m':4})])]
PANELS[0]['name']='Haus links';PANELS[0]['kwp']=7;PANELS[0]['geo']['width_m']=8
extra=copy.deepcopy(PANELS[0]);extra.update(id='panel-5',name='Haus rechts',kwp=7.225,inverterId='wr-4')
PANELS.append(extra)
NEW_NEAR=copy.deepcopy(OLD_NEAR)
NEW_NEAR['id']='publication-test-new-five-fields'
NEW_NEAR['panelProfiles'].append(copy.deepcopy(NEW_NEAR['panelProfiles'][0]))
NEW_NEAR['config']={'panels':PANELS,'inverters':[{'id':'wr-'+str(i+1),'name':'WR'+str(i+1),'maxAcKw':power} for i,power in enumerate([7,5,10,7])]}
NEW_HORIZON=copy.deepcopy(OLD_HORIZON)
NEW_HORIZON['points'][0]['height']+=.25


class Scenario:
    def __init__(self,browser,width=1365):
        self.context=browser.new_context(timezone_id='Europe/Berlin',locale='de-DE',viewport={'width':width,'height':900})
        self.page=self.context.new_page()
        self.page.clock.install(time=datetime(2026,11,5,18,tzinfo=timezone.utc))
        self.phase='initial';self.requests=0;self.errors=[];self.held=[]
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.route('**/*',self.route)
        self.page.goto('https://solar.test/index.html')
        self.page.wait_for_function('window.SolarApp?.getNearData()&&SolarApp.getHorizon()?.length===720&&SolarApp.getCalculated().length>1900')
        self.old_state=self.page.evaluate('JSON.stringify(SolarApp.getState())')
        self.old_model=self.page.evaluate('SolarApp.archiveModelId()')
        self.page.evaluate('''({near,horizon})=>{
          pendingPanels=near.config.panels.map(({geo,...p})=>p);
          pendingGeometry=near.config.panels.map(p=>p.geo);
          pendingInverters=near.config.inverters;
          generatedFiles.doc=near;generatedFiles.horizonDoc=horizon;
          document.getElementById('verifyProfiles').classList.remove('hidden');
          document.getElementById('profileWizard').showModal();
        }''',{'near':NEW_NEAR,'horizon':NEW_HORIZON})

    def route(self,r):
        path=urlsplit(r.request.url).path.lstrip('/') or 'index.html'
        if 'api.open-meteo.com' in r.request.url:
            r.fulfill(content_type='application/json',body=json.dumps(WEATHER));return
        if path in ['nahverschattung.json','horizontprofil.json']:
            if 'profile-check=' in r.request.url:
                self.requests+=1
                if self.phase=='offline':r.abort();return
                if self.phase=='hung':self.held.append(r);return
                if self.phase=='badjson':r.fulfill(content_type='application/json',body='{invalid');return
            if self.phase in ['ready','invalid','half']:
                doc=copy.deepcopy(NEW_NEAR if path.startswith('nah') else NEW_HORIZON)
                if self.phase=='half' and path.startswith('horizont'):doc=OLD_HORIZON
                if self.phase=='invalid' and path.startswith('nah'):doc['panelProfiles'][0]['samples']=[]
            else:doc=OLD_NEAR if path.startswith('nah') else OLD_HORIZON
            r.fulfill(content_type='application/json',body=json.dumps(doc));return
        if path=='index.html':r.fulfill(content_type='text/html',body=HTML)
        elif (ROOT/path).is_file():r.fulfill(path=str(ROOT/path))
        else:r.fulfill(status=404,body='not found')

    def start(self,phase):
        self.phase=phase;self.page.locator('#verifyProfiles').click()

    def message(self,text):
        self.page.wait_for_function('(text)=>document.getElementById("wizardStatus").textContent.includes(text)',arg=text)

    def unchanged(self):
        assert self.page.evaluate('JSON.stringify(SolarApp.getState())')==self.old_state
        assert self.page.evaluate('SolarApp.archiveModelId()')==self.old_model

    def done(self):
        self.page.wait_for_function('!document.getElementById("profileWizard").open')
        assert self.page.evaluate('SolarApp.getState().panels.length')==5
        assert self.page.evaluate('SolarApp.getInverterConfiguration().configured')
        count=self.requests;self.page.clock.fast_forward(60000)
        assert self.requests==count,'Prüfung lief nach Erfolg weiter'
        assert not self.errors,self.errors

    def close(self):
        assert not self.errors,self.errors
        for route in self.held:
            try:route.abort('aborted')
            except PlaywrightError:pass  # Request wurde bereits durch AbortController beendet.
        self.context.close()


with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.getenv('PW_CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
    s=Scenario(browser);s.start('old');s.message('älteren Profilstand')
    assert s.page.locator('#profilePublishProgress').is_visible()
    assert s.page.locator('#verifyProfiles').is_disabled()
    assert s.page.locator('#generateProfiles').is_disabled()
    assert s.page.locator('#domFiles').is_disabled()
    s.unchanged()
    before=s.requests
    s.page.evaluate('document.getElementById("verifyProfiles").dispatchEvent(new Event("click"))')
    assert s.requests==before,'Doppelter Klick startete parallele Prüfung'
    s.phase='half';s.page.clock.fast_forward(5000)
    s.page.wait_for_function('profilePublication!==null')
    assert '0:05' in s.page.locator('#profilePublishElapsed').inner_text()
    s.unchanged();assert s.page.locator('#profileWizard').is_visible()
    s.phase='ready';s.page.clock.fast_forward(5000);s.done();s.close()
    print('OK: sichtbarer Wartezustand, verstrichene Zeit, erneute Prüfung, beide Profile erforderlich, automatisches Schließen.')

    s=Scenario(browser);s.start('old');s.message('älteren Profilstand')
    s.page.clock.fast_forward(300000);s.message('Nach 5 Minuten')
    s.unchanged();assert s.page.locator('#profileWizard').is_visible()
    assert s.page.locator('#verifyProfiles').is_enabled()
    assert not s.page.locator('#profilePublishProgress').is_visible()
    s.start('ready');s.done();s.close()
    print('OK: Zeitlimit, unveränderte Konfiguration und erneuter Versuch ohne Neuberechnung.')

    for phase in ['offline','hung']:
        s=Scenario(browser);s.start(phase)
        if phase=='hung':s.page.clock.fast_forward(12000)
        s.message('nicht erreichbar');s.unchanged()
        s.phase='ready';s.page.clock.fast_forward(5000);s.done();s.close()
    print('OK: Netzwerkfehler und hängende Abrufe werden begrenzt und automatisch erneut geprüft.')

    for cancel in ['button','escape']:
        s=Scenario(browser);s.start('old');s.message('älteren Profilstand')
        if cancel=='button':s.page.locator('#closeWizard').click()
        else:s.page.keyboard.press('Escape')
        count=s.requests;s.phase='ready';s.page.clock.fast_forward(30000)
        assert s.requests==count
        assert s.page.locator('#verifyProfiles').is_enabled()
        s.unchanged();s.close()
    print('OK: Schließen und Escape stoppen Timer/Abrufe ohne spätere Aktivierung.')

    for phase in ['invalid','badjson']:
        s=Scenario(browser);s.start(phase);s.message('Aktivierung nicht abgeschlossen')
        s.unchanged();assert s.page.locator('#profileWizard').is_visible()
        assert s.page.locator('#verifyProfiles').is_enabled()
        s.close()
    print('OK: Ungültige Dateien verändern weder Einstellungen noch die laufende Prognose.')

    s=Scenario(browser,width=390);s.start('old');s.message('älteren Profilstand')
    assert s.page.evaluate('document.getElementById("profileWizard").scrollWidth<=document.getElementById("profileWizard").clientWidth+1')
    s.phase='ready';s.page.clock.fast_forward(5000);s.done();s.close()
    s=Scenario(browser);s.start('ready');s.done();s.close()
    print('OK: iPhone-Breite und sofortige Aktivierung bereits veröffentlichter Profile.')
    browser.close()
