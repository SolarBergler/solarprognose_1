"""Temporary browser verification for today's production window."""
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_fixtures import CHROMIUM, Server, open_page, ready

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=CHROMIUM,args=['--no-sandbox'])
    for width in [1365,390]:
        context,page,errors=open_page(browser,Server(),width=width)
        ready(page)
        assert page.locator('#productionWindow').is_visible()
        times=page.locator('.production-times').inner_text()
        assert 'Uhr' in times
        page.locator('#days .day').last.click()
        assert page.locator('.production-times').inner_text()==times
        assert page.locator('#productionWindow').bounding_box()['x']>=0
        for name in ['productionStart','productionEnd']:
            box=page.locator('#'+name).bounding_box()
            assert box['x']+box['width']<=width
        page.locator('#productionWindow').screenshot(path=f'/tmp/production-{width}.png')
        # Known interval centres, a midday interruption and a tiny positive output.
        page.evaluate("""() => {
          const day='2026-11-05',start=localDayStart(day),end=localDayStart(dayAfter(day));
          renderProductionWindow({day,rows:[
            {ts:start+150,power:0},
            {ts:start+8*3600+150,power:.0001},
            {ts:start+12*3600+150,power:0},
            {ts:start+16*3600-150,power:2},
            {ts:end-150,power:0}
          ]});
        }""")
        assert page.locator('#productionStart').inner_text()=='08:00 Uhr'
        assert page.locator('#productionEnd').inner_text()=='16:00 Uhr'
        page.evaluate("""() => {
          const day='2026-11-05',start=localDayStart(day),end=localDayStart(dayAfter(day));
          renderProductionWindow({day,rows:[{ts:start+150,power:0},{ts:end-150,power:0}]});
        }""")
        assert page.locator('#productionStart').inner_text()=='—'
        assert 'keine Produktion' in page.locator('#productionWindowNote').inner_text()
        page.evaluate("""() => renderProductionWindow({day:'2026-11-05',rows:[{ts:localDayStart('2026-11-05')+12*3600,power:1}]})""")
        assert page.locator('#productionStart').inner_text()=='—'
        assert 'vollständige Prognosedaten' in page.locator('#productionWindowNote').inner_text()
        page.evaluate('renderProductionWindow(null)')
        assert not page.locator('#productionWindow').is_visible()
        assert not errors,errors
        context.close()
    # No radiation must produce no made-up times through the real calculation.
    server=Server()
    for group in ['hourly','minutely_15']:
        for field in ['direct_normal_irradiance','diffuse_radiation','shortwave_radiation']:
            if field in server.weather.get(group,{}):
                server.weather[group][field]=[0]*len(server.weather[group][field])
    context,page,errors=open_page(browser,server)
    ready(page)
    assert page.locator('#productionWindow').is_visible()
    assert 'keine Produktion' in page.locator('#productionWindowNote').inner_text()
    assert not errors,errors
    context.close()
    browser.close()
print('OK: desktop/mobile layout, current day independent of selection, exact interval boundaries, zero output and partial/missing data.')
