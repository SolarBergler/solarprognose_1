"""DWD verwendet den zentralen Standort, ohne lokale oder Umgebungs-Overrides."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dwd',ROOT/'scripts/dwd_mosmix.py')
dwd=importlib.util.module_from_spec(spec);spec.loader.exec_module(dwd)

class CentralDwdLocation(unittest.TestCase):
    def test_published_location(self):
        c=json.loads((ROOT/'anlagenkonfiguration.json').read_text())['location']
        self.assertEqual((dwd.LAT,dwd.LON),(c['latitude'],c['longitude']))

    def test_changed_central_location_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'anlagenkonfiguration.json'
            for lat,lon in [(48.12,11.1),(-21.3,130.4)]:
                path.write_text(json.dumps({'schemaVersion':1,'location':{'latitude':lat,'longitude':lon}}))
                self.assertEqual(dwd.load_location(path),(lat,lon))
            for value in [True,None,'48',91,float('nan')]:
                path.write_text(json.dumps({'schemaVersion':1,'location':{'latitude':value,'longitude':11}}))
                with self.assertRaises(ValueError):dwd.load_location(path)
            path.unlink()
            with self.assertRaises(FileNotFoundError):dwd.load_location(path)

if __name__=='__main__':unittest.main()
