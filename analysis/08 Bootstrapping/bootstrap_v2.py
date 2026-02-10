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
4. Set the number of samples = N (line 141) and sample size (line 148) in this script.
    Sample size depends on your sites to be used in modelling excluding
    the reference station.
5. In line 154, put the reference station's ID, coordinates, etc... and change index
    to the total number of sites [sample size+1 (including the reference station)]
6. OUTPUTS: parameters_rchi.txt, and parameters_wrms.txt
7. To plot the histogram, remove the hash symbol # marked at plot() and put one at
    the beginning of start(). Run the script again.
8. Save the figure and close.
9. The confidence intervals will be displayed on the screen.

-CJVC created on 09/2023; modified on 05/2024
'''

#scientific computing
import pandas as pd  #pandas dataframe
import numpy as np

import sys #use if having issues of not finding module
sys.path.append("C:\\Python\\Python38\\Lib\\site-packages\\matlabengineforpython-9.9.0.2037887.dist-info") #use if having issues of not finding module, change according to your path
import matlab.engine
            
#plot graphs
import matplotlib.pyplot as plt           


def plot():
    #histogram
    east=[]
    depth=[]
    width=[]
    dip=[]
    rate=[]
    slip=[]
    
    with open('parameters_rchi.txt') as f:
        lines=f.readlines()
        for line in lines:
            parameters=line.split('\t')
            east.append(float(parameters[0]))
            depth.append(int(parameters[1]))
            width.append(int(parameters[2]))
            dip.append(int(parameters[3]))
            rate.append(int(parameters[5]))
            slip.append(float(parameters[6]))

    #get 95% confidence interval
    #get the lower bound of the confidence interval
    #east_lower=np.quantile(east, q=0.025)
    #depth_lower=np.quantile(depth, q=0.025)
    #width_lower=np.quantile(width, q=0.025)
    #dip_lower=np.quantile(dip, q=0.025)
    #rate_lower=np.quantile(rate, q=0.025)
    #slip_lower=np.quantile(slip, q=0.025)
    #print('Lower bound of the 95% confidence interval '+str(east_lower)+' '+str(depth_lower)+' '+str(width_lower)+' '+str(dip_lower)+' '+str(rate_lower)+' '+str(slip_lower))
    
    #get the upper bound of the confidence interval
    #east_upper=np.quantile(east, q=0.975)
    #depth_upper=np.quantile(depth, q=0.975)
    #width_upper=np.quantile(width, q=0.975)
    #dip_upper=np.quantile(dip, q=0.975)
    #rate_upper=np.quantile(rate, q=0.975)
    #slip_upper=np.quantile(slip, q=0.975)
    #print('Upper bound of the 95% confidence interval '+str(east_upper)+' '+str(depth_upper)+' '+str(width_upper)+' '+str(dip_upper)+' '+str(rate_upper)+' '+str(slip_upper))
    
    #get 68% confidence interval
    #get the lower bound of the confidence interval
    east_lower=np.quantile(east, q=0.16)
    depth_lower=np.quantile(depth, q=0.16)
    width_lower=np.quantile(width, q=0.16)
    dip_lower=np.quantile(dip, q=0.16)
    rate_lower=np.quantile(rate, q=0.16)
    slip_lower=np.quantile(slip, q=0.16)
    print('Lower bound of the 68% confidence interval '+str(east_lower)+' '+str(depth_lower)+' '+str(width_lower)+' '+str(dip_lower)+' '+str(rate_lower)+' '+str(slip_lower))
    
    #get the upper bound of the confidence interval
    east_upper=np.quantile(east, q=0.84)
    depth_upper=np.quantile(depth, q=0.84)
    width_upper=np.quantile(width, q=0.84)
    dip_upper=np.quantile(dip, q=0.84)
    rate_upper=np.quantile(rate, q=0.84)
    slip_upper=np.quantile(slip, q=0.84)
    print('Upper bound of the 68% confidence interval '+str(east_upper)+' '+str(depth_upper)+' '+str(width_upper)+' '+str(dip_upper)+' '+str(rate_upper)+' '+str(slip_upper))

    plt.figure(figsize=(8,6))
    
    plt.subplot(231)
    plt.hist(east, bins=10, color='deepskyblue', edgecolor='black')
    plt.xlabel('East')
    plt.axvline(east_lower,color='r',linestyle='--')
    plt.axvline(east_upper,color='r',linestyle='--')
    
    plt.subplot(232)
    plt.hist(depth, bins=10, color='deepskyblue', edgecolor='black')
    plt.xlabel('Depth')
    plt.axvline(depth_lower,color='r',linestyle='--')
    plt.axvline(depth_upper,color='r',linestyle='--')
    
    plt.subplot(233)
    plt.hist(width, bins=10, color='deepskyblue', edgecolor='black')
    plt.xlabel('Width') 
    plt.axvline(width_lower,color='r',linestyle='--')
    plt.axvline(width_upper,color='r',linestyle='--')

    plt.subplot(234)
    plt.hist(dip, bins=10, color='deepskyblue', edgecolor='black')
    plt.xlabel('Dip') 
    plt.axvline(dip_lower,color='r',linestyle='--')
    plt.axvline(dip_upper,color='r',linestyle='--')

    plt.subplot(235)
    plt.hist(rate, bins=10, color='deepskyblue', edgecolor='black')
    plt.xlabel('Rate') 
    plt.axvline(rate_lower,color='r',linestyle='--')
    plt.axvline(rate_upper,color='r',linestyle='--')

    plt.subplot(236)
    plt.hist(slip, bins=10, color='deepskyblue', edgecolor='black')
    plt.xlabel('Slip')
    plt.axvline(slip_lower,color='r',linestyle='--')
    plt.axvline(slip_upper,color='r',linestyle='--')
    
    plt.tight_layout()
    plt.show()

def start(n_samples=100):
    
    #population (load data into a pandas dataframe) and skip first data row
    df=pd.read_csv('PHm.csv',skiprows=[1])
    
    for i in range(n_samples):
        #set sample size
        def create_boothstrap_samples(sample_size=8):

            #draw a bootstrap sample of size n
            bootstrap_sample=df.sample(sample_size, replace=True)
            
            #add the skipped row back
            df1=pd.DataFrame({"sites":["VIGN"],"Ecoord":[83978.2690],"Ncoord":[-673280.2167],"height":[0],"velocity":[0],"azimuth":[0],"Vu":[0],"hgt":[0],"erreast":[0.14],"errnorth":[0.01]}, index=[9])
            bootstrap_concat=pd.concat([bootstrap_sample, df1])
            
            print(bootstrap_concat)
    
            #write samples in text
            bootstrap_concat.to_csv('PHm.txt', sep='\t', index=False)
    
        def velprojm():
            #run .m file in python
            eng = matlab.engine.start_matlab()
            eng.velproj_loop(nargout=0)
            eng.quit()
    
        def makeG_2dm():
            #run .m file in python
            eng = matlab.engine.start_matlab()
            eng.makeG_2ds_v3_loop(nargout=0)
            eng.quit()
            
        def get_parameters_wrms():
            #parameters (load data into a pandas dataframe) and skip first data row
            df=pd.read_csv('parameters.txt',delimiter=' ')
            convert_df=dtype={"East":str,"Depth":int,"Width":int,"Dip":int,"Residual":float,"Rate":int,"Slip":float,"Reduced chi2":float,"Chi2":float}
            df=df.astype(convert_df)
            new_df=df[df['Slip'] <= df['Rate']]
            min_wrms=new_df['Residual'].min()
            print(min_wrms)
            with open("parameters.txt") as lines:
                for i in range(1):
                    next(lines)
                for line in lines:
                    x = line.split()
                    if float(x[4])==min_wrms:
                        f = open("parameters_wrms.txt", 'a+')
                        f.write(x[0]+'\t'+x[1]+'\t'+x[2]+'\t'+x[3]+'\t'+x[4]+'\t'+x[5]+'\t'+x[6]+'\t'+x[7]+'\t'+x[8]+'\n')
                        f.close()
                        
        def get_parameters_rchi():
            #parameters (load data into a pandas dataframe) and skip first data row
            num=1
            df=pd.read_csv('parameters.txt',delimiter=' ')
            convert_df=dtype={"East":str,"Depth":int,"Width":int,"Dip":int,"Residual":float,"Rate":int,"Slip":float,"Reduced chi2":float,"Chi2":float}
            df=df.astype(convert_df)
            new_df=df[df['Slip'] <= df['Rate']]
            rchi=new_df.iloc[(new_df['Reduced chi2']-num).abs().argsort()[:1]]
            print(rchi)
            #rchi=rchi.to_string(index=False)
            with open('parameters_rchi.txt','a+') as file:
                rchi.to_csv(file,sep='\t',header=False,index=False)
                        
        create_boothstrap_samples()
        velprojm()
        makeG_2dm()
        get_parameters_wrms()
        get_parameters_rchi()
        
start() #to create samples and run matlab
#plot() #to plot histogram
