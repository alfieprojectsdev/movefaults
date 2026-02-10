import os, glob, math, subprocess
print('Running: campv6.exe')
print('---------------------------------------------------------------------------')
print('\nThis program runs runpkr00 and teqc on indicated files in a folder in the Documents folder')
print('Press CTRL + C to terminate program. Type EXIT to exit folder.')

def start():    #while defining, the program does not yet recognize it unless called
    
    homepath = os.path.expanduser(os.getenv('USERPROFILE')) 
    inputdir = homepath + "\\Documents\\" + input('\nInput Documents Folder: ')
    if os.path.exists(inputdir) == False:
        print('\n ERROR: Folder not found! Please recheck if folder is in Documents.')
        start()
    elif os.path.exists(inputdir) == True:
        os.chdir(inputdir)
    
    def runpk():
        print("\nStarting runpkr00.exe...")
        for rnx in glob.glob('*.t0*'):
                os.system('runpkr00 -g -d ' + rnx) #.t0 files are now converted to .dat (added '-g' on 06.13.2019)
                print("        Converting " + rnx + " to .DAT/.TGD...")

    def rinex():
        code = 1
        while code == 1:
            teqc = input('\nInput file name: ')
            teqc = teqc.upper()
            if teqc == 'EXIT':
                print('  Exiting folder...')
                start()
            elif os.path.isfile(teqc) == False:
                print('    *** Error filename! ***')
            elif os.path.isfile(teqc) == True:
                print('\n      --==*** Additional info for:   ' + teqc + '   ***==--')
                mo = input('    Site name: ')
                ask = input('    Antenna Type: \n    1 = TRM41249.00 , 2 = TRM57971.00, 3 = TRM115000.00 :  ') #added TRM115000.00 on 07.29.2019 for the newly purchased GPS antenna
                if ask == '1':
                    at = 'TRM41249.00'
                elif ask == '2':
                    at = 'TRM57971.00'
                elif ask == '3':
                    at = 'TRM115000.00'
                pe = input('    Average height: ')
                pe1 = math.sqrt(float(pe)*float(pe)-0.16981*0.16981) - 0.04435
                subprocess.run(['teqc', '-tr', 'd', '-O.dec', '30', '-O.o', 'MOVEFaultsProject', '-O.ag', 'PHIVOLCS', '-O.mo', mo, '-O.at', at, '-O.pe', ("%.4f" %pe1), '0', '0', '+C2', '+obs', '+', '-tbin', '1d', mo, teqc]) #added +C2 on 12.09.2020, added agency and observer on 10.03.2025
                
                
    flow = input('Start with runpkr00? \nY = start runpkr00, N = skip to teqc: ')
    flow = flow.upper()
    if flow == 'Y':
        runpk()
    elif flow == 'N':
        print('\nSkipping runpkr00. Going to teqc...')
        rinex()
    
    rinex()
    runpk()    
start()        #this is the start of the program because it called start()
