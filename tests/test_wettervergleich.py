from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import archiviere_wettervergleich as archive
import schneeprognose as snow_rule
import vergleiche_wettermodelle as comparison


class WeatherComparisonTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat('2026-11-22T18:02:00+01:00')
        self.day = archive.FIRST_DAY
        self.start, self.end = archive.day_bounds(self.day)

    def weather(self, level):
        def component(step, fields):
            times = list(range(self.start + step, self.end + 1, step))
            return {'time': times, **{k: [(
                10 if k == 'temperature_2m' else 95 if k == 'cloud_cover' else
                level if k in ('shortwave_radiation', 'diffuse_radiation') else 0
            )] * len(times) for k in fields}}
        return {'hourly': component(3600, archive.HOURLY_FIELDS),
                'minutely_15': component(900, archive.FIELDS)}

    def test_time_windows_preserve_original_forecast_lead(self):
        self.assertEqual(archive.forecast_window('18', self.now)[1], self.day)
        self.assertEqual(archive.forecast_window('06', self.now.replace(day=23, hour=6))[1], self.day)
        self.assertIsNone(archive.forecast_window('06', self.now.replace(hour=6)))
        with self.assertRaises(ValueError):
            archive.forecast_window('18', self.now.replace(hour=20))
        self.assertIsNone(archive.forecast_window('18', self.now.replace(month=12, day=13)))

    def test_daylight_missing_hour_is_rejected(self):
        data = self.weather(100)
        data['hourly']['diffuse_radiation'][10] = None
        with self.assertRaisesRegex(ValueError, 'diffuse_radiation'):
            archive.weather_for_day(data, self.day, True)

    def test_morning_mosmix_without_first_night_hours_is_usable(self):
        data = self.weather(100)
        for key, values in data['hourly'].items():
            data['hourly'][key] = values[4:]
        weather = archive.weather_for_day(data, self.day, False)
        hourly = weather['hourly']
        self.assertEqual(len(hourly['time']), 24)
        self.assertEqual(hourly['shortwave_radiation'][:5], [0, 0, 0, 0, 100])
        self.assertEqual(hourly['temperature_2m'][:5], [None, None, None, None, 10])
        for key, values in data['hourly'].items():
            data['hourly'][key] = values[7:]
        with self.assertRaisesRegex(ValueError, 'stündliche Abdeckung'):
            archive.weather_for_day(data, self.day, False)

    def test_one_file_contains_independent_curves_and_retains_original(self):
        def source(value):
            return {'issuedAtUtc': '2026-11-22T12:00:00+00:00', 'weather': self.weather(value)}

        cases = {'icon': 110, 'ifs': 140, 'best-match': 130}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '2026-11-22' / 'wettervergleich-18.json'
            with (patch.object(archive, 'read_mosmix', return_value=source(80)),
                  patch.object(archive, 'download_model', side_effect=lambda model, *_: source(cases[model])) as fetch,
                  patch.object(archive, 'estimate_snow', side_effect=ValueError('Fehlende Testdaten'))):
                archive.run_comparison('18', self.now, path)
                before = path.read_bytes()
                archive.run_comparison('18', self.now.replace(minute=20), path)
                self.assertEqual(fetch.call_count, 3)
                self.assertEqual(path.read_bytes(), before)
            doc = json.loads(before)
            self.assertEqual(doc['targetDay'], self.day.isoformat())
            self.assertEqual(doc['snowForecast']['status'], 'unavailable')
            self.assertEqual(set(doc['models']), set(archive.MODELS))
            ordered = [doc['models'][key] for key in ('mosmix', 'icon', 'best-match', 'ifs')]
            self.assertEqual([item['status'] for item in ordered], ['ok'] * 4)
            self.assertEqual([len(item['rows']) for item in ordered], [288] * 4)
            energies = [item['powerKWh'] for item in ordered]
            self.assertEqual(energies, sorted(set(energies)))
            self.assertEqual(ordered[0]['weatherResolution'], {'quarters': 0, 'hours': 24})
            self.assertEqual(ordered[1]['weatherResolution'], {'quarters': 96, 'hours': 0})
            # The second day has three forecasts. It cannot enter the common ranking.
            partial = root / '2026-11-23' / path.name
            doc.update(targetDay='2026-11-24', captureDay='2026-11-23', capturedAtUtc='2026-11-23T17:02:00+00:00')
            doc['models']['best-match']['status'] = 'unavailable'
            archive.save_json(partial, doc)
            data = comparison.summarize({'dailyEnergy': [
                {'day': self.day.isoformat(), 'energyKWh': energies[2], 'status': 'reported'},
                {'day': '2026-11-24', 'energyKWh': 0, 'status': 'reported'}
            ]}, root)
            self.assertEqual(data['06']['actualDays'], 2)
            self.assertIsNone(data['06']['scores']['all']['mosmix'])
            self.assertEqual(data['18']['commonDays'], [self.day.isoformat()])
            scores = data['18']['scores']['all']
            self.assertEqual(len(scores), 15)
            self.assertEqual(scores['mosmix']['days'], 1)
            self.assertEqual(scores['best-match']['MAE'], 0)
            self.assertAlmostEqual(scores['mean:mosmix+best-match']['MAE'], (energies[2] - energies[0]) / 2)
            self.assertEqual(data['18']['dailyValues'][0]['nearestSingleModels'], ['best-match'])
            self.assertEqual(data['18']['dailyValues'][1]['nearestSingleModels'], ['mosmix'])

    def test_snow_ranked_separately_and_missing_observation_is_unknown(self):
        actual = {'day': self.day.isoformat(), 'energyKWh': .616, 'status': 'reported'}
        snow_observation = {'day': self.day.isoformat(), 'condition': 'snow_on_modules'}
        record = {
            'capturedAtUtc': self.now.isoformat(), 'physicalHash': 'fixture',
            'models': {key: {'status': 'ok', 'powerKWh': 14, 'indicators': {}} for key in archive.MODELS},
            'snowForecast': {'status': 'ok', 'expectedSnowOnModules': True},
        }
        def read(day, *_):
            return record if day in (self.day, self.day + timedelta(days=1)) else None
        with patch.object(comparison, 'read_archive', side_effect=read):
            data = comparison.summarize({'dailyEnergy': [actual], 'plantObservations': [snow_observation]})
        report = data['18']
        self.assertEqual(report['commonDays'], [])
        self.assertEqual(report['dailyValues'][0]['absoluteErrors']['icon'], 14 - .616)
        self.assertEqual(report['dailyValues'][0]['nearestSingleModels'], [])
        self.assertEqual(report['snowCheck']['hit'], ['2026-11-23'])
        self.assertEqual(report['snowCheck']['warningWithoutObservation'], ['2026-11-24'])
        self.assertEqual(report['snowCheck']['falseAlarm'], [])

    def test_overnight_snow_persists_until_thaw_and_can_carry_to_next_day(self):
        location = {'latitude': 47.7, 'longitude': 11.88}
        snow_end = int(datetime.combine(self.day, time(1), archive.LOCAL).timestamp())
        warm_start = int(datetime.combine(self.day, time(12), archive.LOCAL).timestamp())

        def fetch(issued, _):
            begin = int(issued.timestamp())
            return {
                'issuedAtUtc': issued.isoformat(),
                'rows': {
                    t: (1.2 if t == snow_end else 0, 3 if t in (warm_start, warm_start + 3600) else -2, 100)
                    for t in range(begin + 3600, begin + 48 * 3600, 3600)
                },
            }

        with patch.object(snow_rule, 'fetch_icon_run', side_effect=fetch):
            snow = snow_rule.estimate_snow(self.day, '06', location)
            self.assertTrue(snow['expectedSnowOnModules'])
            self.assertEqual(snow['nearZeroWindows'][-1]['endUtc'], warm_start + 3600)
            self.assertEqual(snow['carryState']['coldSnowCm'], 0)
            snow['carryState']['coldSnowCm'] = 1.5
            following = snow_rule.estimate_snow(self.day + timedelta(days=1), '06', location, snow)
            self.assertTrue(following['expectedSnowOnModules'])
            self.assertEqual(len(following['sourceRuns']), 2)


if __name__ == '__main__':
    unittest.main()
