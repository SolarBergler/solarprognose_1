import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from baue_modulnahprofil import utm32,grid_convergence_degrees,true_north_bins
import numpy as np

class NearAzimuth(unittest.TestCase):
    def test_geographic_directions(self):
        lat,lon=47.6978583,11.8804056
        g=grid_convergence_degrees(lat,lon)
        self.assertAlmostEqual(grid_convergence_degrees(lat,9),0,places=7)
        self.assertTrue(2.12<g<2.14)
        south=np.array(utm32(lat-.0001,lon));north=np.array(utm32(lat+.0001,lon))
        east=np.array(utm32(lat,lon+.0001));west=np.array(utm32(lat,lon-.0001))
        vectors=np.array([north-south,east-west,south-north,west-east])
        self.assertEqual(true_north_bins(vectors[:,0],vectors[:,1],g).tolist(),[0,180,360,540])

if __name__=='__main__':unittest.main()
