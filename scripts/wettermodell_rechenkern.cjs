'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

const root = path.join(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');

async function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const scope = { crypto: webcrypto, TextEncoder, TextDecoder };
  scope.window = scope;
  vm.createContext(scope);
  for (const file of ['inverters.js', 'central-config.js', 'near-area.js']) {
    vm.runInContext(read(file), scope, { filename: file });
  }
  const html = read('index.html');
  const from = html.indexOf("'use strict';", html.indexOf('<script src="./near-area.js'));
  const to = html.indexOf('function renderProductionWindow(day)', from);
  const dayAfter = html.match(/^function dayAfter\(.*$/m)?.[0];
  const version = html.match(/<title>[^<]*\b(V[\d.]+)<\/title>/)?.[1];
  if (from < 0 || to <= from || !dayAfter || !version) throw Error('Rechenkern oder Versionsangabe fehlt in index.html.');
  vm.runInContext(html.slice(from, to) + '\n' + dayAfter + `
    globalThis.forecast = (bundle, day, forecasts) => {
      const setup = bundle.config;
      centralBundle = bundle;
      state = {lat:setup.location.latitude,lon:setup.location.longitude,panels:setup.panels,
        inverters:setup.inverters,albedo:setup.albedo,roofHeight:setup.location.roofHeightM};
      horizon = bundle.horizon.points;
      nearData = bundle.near;
      initNearFactors();
      return Object.fromEntries(Object.entries(forecasts).map(([id, weather]) => [id, weatherForecastForDay(weather,day)]));
    };
  `, scope, { filename: 'index.html' });
  const bundle = await scope.SolarCentral.verifyBundle(read('anlagenkonfiguration.json'), read('horizontprofil.json'), read('nahverschattung.json'));
  const outputs = scope.forecast(bundle, input.day, input.forecasts);
  process.stdout.write(JSON.stringify({
    modelVersion: version, configurationHash: bundle.configHash, physicalHash: bundle.physicalHash,
    profiles: bundle.config.profiles, forecasts: outputs,
  }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
