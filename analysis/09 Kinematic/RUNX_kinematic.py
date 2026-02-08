#Date created: March 2020

import glob, os, time
import pymap3d

def start():

		def getxyz():
				print('\t ======================================================================== \n')
				print('\t \t \t \t WELCOME GPS TEAM! :) \n')
				print('\t Transform ECEF (XYZ) to ENU (East-North-Up) coordinates using PYMAP3D \n')
				print('\t About this version: The local ENU coordinates are fixed to your input \n \t \t \t \t LLA coordinates.')
				print('\t \t INPUT: CRD files \t \t OUTPUT: PLOT files \n')
				print('\t ======================================================================== \n')
				input('\t Press Enter to continue \n')
				print('\t ========================= Getting XYZ coordinates ====================== \n')
				for files in glob.glob('*.KIN'):
						with open(files) as lines:
								for i in range(5):
										next(lines)
								for line in lines:
										x = line.split()
										if len(line.split()) == 8:
												f = open('XYZ', 'a+')
												f.write('{:4s}  {:5s}  {:.6}  {:>13}  {:>13}  {:>13}\n'.format(x[0], files[4:9], x[3], x[4], x[5], x[6]))
												f.close()
												print('\t ' +x[0]+' '+files[4:9])	
										else:
												f = open('XYZ', 'a+')
												f.write('----------------------------------------------------------\n')
												f.close()
		
		def transform():
				print('\n \t ============== Transforming XYZ coordinates to local ENU =============== \n')
				
				lat = input('\t Input latitude (DD): ')
				lon = input('\t Input longitude (DD): ')
				alt = input('\t Input altitude (m): ')
				
				for file in open('XYZ'):
						r = file.split()
						if len(r) == 6:
								X = float(r[3])
								Y = float(r[4])
								Z = float(r[5])
								east, north, up = pymap3d.ecef2enu(X, Y, Z, float(lat), float(lon), float(alt), deg=True)
								f = open('ENU', 'a+')
								f.write('{:4s}  {:5s}  {:6s}  {:.4f}  {:.4f}  {:.4f}\n'.format(r[0], r[1], r[2], east, north, up))
								f.close()
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
								open(sname[0], 'a+').write(x[1]+'  '+x[2]+','+x[3]+','+x[4]+','+x[5])
								open(sname[0], 'a+').write('\n')
						else:
								pass
						
		def plotfiles():
				input('\t To create PLOT files, press Enter')
				
				print('\t Running...')
				
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
				
				
				print('\n \t DONE! ')
				time.sleep(3)
				
		getxyz()
		transform()
		getenu()
		plotfiles()
start()
