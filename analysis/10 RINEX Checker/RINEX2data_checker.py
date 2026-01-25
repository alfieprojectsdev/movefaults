'''
NOTE TO USER: You may replace 'rinex2_folderPath' with the folder path of your RINEX2 data.
Its subfolders will also be included by this script. 
'''
'''
RINEX2 Data Checker
v. 1.1

Created by kurt
May 2024

This python script detects the day/s with and without RINEX2 file, 
i.e., w/ and w/o data, for a given station in a given year.
These days are written into a .txt file.
'''

import os
import sys


#Set folder/directory path containing the RINEX2 files.
print() #single space
print("Note: The subfolders within the given path will also be checked.")
print("Type 'exit' to close the script.\n\n")
 
rinex2_folderPath = r""   #<<---REPLACE WITH YOUR RINEX2 FOLDER PATH, INSIDE THE QUOTATION MARKS
    #Subfolders will also be included 

while len(rinex2_folderPath) == 0:
    rinex2_folderPath = input(r'Enter RINEX2 folder path here [\path]: ')
        
    if os.path.exists(rinex2_folderPath): 
        print('\n')
        break #path is existing, so proceed to next parts of the code
        
    elif rinex2_folderPath in ('exit', 'EXIT', 'break', 'BREAK'):
        print ('Closing program...')
        sys.exit() #to manually close the script, when 'exit' or 'break' is typed
        
    else: #if input path is not found, repeat input again
        print('\nRINEX2 folder path is not found. (awts) Please try again.\n')
        rinex2_folderPath = r"" #reset to empty string for re-input


#FUNCTIONS
def get_line_numbers_concat(numberList):
    '''
    Writes a list of numbers into range/s of numbers with dashes.

    Parameters
    ----------
    numberList : list
        List of numbers.

    Returns
    -------
    final_str : string
        Dashed range/s of the numbers.

    '''

    seq = []
    final = []
    last = 0

    for index, val in enumerate(numberList):

        if last + 1 == val or index == 0:
            seq.append(val)
            last = val
        else:
            if len(seq) > 1:
               final.append(str(seq[0]) + '---' + str(seq[len(seq)-1]))
            else:
               final.append(str(seq[0]))
            seq = []
            seq.append(val)
            last = val

        if index == len(numberList) - 1:
            if len(seq) > 1:
                final.append(str(seq[0]) + '---' + str(seq[len(seq)-1]))
            else:
                final.append(str(seq[0]))

    final_str = ', '.join(map(str, final))
    return final_str


def list_filesOnly_inFolder_andItsSubfolders(dir_path):
    '''
    Lists filenames, with file extension, of files only in a given folder/directory path 
    and its subdirectories.

    Parameters
    ----------
    path : string
        Folder/directory path.

    Returns
    -------
    filenames : list
        List containing filenames with extension of files only in the given folder and 
        its subfolders.

    '''
    filenames = []
    for (dir_path, dir_names, file_names) in os.walk(dir_path):
        filenames.extend(file_names)
    
    return filenames


def get_RINEX2FileNames_fromAList(filesList, station, year):
    '''
    From a list of filenames, extracts the RINEX2 files only of a given station in a given year.

    Parameters
    ----------
    filesList : list
        List of filenames with extension.
    station : string
        Station ID.
    year : string
        Last two digits of the year.

    Returns
    -------
    rinex2sList : list
        List containing filenames, with extension, of RINEX2 files of 
        a given station in a given year.

    '''
    rinex2sList = []
    for f in filesList:
        if f.startswith(station) and f.endswith('.'+year+'O'): #rinex file ends with big "O"
            rinex2sList.append(f)
        elif f.startswith(station) and f.endswith('.'+year+'o'): #rinex file ends with small "o"
            rinex2sList.append(f)
    #Given the RINEX2 filename format is <XXXXDOY0.YYO>
    
    return rinex2sList


#Print welcome texts
programTitle = 'RINEX2 Data Checker'
print('='*75)
print(programTitle)
print('='*75)
print('Input: RINEX2 O files')
print('Output: Text file')
print('Current directory of RINEX2 files: ' + str(rinex2_folderPath))
print('='*75)

print('\nChecks the completeness of RINEX2 data of a given station in a given year.\n')


#INPUTS
#Get inputs here for the a) station ID and b) year.
sta_input = input('Enter station ID here [ABCD]: ')
if len(sta_input) == 4:
    sta = sta_input.upper()

yr = input('Enter last 2 digits of year here [YY]: ')
if int(yr) > 0 and len(yr) > 3: #to get last 2 digits only if 4 digits are typed
    yr = yr[2:4]
    
#if statement to spell out year from 1980s to 2070s
if int(yr) >= 80:
    yearYYYY = '19'+yr
else:
    yearYYYY = '20'+yr
        
print('\nNow processing...')


#PROCESSING
#List filenames of files ONLY in the folder/directory and its subdirectories.
filenames_list = list_filesOnly_inFolder_andItsSubfolders(rinex2_folderPath)

   
#List RINEX2 filenames of a given station in a given year.
rinex2s = get_RINEX2FileNames_fromAList(filenames_list, sta, yr)

#List day of year numbers from the RINEX2 filenames list
#Given file name format is <XXXXDOY0.extension> 
rinex2s_dayOfYears_list = [int(i[4:7]) for i in rinex2s]
rinex2s_dayOfYears = list(set(rinex2s_dayOfYears_list)) #put in set to make sure DOY values are unique, i.e. no duplication
rinex2s_dayOfYears.sort() #sorts the day of year numbers from lowest to highest.

#Get start and end of day count for the given year.
start = 1

if int(yearYYYY) % 4 == 0: #if leap year
    end = 366
else:
    end = 365 #for the usual 365 days per year
 
completeNumbers_from1ToEndOfYear = range(start, end + 1) #from 1 to 365 or 366

#List RINEX2 day gaps.
gaps = list(set(completeNumbers_from1ToEndOfYear).difference(rinex2s_dayOfYears))
gaps.sort() #sort from lowest to highest, since set elements are of random order


#OUTPUT
#Create a .txt file with the days with RINEX2 and also those without
with open('gaps-'+sta+'-'+yearYYYY+'.txt', 'w+') as f: #output filename as gaps-station-year

    #write year header at top of txt file
    f.write('-'*47+'\n')
    f.write('Year: '+yearYYYY+'\n')
    f.write('-'*47+'\n')
    f.write('\n')
    
    #station ID header in the text file
    f.write('-'*47+'\n')
    f.write('Station: '+sta+'\n')
    f.write('-'*47+'\n')
    #f.write('\n')

    f.write('Number of days with data: '+str(end-len(gaps))+' out of '+str(end)+' days.\n') 
    #writes number of days with data at the start of the .txt file

    if len(rinex2s_dayOfYears) > 0:
        f.write('Day/s WITH data for station '+sta+' in '+yearYYYY+':\n')
        f.write(get_line_numbers_concat(rinex2s_dayOfYears))
    
    f.write('\n\n') #double blank space
   
    f.write('Number of days with NO data: '+str(len(gaps))+' out of '+str(end)+' days.\n') 
    #writes number of days with NO data

    if len(gaps) > 0:
        f.write('Day/s with NO data for station '+sta+' in '+yearYYYY+':\n')
        f.write(get_line_numbers_concat(gaps))
    
f.close()


print('\nDONE.')
