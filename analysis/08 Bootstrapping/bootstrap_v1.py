'''
The purpose is to compute the uncertainties of the fault parameters by applying
the bootstrap method of resampling GPS data (with replacement) to generate synthetic
data sets. The datasets are run with velproj_loop.m and makeG_2ds_v3_loop.m and get
the fault parameters with the least residual value and the reduced chi-squared closest to 1.

How to use:
1. Prepare the GPS data in the PHm.csv file (similar to PHm.prn).
2. Open velproj_loop.m and input the filename (name of data file,
    Az [direction of projection (start from N, CW is + (0-180)],
    ref (coordinate of reference station/point on the fault)
    and width of profile (lines 15-18).
3. Set the upper and lower limits of the parameters in the makeG_2ds_v3_loop.m file.
   These are lines 30-35 for east, north, depth, width, dip, and block motion/slip.
4. Set the number of samples = N (line 139) and sample size (line 146) in this script.
    Sample size depends on your sites to be used in modelling excluding
    the reference station.
5. In line 152, put the reference station's ID, coordinates, etc... and change index
    to the total number of sites [sample size+1 (including the reference station)]
6. OUTPUTS: parameters_rchi.txt, and parameters_wrms.txt
7. To plot the histogram, remove the hash symbol # marked at plot() and put one at
    the beginning of start(). Run the script again.
8. Save the figure and close.
9. The confidence intervals will be displayed on the screen.

-CJVC 09/2023
'''

import bootstrap_utils


def plot():
    bootstrap_utils.plot_histogram()

def start(n_samples=10):

    #population (load data into a pandas dataframe) and skip first data row
    # In v1, the reference station was at index 13 and hardcoded.

    ref_station_data = {
        "sites":["IBAZ"],
        "Ecoord":[42173.1739],
        "Ncoord":[-919208.7877],
        "height":[-67087.8326],
        "velocity":[0],
        "azimuth":[0],
        "Vu":[0],
        "hgt":[0],
        "erreast":[0],
        "errnorth":[0]
    }

    bootstrap_utils.run_bootstrap_simulation(
        n_samples=n_samples,
        sample_size=12,
        ref_station_data=ref_station_data,
        ref_station_index=[13],
        csv_file='PHm.csv',
        skiprows=[1]
    )

start() #to create samples and run matlab
#plot() #to plot histogram
