"""Real Chromium: rest field, hourly fetch, resume, cache and responsive layout.

Uses a pinned weather fixture, never the live weather service or GitHub writes.
"""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import copy, json, os, subprocess
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def run():
    fixture=os.environ.get('PV_TEST_WEATHER_FIXTURE')
    text=Path(fixture).read_text() if fixture else subprocess.check_output(
        ['git','show','e94f948943a1d7593bcec1e7d777cec29b853763:prognosen/letzter_wetterstand.json'],cwd=ROOT,text=True)
    weather=json.loads(text)['weather']
    state={'weather':copy.deepcopy(weather),'calls':0,'fail':False}
    errors=[]
    def route(request):
        url=urlsplit(request.request.url)
        if url.netloc=='api.open-meteo.com':
            state['calls']+=1
            request.fulfill(status=400 if state['fail'] else 200,content_type='application/json',
                            body=json.dumps({'error':True} if state['fail'] else state['weather']))
        elif url.path.startswith('/prognosen/'):
            request.fulfill(status=404,content_type='application/json',body='{}')
        else:
            file=ROOT/url.path.lstrip('/')
            if file.is_file():request.fulfill(path=str(file))
            else:request.fulfill(status=404,body='not found')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('PW_CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
        context=browser.new_context(timezone_id='America/New_York',locale='de-DE',viewport={'width':1365,'height':1000})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.clock.install(time=datetime(2026,11,6,10,7,30,tzinfo=timezone.utc))
        page.clock.pause_at(datetime(2026,11,6,10,7,31,tzinfo=timezone.utc))
        page.route('**/*',route);page.goto('https://solar.test/index.html')
        page.wait_for_function('SolarApp?.getRemainingForecast()?.available')
        assert state['calls']==1
        assert 'kWh' in page.locator('#remainingEnergy').inner_text()
        assert '11:07' in page.locator('#remainingNote').inner_text(),'Site time, not the device timezone'
        page.evaluate("SolarApp.saveForecastSnapshots(Date.parse('2026-11-06T06:00:00+01:00'))")
        original=page.evaluate('JSON.stringify(SolarApp.getArchive().days["2026-11-06"].original)')
        expected_old=page.evaluate("SolarApp.getRemainingForecast(Date.parse('2026-11-06T12:00:31+01:00')).kWh")
        for group in ['hourly','minutely_15']:
            for key in ['direct_normal_irradiance','diffuse_radiation','shortwave_radiation']:
                state['weather'][group][key]=[None if v is None else v*1.5 for v in state['weather'][group][key]]
        page.clock.run_for(30*60000)
        assert state['calls']==1,'No more half-hour weather polling'
        page.clock.run_for(23*60000)
        page.wait_for_function("SolarApp.getWeatherDiagnostics().issuedAt>=Date.parse('2026-11-06T12:00:00+01:00')")
        assert state['calls']==2
        assert page.evaluate('SolarApp.getRemainingForecast().kWh')>expected_old*1.4
        assert page.evaluate('JSON.stringify(SolarApp.getArchive().days["2026-11-06"].original)')==original
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true})")
        page.clock.run_for(60*60000)
        assert state['calls']==2,'A hidden tab does not fetch hourly'
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('focus'))")
        page.wait_for_function("SolarApp.getWeatherDiagnostics().issuedAt>=Date.parse('2026-11-06T13:00:00+01:00')")
        assert state['calls']==3,'Visibility and focus must not duplicate the resume fetch'
        state['fail']=True;page.locator('#refresh').click();page.clock.run_for(5000)
        page.wait_for_function('SolarApp.getWeatherDiagnostics().notLive===true')
        assert page.locator('#remainingToday').get_attribute('data-stale')=='true'
        assert 'nicht live' in page.locator('#remainingNote').inner_text()
        assert page.evaluate('JSON.stringify(SolarApp.getArchive().days["2026-11-06"].original)')==original
        output=Path(os.environ.get('PV_TEST_SCREENSHOTS',str(ROOT.parent/'screenshots')));output.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(output/'remaining-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        assert page.locator('#remainingEnergy').is_visible()
        page.screenshot(path=str(output/'remaining-mobile.png'))
        assert not errors,errors
        context.close();browser.close()
    print('PASS: actual Chromium, hourly update, resume deduplication, cache marking, preserved original and 390px layout')

if __name__=='__main__':run()
