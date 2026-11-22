from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import archiviere_wettervergleich as archive
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

    def test_one_file_contains_independent_curves_and_retains_original(self):
        def source(value):
            return {'issuedAtUtc': '2026-11-22T12:00:00+00:00', 'weather': self.weather(value)}

        cases = {'icon': 110, 'ifs': 140, 'best-match': 130}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / '2026-11-22' / 'wettervergleich-18.json'
            with patch.object(archive, 'read_mosmix', return_value=source(80)), patch.object(
                archive, 'download_model', side_effect=lambda model, *_: source(cases[model]),
            ) as fetch:
                archive.run_comparison('18', self.now, path)
                before = path.read_bytes()
                archive.run_comparison('18', self.now.replace(minute=20), path)
                self.assertEqual(fetch.call_count, 3)
                self.assertEqual(path.read_bytes(), before)
            doc = json.loads(before)
            self.assertEqual(doc['targetDay'], self.day.isoformat())
            self.assertEqual(set(doc['models']), set(archive.MODELS))
            ordered = [doc['models'][key] for key in ('mosmix', 'icon', 'best-match', 'ifs')]
            self.assertEqual([item['status'] for item in ordered], ['ok'] * 4)
            self.assertEqual([len(item['rows']) for item in ordered], [288] * 4)
            energies = [item['powerKWh'] for item in ordered]
            self.assertEqual(energies, sorted(set(energies)))
            self.assertEqual(ordered[0]['weatherResolution'], {'quarters': 0, 'hours': 24})
            self.assertEqual(ordered[1]['weatherResolution'], {'quarters': 96, 'hours': 0})
            data = comparison.summarize({'dailyEnergy': [
                {'day': self.day.isoformat(), 'energyKWh': 0, 'status': 'reported'}
            ]}, root)
            self.assertEqual(data['06']['actualDays'], 1)
            self.assertIsNone(data['06']['commonThreeModels']['mosmix'])
            self.assertEqual(data['18']['commonWithReference']['all']['mosmix']['days'], 1)
            self.assertAlmostEqual(data['18']['commonWithReference']['all'][comparison.RULE]['MAE'], energies[0])


if __name__ == '__main__':
    unittest.main()
