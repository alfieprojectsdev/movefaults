#Date created: March 2020

import glob, os, numpy, time
import pymap3d

def start():

		def getxyz():
				print('\t ======================================================================== \n')
				print('\t \t \t \t WELCOME GPS TEAM! :) \n')
				print('\t List geocentric ECEF (XYZ) coordinates from the CRD files \n')
				print('\t About this version: The origin (0,0,0) is at the center of mass of the \n \t \t \t \t \t Earth.')
				print('\t \t INPUT: CRD files \t \t OUTPUT: PLOT files \n')
				print('\t ======================================================================== \n')
				input('\t Press Enter to continue \n')
				print('\t ========================= Getting XYZ coordinates ====================== \n')
				for files in glob.glob('*.CRD'):
						with open(files) as lines:
								for i in range(5):
										next(lines)
								for line in lines:
										x = line.split()
										if len(line.split()) == 7:
												f = open('XYZ', 'a+')
												f.write('{:.4s}  {:.5s}  {:>13}  {:>13}  {:>13}\n'.format(x[1], files[2:7], x[3], x[4], x[5]))
												f.close()
												print('\t ' +x[1]+' '+files[2:7])	
										elif len(line.split()) == 6:
												pass
										else:
												f = open('XYZ', 'a+')
												f.write('----------------------------------------------------------\n')
												f.close()
						
		def sites():
				print('\n \t ======================= Creating site files... ========================= \n')
				
				sname = []
				
				for lines in open('XYZ'):
						x = lines.split()
						if len(x[0]) == 4:
								if len(sname) == 0:
										sname.append(x[0])
								elif len(sname) == 1:
										del sname[0]
										sname.append(x[0])
								open(sname[0], 'a').write(x[1]+'  '+x[2]+'  '+x[3]+'  '+x[4])
								open(sname[0], 'a').write('\n')
						
		def plotfiles():
				input('\t To create PLOT files, press Enter')
				
				print('\t Running... \n')
				
				alldata = []
				
				dirName = 'PLOTS'
				if not os.path.exists(dirName):
						os.mkdir(dirName)
						print('\t Directory', dirName, 'created')
				else:
						print('\t Directory', dirName, 'already exists')
						pass
				
				print('\n \t ======================= Creating PLOT files ============================')
				
				print('\n \t List of sites: ')
				
				for sites in glob.glob('????'):
						print('\t '+ sites)
						f = open('123', 'a+')
						f.write(sites + '\n')
						f.close()
						for lines in open(sites):
								alldata.append(sites+' '+lines)
				
				os.rename(os.getcwd()+'//123', os.getcwd()+'//PLOTS'+'//123')
				
				os.chdir(os.getcwd()+'//PLOTS')
				
				for files in alldata:
						allyear = str(files.split()[1])
						if 00 <= int(allyear[0:2]) <=80:
								year='20'+allyear[0:2]
						else:
								year='19'+allyear[0:2]
						day = int(allyear[2:5])/365.25
						date = int(year)+day
						sitenames = files.split()[0]
						coordx = str(files.split()[2])
						coordy = str(files.split()[3])
						coordz = str(files.split()[4])
						if os.path.isfile(os.getcwd()+'//'+sitenames) is True:
								sitefile = open(sitenames, 'a')
								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coordx, coordy, coordz))
						if os.path.isfile(os.getcwd()+'//'+sitenames) is False:
								sitefile = open(sitenames, 'w')
								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coordx, coordy, coordz))
				
				print('\n \t DONE! ')
				time.sleep(3)

		getxyz()
		sites()
		plotfiles()
start()
