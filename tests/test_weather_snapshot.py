"""Checks that only original, live forecast weather is frozen in archive records."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from weather_snapshot import build_snapshot

class WeatherSnapshotTest(unittest.TestCase):
    def setUp(self):
        start=datetime(2026,11,19,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()
        self.weather={'hourly':{
            'time':[start+i*3600 for i in range(48)],
            'direct_normal_irradiance':[100]*48,
            'diffuse_radiation':[20]*48,
            'shortwave_radiation':[120]*48},
            'minutely_15':{
                'time':[start+i*900 for i in range(96)],
                'direct_normal_irradiance':[100]*96,
                'diffuse_radiation':[20]*96,
                'shortwave_radiation':[120]*96}}
        self.diag={'source':'open-meteo','notLive':False,'issuedAt':1795000000000}
    def build(self):
        return build_snapshot(self.weather,self.diag,'2026-11-19','06','modelhash','confighash')
    def test_valid_forecast_preserves_original_hourly_and_quarterly_values(self):
        result=self.build()
        self.assertEqual(result['weather'],self.weather)
        self.assertEqual(result['configurationHash'],'confighash')
        self.assertEqual(result['sourceIssuedAtMs'],1795000000000)
    def test_dwd_is_supported(self):
        self.diag['source']='dwd'
        self.assertEqual(self.build()['source'],'dwd')
    def test_cached_data_is_rejected(self):
        self.diag['notLive']=True
        with self.assertRaises(ValueError):self.build()
    def test_missing_radiation_is_rejected(self):
        del self.weather['hourly']['diffuse_radiation']
        with self.assertRaises(ValueError):self.build()
    def test_different_forecast_day_is_rejected(self):
        with self.assertRaises(ValueError):
            build_snapshot(self.weather,self.diag,'2026-11-22','06','modelhash','confighash')
    def test_incorrect_array_length_is_rejected(self):
        self.weather['hourly']['shortwave_radiation']=[0]
        with self.assertRaises(ValueError):self.build()
    def test_non_monotonic_time_is_rejected(self):
        self.weather['hourly']['time'][1]=self.weather['hourly']['time'][0]
        with self.assertRaises(ValueError):self.build()
    def test_hourly_only_weather_is_valid(self):
        self.weather.pop('minutely_15')
        self.assertEqual(self.build()['schema'],1)

if __name__=='__main__':
    unittest.main()
