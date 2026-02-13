"""
Core utility functions for the bootstrapping analysis.
Extracted from bootstrap_v1.py and bootstrap_v2.py.
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_histogram(parameters_file='parameters_rchi.txt', figsize=(8,6), show=True):
    """
    Plots histograms of the parameters and calculates confidence intervals.
    """
    if not os.path.exists(parameters_file):
        print(f"Error: {parameters_file} not found.")
        return

    # Use lists to store data
    east = []
    depth = []
    width = []
    dip = []
    rate = []
    slip = []

    try:
        with open(parameters_file) as f:
            lines = f.readlines()
            for line in lines:
                parameters = line.strip().split('\t')
                if len(parameters) < 7:
                    continue # Skip invalid lines
                east.append(float(parameters[0]))
                depth.append(int(parameters[1]))
                width.append(int(parameters[2]))
                dip.append(int(parameters[3]))
                rate.append(int(parameters[5]))
                slip.append(float(parameters[6]))
    except Exception as e:
        print(f"Error reading parameters file: {e}")
        return

    if not east:
        print("No valid data found in parameters file.")
        return

    # Calculate 68% confidence interval
    # Lower bound
    east_lower = np.quantile(east, q=0.16)
    depth_lower = np.quantile(depth, q=0.16)
    width_lower = np.quantile(width, q=0.16)
    dip_lower = np.quantile(dip, q=0.16)
    rate_lower = np.quantile(rate, q=0.16)
    slip_lower = np.quantile(slip, q=0.16)
    print('Lower bound of the 68% confidence interval ' +
          f'{east_lower} {depth_lower} {width_lower} {dip_lower} {rate_lower} {slip_lower}')

    # Upper bound
    east_upper = np.quantile(east, q=0.84)
    depth_upper = np.quantile(depth, q=0.84)
    width_upper = np.quantile(width, q=0.84)
    dip_upper = np.quantile(dip, q=0.84)
    rate_upper = np.quantile(rate, q=0.84)
    slip_upper = np.quantile(slip, q=0.84)
    print('Upper bound of the 68% confidence interval ' +
          f'{east_upper} {depth_upper} {width_upper} {dip_upper} {rate_upper} {slip_upper}')

    if not show:
        return

    plt.figure(figsize=figsize)

    # Helper to plot subplot
    def plot_subplot(index, data, label, lower, upper):
        plt.subplot(2, 3, index)
        plt.hist(data, bins=10, color='deepskyblue', edgecolor='black')
        plt.xlabel(label)
        plt.axvline(lower, color='r', linestyle='--')
        plt.axvline(upper, color='r', linestyle='--')

    plot_subplot(1, east, 'East', east_lower, east_upper)
    plot_subplot(2, depth, 'Depth', depth_lower, depth_upper)
    plot_subplot(3, width, 'Width', width_lower, width_upper)
    plot_subplot(4, dip, 'Dip', dip_lower, dip_upper)
    plot_subplot(5, rate, 'Rate', rate_lower, rate_upper)
    plot_subplot(6, slip, 'Slip', slip_lower, slip_upper)

    plt.tight_layout()
    plt.show()

def run_bootstrap_simulation(
    n_samples,
    sample_size,
    ref_station_data,
    ref_station_index,
    csv_file='PHm.csv',
    skiprows=None,
    output_wrms='parameters_wrms.txt',
    output_rchi='parameters_rchi.txt',
    matlab_engine_setup_func=None
):
    """
    Runs the bootstrap simulation.

    Args:
        n_samples (int): Number of bootstrap samples.
        sample_size (int): Size of each sample.
        ref_station_data (dict): Data for the reference station row to append.
        ref_station_index (list): Index for the reference station row.
        csv_file (str): Path to the CSV file.
        skiprows (list, optional): Rows to skip when reading CSV. Defaults to [1].
        output_wrms (str): Output file for WRMS parameters.
        output_rchi (str): Output file for RCHI parameters.
        matlab_engine_setup_func (callable, optional): Function to setup matlab engine path/env.
    """
    if skiprows is None:
        skiprows = [1]

    if matlab_engine_setup_func:
        matlab_engine_setup_func()

    try:
        import matlab.engine  # noqa: F401
    except ImportError:
        pass # Handle or log if needed, but assuming environment is correct for real runs

    try:
        df = pd.read_csv(csv_file, skiprows=skiprows)
    except FileNotFoundError:
        print(f"Error: {csv_file} not found.")
        return

    for _i in range(n_samples):
        # 1. Create bootstrap samples
        bootstrap_sample = df.sample(sample_size, replace=True)

        # Add the reference station row
        ref_df = pd.DataFrame(ref_station_data, index=ref_station_index)

        # Use concat instead of append (which is deprecated/removed in pandas 2.0+)
        bootstrap_concat = pd.concat([bootstrap_sample, ref_df])

        print(bootstrap_concat)

        # Write samples to text file for MATLAB
        bootstrap_concat.to_csv('PHm.txt', sep='\t', index=False)

        # 2. Run MATLAB scripts
        _run_matlab_script('velproj_loop')
        _run_matlab_script('makeG_2ds_v3_loop')

        # 3. Process results
        _get_parameters_wrms(output_wrms)
        _get_parameters_rchi(output_rchi)

def _run_matlab_script(script_name):
    """Runs a MATLAB script using the engine."""
    try:
        import matlab.engine
        eng = matlab.engine.start_matlab()
        getattr(eng, script_name)(nargout=0)
        eng.quit()
    except Exception as e:
        print(f"Error running MATLAB script {script_name}: {e}")

def _get_parameters_wrms(output_file):
    """Processes parameters.txt and writes to parameters_wrms.txt"""
    try:
        if not os.path.exists('parameters.txt'):
             return

        df = pd.read_csv('parameters.txt', delimiter=' ')

        convert_df = {"East":str, "Depth":int, "Width":int, "Dip":int,
                      "Residual":float, "Rate":int, "Slip":float,
                      "Reduced chi2":float, "Chi2":float}

        try:
             df = df.astype(convert_df)
        except Exception:
             pass

        if 'Slip' in df.columns and 'Rate' in df.columns:
            new_df = df[df['Slip'] <= df['Rate']]
        else:
            new_df = df

        if new_df.empty or 'Residual' not in new_df.columns:
            return

        min_wrms = new_df['Residual'].min()
        print(min_wrms)

        with open("parameters.txt") as lines:
            next(lines) # Skip header
            for line in lines:
                x = line.split()
                if len(x) > 4 and float(x[4]) == min_wrms:
                    with open(output_file, 'a+') as f:
                        f.write('\t'.join(x[:9]) + '\n')
    except Exception as e:
        print(f"Error in _get_parameters_wrms: {e}")

def _get_parameters_rchi(output_file):
    """Processes parameters.txt and writes to parameters_rchi.txt"""
    try:
        num = 1
        if not os.path.exists('parameters.txt'):
             return

        df = pd.read_csv('parameters.txt', delimiter=' ')
        convert_df = {"East":str, "Depth":int, "Width":int, "Dip":int,
                      "Residual":float, "Rate":int, "Slip":float,
                      "Reduced chi2":float, "Chi2":float}
        try:
            df = df.astype(convert_df)
        except Exception:
            pass

        if 'Slip' in df.columns and 'Rate' in df.columns:
            new_df = df[df['Slip'] <= df['Rate']]
        else:
            new_df = df

        if new_df.empty or 'Reduced chi2' not in new_df.columns:
            return

        idx = (new_df['Reduced chi2'] - num).abs().argsort()[:1]
        rchi = new_df.iloc[idx]

        print(rchi)

        with open(output_file, 'a+') as file:
            rchi.to_csv(file, sep='\t', header=False, index=False)

    except Exception as e:
        print(f"Error in _get_parameters_rchi: {e}")
