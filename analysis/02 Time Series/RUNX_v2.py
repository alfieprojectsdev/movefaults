#Date created: March 2020

import glob, os, numpy, time
import pymap3d

def start():

		def getxyz():
				print('\t ======================================================================== \n')
				print('\t \t \t \t WELCOME GPS TEAM! :) \n')
				print('\t Transform ECEF (XYZ) to ENU (East-North-Up) coordinates using PYMAP3D \n')
				print('\t About this version: The local ENU coordinates are fixed to your selected \n \t \t \t \t reference station.')
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
		
		def transform():
				print('\n \t ============== Transforming XYZ coordinates to local ENU =============== \n')
				
				refsite = input('\t Input reference station: ')
				refsite = refsite.upper()

				for files in glob.glob('*.CRD'):
						with open(files) as lines:
								for i in range(6):
										next(lines)
								for line in lines:
										a = line.split()
										if len(line.split()) == 7 and a[1] == refsite:
												X = float(a[3])
												Y = float(a[4])
												Z = float(a[5])
												lat, lon, alt = pymap3d.ecef2geodetic(X, Y, Z, deg=True)
												for file in glob.glob('*.CRD'):
														with open(file) as line:
																for i in range(6):
																		next(line)
																for lines in line:
																		r = lines.split()
																		if file[2:7] == files[2:7]:
																				if len(lines.split()) == 7 and r[1] != refsite:
																						X = float(r[3])
																						Y = float(r[4])
																						Z = float(r[5])
																						east, north, up = pymap3d.ecef2enu(X, Y, Z, lat, lon, alt, deg=True)
																						f = open('ENU', 'a')
																						f.write('{:4s}  {:4s}  {:5s}  {:.4f}  {:.4f}  {:.4f}\n'.format(r[1], refsite, file[2:7], east, north, up))
																				elif len(lines.split()) >= 6 and r[1] == refsite:
																						pass
																				elif len(lines.split()) == 6:
																						pass
																				else:
																						f = open('ENU', 'a+')
																						f.write('----------------------------------------------------------\n')
																						f.close()
						
		def getenu():
				print('\n \t ==================== Getting local ENU coordinates ===================== \n')
				
				sname = []
				
				for lines in open('ENU'):
						x = lines.split()
						if len(x[0]) == 4:
								if len(sname) == 0:
										sname.append(x[0])
								elif len(sname) == 1:
										del sname[0]
										sname.append(x[0])
								open(sname[0], 'a').write(x[2]+'  '+x[3]+'  '+x[4]+'  '+x[5])
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
						coorde = str(files.split()[2])
						coordn = str(files.split()[3])
						coordu = str(files.split()[4])
						if os.path.isfile(os.getcwd()+'//'+sitenames) is True:
								sitefile = open(sitenames, 'a')
								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coorde, coordn, coordu))
						if os.path.isfile(os.getcwd()+'//'+sitenames) is False:
								sitefile = open(sitenames, 'w')
								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coorde, coordn, coordu))
				
				print('\n \t DONE! ')
				time.sleep(3)

		getxyz()
		transform()
		getenu()
		plotfiles()
start()
