import os, glob, math, sys
print('Running: continuous_v6...')

person = input('Your 4-character name: ')
person = person.upper()

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

        flow = input('Input action. \n1 = Go back to top, 2 = Trimble teqc\n')
        if flow == '1':
            start()
        elif flow == '2':
            print('\nTRIMBLE TEQC')
            rinex()


    def rinex():
        mo = input('\nSite name: ')
        mo = mo.upper()
        for teqc in glob.glob('*.tgd') or glob.glob('*.dat'):
            os.system('teqc -tr d -O.dec 30 -O.o MOVEFaultsProject -O.ag PHIVOLCS -O.r ' +person+' -O.mo '+mo+' -O.mn '+mo+' -O.pe 0 0 0 +C2 +obs + -tbin 1d '+mo+' '+teqc) #added +C2 on 12.09.2020, added agency and observer on 10.03.2025
            print('    Converting ' + teqc + '...') 

        tow = input('\nType "E" to go back to top or "R" to retry: ')
        tow = tow.upper()
        if tow == 'E':
            start()
        elif tow == 'R':
            return()

    def leica():
        mo = input('\nSite name: ')
        mo = mo.upper()
        fe = input('Input first character file extension: ')
        for teqc in glob.glob('*.'+fe+'??'):
            os.system('teqc -lei mdb -O.dec 30 -O.o MOVEFaultsProject -O.ag PHIVOLCS -O.r ' +person+' -O.mo '+mo+' -O.mn '+mo+' -O.pe 0 0 0 +C2 +obs + -tbin 1d '+mo+' '+teqc) #added +C2 for Bernese 5.2 processing, added agency and observer, and data format
 

        tow = input('\nType "E" to go back to top or "R" to retry: ')
        tow = tow.upper()
        if tow == 'E':
            start()
        elif tow == 'R':
            return()

        
    flow = input('Input action. \n1 = start runpkr00, 2 = Trimble teqc, 3 = Leica teqc\n')
    if flow == '1':
        runpk()
    elif flow == '2':
        print('\nTRIMBLE TEQC')
        rinex()
    elif flow == '3':
        print('\nLEICA TEQC')
        leica()
    
    
    rinex()
    runpk()    
start()        #this is the start of the program because it called start()
