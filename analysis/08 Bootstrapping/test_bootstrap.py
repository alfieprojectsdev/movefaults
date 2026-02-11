import unittest
import sys
import os
import shutil
from unittest.mock import MagicMock, patch
import pandas as pd

class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self.test_dir = 'test_bootstrap_output'
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)

        # Create dummy PHm.csv
        self.csv_file = os.path.join(self.test_dir, 'PHm.csv')
        with open(self.csv_file, 'w') as f:
            f.write("sites,Ecoord,Ncoord,height,velocity,azimuth,Vu,hgt,erreast,errnorth\n")
            # Line 1 (skipped by skiprows=[1])
            f.write("SKIP,0,0,0,0,0,0,0,0,0\n")
            # Data lines
            f.write("SITE1,100,200,10,1,10,0,0,0.1,0.1\n")
            f.write("SITE2,110,210,11,1,10,0,0,0.1,0.1\n")

        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Add source dir to path
        self.source_dir = os.path.join(self.original_cwd, 'analysis/08 Bootstrapping')
        if self.source_dir not in sys.path:
            sys.path.append(self.source_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_run_simulation(self):
        import bootstrap_utils

        # Mock matlab.engine
        mock_matlab = MagicMock()
        mock_eng = MagicMock()
        mock_matlab.start_matlab.return_value = mock_eng

        # Setup mock side effect to create parameters.txt when matlab scripts are "run"
        def side_effect_velproj(*args, **kwargs):
            # Create a dummy parameters.txt
            with open('parameters.txt', 'w') as f:
                # Header space delimited, with quotes for "Reduced chi2" as MATLAB writetable does
                f.write('East Depth Width Dip Residual Rate Slip "Reduced chi2" Chi2\n')
                # Write a matching row. Min residual 0.5.
                f.write("100 10 20 30 0.5 5 2.0 1.0001 10.0\n")
                f.write("100 10 20 30 0.8 5 2.0 1.0005 12.0\n")

        mock_eng.velproj_loop.side_effect = side_effect_velproj

        # Patch matlab module in sys.modules
        mock_matlab_pkg = MagicMock()
        mock_matlab_pkg.engine = mock_matlab
        with patch.dict('sys.modules', {'matlab': mock_matlab_pkg, 'matlab.engine': mock_matlab}):

            ref_data = {
                "sites":["REF"], "Ecoord":[0], "Ncoord":[0], "height":[0],
                "velocity":[0], "azimuth":[0], "Vu":[0], "hgt":[0],
                "erreast":[0], "errnorth":[0]
            }

            bootstrap_utils.run_bootstrap_simulation(
                n_samples=2,
                sample_size=2,
                ref_station_data=ref_data,
                ref_station_index=[99],
                csv_file='PHm.csv',
                skiprows=[1],
                output_wrms='out_wrms.txt',
                output_rchi='out_rchi.txt'
            )

            # Verify PHm.txt created
            self.assertTrue(os.path.exists('PHm.txt'))

            # Verify outputs
            self.assertTrue(os.path.exists('out_wrms.txt'))
            self.assertTrue(os.path.exists('out_rchi.txt'))

            # Check content of wrms
            with open('out_wrms.txt', 'r') as f:
                content = f.read()
                lines = content.strip().split('\n')
                # Expect 2 lines because n_samples=2
                self.assertEqual(len(lines), 2)
                # Check data format (tab separated)
                self.assertIn("100\t10\t20\t30\t0.5", lines[0])

if __name__ == '__main__':
    unittest.main()
