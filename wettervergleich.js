(() => {
  'use strict';
  const panel = document.getElementById('weatherComparison');
  const day = document.getElementById('comparisonDay');
  const table = document.getElementById('comparisonRows');
  const status = document.getElementById('comparisonStatus');
  const sources = document.getElementById('comparisonSources');
  const root = 'https://raw.githubusercontent.com/SolarBergler/solarprognose_1/main/prognosen/';
  const models = {
    mosmix: 'DWD MOSMIX-L', icon: 'DWD ICON-D2 Native', ifs: 'ECMWF IFS HRES',
    'best-match': 'Open-Meteo Best Match',
  };
  const format = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  const berlin = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Berlin', dateStyle: 'short' });
  const clock = new Intl.DateTimeFormat('de-DE', { timeZone: 'Europe/Berlin', timeStyle: 'short' });
  const previous = value => new Date(Date.parse(value + 'T00:00:00Z') - 86400000).toISOString().slice(0, 10);
  day.min = '2026-11-23';
  day.max = '2026-12-13';
  const today = berlin.format(new Date());
  day.value = today < day.min ? day.min : today > day.max ? day.max : today;
  let generation = 0;

  async function get(captureDay, slot, target) {
    const url = root + captureDay + '/wettervergleich-' + slot + '.json';
    const response = await fetch(url, { cache: 'no-store' });
    if (response.status === 404) return { state: 'Fehlt im Archiv' };
    if (!response.ok) throw Error('HTTP ' + response.status);
    const record = await response.json();
    if (record.schema !== 1 || record.targetDay !== target || record.slot !== slot) throw Error('Falscher Archivstand');
    return { record, url };
  }

  function snowLabel(item) {
    const snow = item.record?.snowForecast;
    if (!snow) return item.state ?? 'Noch nicht erfasst';
    if (snow.status !== 'ok') return 'Schneeprognose fehlt';
    if (!snow.expectedSnowOnModules) return 'Kein Schneesignal';
    const windows = snow.nearZeroWindows.map(({ startUtc, endUtc }) =>
      clock.format(new Date(startUtc * 1000)) + '–' + clock.format(new Date(endUtc * 1000)));
    return 'Schnee erwartet, Ertrag nahe null · ' + windows.join(', ') + ' Uhr';
  }

  async function render() {
    const request = ++generation;
    const target = day.value;
    table.replaceChildren();
    sources.replaceChildren();
    if (!day.validity.valid || !target) {
      status.textContent = 'Wähle einen Zieltag im Vergleichszeitraum.';
      return;
    }
    status.textContent = 'Archiv wird geladen …';
    const settled = await Promise.allSettled([get(previous(target), '18', target), get(target, '06', target)]);
    if (request !== generation) return;
    const slots = settled.map(item => item.status === 'fulfilled' ? item.value : { state: 'Abruf fehlgeschlagen' });
    for (const [id, title] of Object.entries(models)) {
      const tr = document.createElement('tr');
      const heading = document.createElement('th');
      heading.scope = 'row';
      heading.textContent = title;
      tr.append(heading);
      for (const item of slots) {
        const value = item.record?.models[id];
        const cell = document.createElement('td');
        cell.textContent = Number.isFinite(value?.powerKWh) ? format.format(value.powerKWh) + ' kWh'
          : item.state ?? 'Nicht verfügbar';
        if (value?.issuedAtUtc) cell.title = 'Modelllauf ' + value.issuedAtUtc;
        tr.append(cell);
      }
      table.append(tr);
    }
    const snowRow = document.createElement('tr');
    const snowHeading = document.createElement('th');
    snowHeading.scope = 'row';
    snowHeading.textContent = 'Schnee auf Modulen';
    snowRow.append(snowHeading);
    for (const item of slots) {
      const cell = document.createElement('td');
      cell.textContent = snowLabel(item);
      snowRow.append(cell);
    }
    table.append(snowRow);
    status.textContent = '';
    slots.forEach(({ record, url }, index) => {
      if (!record) return;
      const link = document.createElement('a');
      link.href = url;
      link.textContent = (index === 0 ? 'Vorabend' : 'Morgen') + ' · ' + clock.format(new Date(record.capturedAtUtc)) + ' Uhr · Rohdaten und 5-Minuten-Kurven';
      if (sources.childNodes.length) sources.append(document.createElement('br'));
      sources.append(link);
    });
  }
  panel.addEventListener('toggle', () => { if (panel.open) render(); });
  day.addEventListener('change', render);
  document.getElementById('refreshComparison').addEventListener('click', render);
})();
