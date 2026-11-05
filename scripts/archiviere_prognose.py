#!/usr/bin/env python3
"""Archiviert die auf der Website berechnete V12-Prognose via Chromium.

Benoetigt auf GitHub Actions: playwright + chromium. Auf iOS/macOS keine Installation.
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'prognosen'
STATE_FILE = DATA / 'browser_prognosezustand_v11.json'
URL = os.getenv('PV_SITE_URL', 'https://solarbergler.github.io/solarprognose_1/')
EVENT = os.getenv('GITHUB_EVENT_NAME', 'workflow_dispatch')
CRON = os.getenv('GITHUB_EVENT_SCHEDULE', '')
TZ = ZoneInfo('Europe/Berlin')
ARCHIVE_KEY = 'schliersee-forecast-progressive-v11'


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def main():
    now = datetime.now(TZ)
    day = now.strftime('%Y-%m-%d')
    # Dieser Testlauf ist absichtlich nur fuer den 1.–8. November 2026 aktiv.
    if EVENT == 'schedule' and not ('2026-11-01' <= day <= '2026-11-08'):
        print('Außerhalb des vereinbarten Messzeitraums: keine Aktion.')
        return 0

    if EVENT == 'schedule':
        if CRON in ('0 6 1-7 11 *', '0 6 * * *'):
            slot, target = '06', 6
        elif CRON in ('0 18 1-7 11 *', '0 18 * * *'):
            slot, target = '18', 18
        else:
            raise RuntimeError(f'Unbekannter Scheduler-Ausloeser {CRON!r}; archiviere nichts.')
        # Groessere Scheduler-Verzoegerungen duerfen nicht als 06/18-Uhr-Prognose erscheinen.
        if not (target <= now.hour < target + 2):
            raise RuntimeError(f'Abruf zu spaet fuer {slot}: {now.isoformat()}; kein irrefuehrender Snapshot.')
        output = DATA / day / f'{slot}.json'
    else:
        slot = 'test'
        output = DATA / day / f'test-{now.strftime("%H%M%S")}.json'

    if output.exists():
        print(f'Originalsnapshot existiert bereits und bleibt unveraendert: {output}')
        return 0

    previous = None
    if STATE_FILE.exists():
        previous = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        if previous.get('version') != 2 or not isinstance(previous.get('days'), dict):
            raise RuntimeError('Gespeicherter V12-Prognosezustand ist ungueltig.')
        for record in previous['days'].values():
            # V10 benutzt im RAM eine Map fuer die Diagramme. Nach JSON-Serialisierung
            # waere daraus ein kaputtes {} geworden. Diese Zwischenwerte NIE importieren.
            if isinstance(record, dict):
                record.pop('_lookup', None)
                record.pop('_lookupVersion', None)

    errors = []
    failed_requests = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.getenv('PW_CHROMIUM_PATH') or None, args=['--no-sandbox'])
        context = browser.new_context(timezone_id='Europe/Berlin', locale='de-DE', viewport={'width': 1365, 'height': 960})
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('requestfailed', lambda req: failed_requests.append(f'{req.url}: {req.failure}'))
        # Frisch abgerufene DWD-Datei sofort für den automatischen Browser bereitstellen.
        # GitHub Pages braucht nach einem Commit eventuell noch einige Minuten zur Veröffentlichung.
        dwd_file = DATA / 'dwd_wetterstand.json'
        if dwd_file.exists():
            def serve_dwd(route):
                route.fulfill(status=200,content_type='application/json',body=dwd_file.read_text(encoding='utf-8'))
            page.route('**/prognosen/dwd_wetterstand.json*',serve_dwd)
        if previous is not None:
            # localStorage wird vor dem ersten V10-Script gesetzt, damit die Daten vor
            # dem neuen Abruf eingefroren sind und die Vorabendkurve erhalten bleibt.
            init_js = "try { localStorage.setItem(" + json.dumps(ARCHIVE_KEY) + ", " + json.dumps(json.dumps(previous, ensure_ascii=False)) + "); } catch (e) { console.error(e); }"
            page.add_init_script(script=init_js)

        print('Öffne echte Solarprognose:', URL)
        if os.getenv('PV_TEST_HTML_FILE'):
            # Nur fuer lokale Simulationen ohne Netz. GitHub verwendet immer page.goto().
            from pathlib import Path as _Path
            test_html = _Path(os.environ['PV_TEST_HTML_FILE']).read_text(encoding='utf-8')
            if previous is not None:
                # Die Testseite hat ihren eigenen localStorage-Dummy, der vor V10 geladen wird.
                assign = 'window.__fakeStore[' + json.dumps(ARCHIVE_KEY) + ']=' + json.dumps(json.dumps(previous)) + ';'
                test_html = test_html.replace('<!-- BEFORE_APP -->', '<script>'+assign+'</script><!-- BEFORE_APP -->')
            page.set_content(test_html, wait_until='domcontentloaded')
        else:
            page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        try:
            page.wait_for_function('''() => {
              const a=window.SolarApp;
              const required=['getHorizon','getNearData','getArchive','archiveModelId',
                              'groupDays','getState','getWeatherResolution'];
              if (!a || !required.every(name=>typeof a[name]==='function') ||
                  a.getHorizon()?.length!==720 || !a.getNearData?.() ||
                  !document.getElementById('status')?.textContent?.includes('Nahverschattung aktiv')) return false;
              const date=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
              const rec=a.getArchive()?.days?.[date];
              return !!(rec && rec.model===a.archiveModelId() && rec.current?.length>=280 &&
                        a.groupDays().some(d=>d.day===date && d.rows?.length>=280));
            }''', timeout=120000)
        except PlaywrightTimeoutError as ex:
            try:
                path = ROOT / 'pv_archiv_fehler.png'
                page.screenshot(path=str(path), full_page=True)
                print(f'Fehlerscreenshot: {path}')
                print('Status:', page.locator('#status').inner_text(timeout=2000) if page.locator('#status').count() else '?')
                print('Horizont:', page.locator('#horizonSource').inner_text(timeout=2000) if page.locator('#horizonSource').count() else '?')
            except Exception as diagnostic_error:
                print('Diagnose fehlgeschlagen:', diagnostic_error)
            print('JavaScript-Fehler:', errors[-5:])
            print('Fehlgeschlagene Netzwerkanfragen:', failed_requests[-10:])
            raise RuntimeError('V12 konnte keine gültige Live-Prognose mit 720-Punkte-Berg- und DOM20-Nahprofil bereitstellen.') from ex

        result = page.evaluate(r'''() => {
          const app=window.SolarApp;
          const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
          const day=app.groupDays().find(d=>d.day===today);
          const archive=app.getArchive();
          const record=archive.days[today];
          const state=app.getState();
          return {
            day:today,
            recordedAt:new Date().toISOString(),
            status:document.getElementById('status')?.textContent?.trim(),
            horizonSource:document.getElementById('horizonSource')?.textContent?.trim(),
            modelHash:app.archiveModelId(),
            modelVersion:document.querySelector('.eyebrow')?.textContent?.match(/\bV\d+(?:\.\d+)+\b/i)?.[0] || null,
            weatherDiagnostics:app.getWeatherDiagnostics?.(),
            nearProfileId:app.getNearData()?.id,
            nearProfileSource:app.getNearData()?.source,
            horizonPoints:app.getHorizon()?.length,
            weatherResolution:app.getWeatherResolution(),
            locationName:state.locationName,
            latitude:state.lat,
            longitude:state.lon,
            plantKWp:state.panels.reduce((a,p)=>a+p.kwp,0),
            panelNames:state.panels.map(p=>p.name),
            powerKWh:day.power,
            withoutHorizonKWh:day.base,
            byPanel:day.panels.map((p,i)=>({name:state.panels[i].name,kWh:p.power,withoutHorizonKWh:p.base})),
            original:record.original,
            progressiveCurrent:record.current,
            progressiveLastUpdate:record.updatedAt,
            browserArchive:archive,
            sourceWeatherData:app.getWeatherData?.() || null,
          };
        }''')
        browser.close()

    if result['day'] != day:
        raise RuntimeError(f'Lokales Datum {day} != Prognosedatum {result["day"]}')
    if result['horizonPoints'] != 720 or not result['nearProfileId'] or not result['status'] or 'Nahverschattung aktiv' not in result['status']:
        raise RuntimeError('Kein aktives Geländeprofil. Zahlen werden nicht archiviert.')
    if len(result['progressiveCurrent']) < 280 or len(result['original']['values']) < 280:
        raise RuntimeError('Unvollständige Fünf-Minuten-Prognose.')
    if abs(datetime.now(timezone.utc).timestamp()*1000 - result['progressiveLastUpdate']) > 5*60*1000:
        raise RuntimeError('Prognose wurde nicht frisch erzeugt.')

    # Prüfung des integrierten Tagesertrags. Werte der Seite sind 5-Minuten-Mittel in kW.
    total = sum(float(r[1])/12 for r in result['progressiveCurrent'])
    if abs(total - float(result['powerKWh'])) > 0.2:
        raise RuntimeError(f'Widerspruch zwischen archivierter 5-Minuten-Kurve ({total:.3f} kWh) und Tageswert ({result["powerKWh"]:.3f} kWh)')

    # Der Roh-Wetterstand wird zusätzlich öffentlich auf GitHub Pages bereitgestellt.
    # Bei einer fehlgeschlagenen Browser-Open-Meteo-Abfrage darf nie ein alter
    # Cache als frischer Wetterstand gespeichert werden. Die bestehende
    # Archivdatei (06/18 Uhr) und die fortgeschriebenen Kurven bleiben unverändert.
    source_weather = result.pop('sourceWeatherData', None)
    meteo_provider=(result.get('weatherDiagnostics') or {}).get('source', 'unknown')
    if meteo_provider not in ('open-meteo','dwd'):
        raise RuntimeError(f'Kein frischer unabhängiger Wetterstand verfügbar: {meteo_provider}')
    if isinstance(source_weather, dict) and isinstance(source_weather.get('hourly', {}).get('time'), list):
        shared_weather = {
            'schema': 1,
            'capturedAt': datetime.now(timezone.utc).isoformat(),
            'latitude': result['latitude'],
            'longitude': result['longitude'],
            'source': 'Open-Meteo, live über die archivierende GitHub-Actions-Browserausführung',
            'weather': source_weather,
        }
        save_json(DATA / 'letzter_wetterstand.json', shared_weather)
        print('GitHub-Wetterstand aktualisiert (Safari-Fallback).')
    else:
        print('WARNUNG: Kein sicher live erfasster Wetterstand verfügbar; GitHub-Wettercache bleibt unverändert.')

    browser_archive = result.pop('browserArchive')
    for record in browser_archive.get('days', {}).values():
        if isinstance(record, dict):
            record.pop('_lookup', None)
            record.pop('_lookupVersion', None)
    result['captureType'] = 'live-browser-solarprognose-dom20'
    result['slot'] = slot
    result['sourceUrl'] = URL
    result['description'] = 'Echter JavaScript-Lauf mit DOM20-Baum- und Gebäudeverschattung, 720-Punkte-Berghorizont und 5-Minuten-Werten. Abgelaufene Intervalle bleiben eingefroren. Historische V10-Dateien sind unverändert.'
    result['capturedAtLocal'] = datetime.now(TZ).isoformat()
    save_json(output, result)
    save_json(STATE_FILE, browser_archive)
    print('GESPEICHERT:', output, '| Wetterquelle:', meteo_provider)
    print(f'Ist von der Seite gelesene V12-Prognose: {result["powerKWh"]:.2f} kWh; Original: {sum(v[1]/12 for v in result["original"]["values"]):.2f} kWh')
    print('Gelände:', result['horizonSource'])
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f'FEHLER: {e}', file=sys.stderr)
        raise
