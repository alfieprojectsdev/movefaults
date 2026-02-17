#Date created: March 2020

import glob, os, time
import pymap3d

# Filename constants
XYZ_FILENAME = 'XYZ'
ENU_FILENAME = 'ENU'
TEMP_FILENAME = '123'
PLOTS_DIRNAME = 'PLOTS'
KIN_GLOB = '*.KIN'
SITE_GLOB = '????'

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
				with open(XYZ_FILENAME, 'a+', encoding='utf-8') as f:
						for files in glob.glob(KIN_GLOB):
								with open(files, encoding='utf-8') as lines:
										for i in range(5):
												next(lines)
										for line in lines:
												x = line.split()
												if len(x) == 8:
														f.write('{:4s}  {:5s}  {:.6}  {:>13}  {:>13}  {:>13}\n'.format(x[0], files[4:9], x[3], x[4], x[5], x[6]))
														print('\t ' +x[0]+' '+files[4:9])
												else:
														f.write('----------------------------------------------------------\n')
		
		def transform():
				print('\n \t ============== Transforming XYZ coordinates to local ENU =============== \n')
				
				lat = input('\t Input latitude (DD): ')
				lon = input('\t Input longitude (DD): ')
				alt = input('\t Input altitude (m): ')
				
				with open(XYZ_FILENAME, 'r', encoding='utf-8') as input_f, open(ENU_FILENAME, 'a+', encoding='utf-8') as output_f:
						for line in input_f:
								r = line.split()
								if len(r) == 6:
										X = float(r[3])
										Y = float(r[4])
										Z = float(r[5])
										east, north, up = pymap3d.ecef2enu(X, Y, Z, float(lat), float(lon), float(alt), deg=True)
										output_f.write('{:4s}  {:5s}  {:6s}  {:.4f}  {:.4f}  {:.4f}\n'.format(r[0], r[1], r[2], east, north, up))
								else:
										output_f.write('----------------------------------------------------------\n')
						
		def getenu():
				print('\n \t ==================== Getting local ENU coordinates ===================== \n')
				
				with open(ENU_FILENAME, 'r', encoding='utf-8') as f:
						for lines in f:
								x = lines.split()
								if x and len(x[0]) == 4:
										with open(x[0], 'a+', encoding='utf-8') as site_f:
												site_f.write(x[1]+'  '+x[2]+','+x[3]+','+x[4]+','+x[5] + '\n')
								else:
										pass
						
		def plotfiles():
				input('\t To create PLOT files, press Enter')
				
				print('\t Running...')
				
				alldata = []
				
				if not os.path.exists(PLOTS_DIRNAME):
						os.mkdir(PLOTS_DIRNAME)
						print('\t Directory', PLOTS_DIRNAME, 'created')
				else:
						print('\t Directory', PLOTS_DIRNAME, 'already exists')
						pass
				
				print('\n \t ======================= Creating PLOT files ============================')
                
				print('\n \t List of sites: ')
				
				with open(TEMP_FILENAME, 'a+', encoding='utf-8') as f:
						for sites in glob.glob(SITE_GLOB):
								print('\t '+ sites)
								f.write(sites + '\n')
								with open(sites, 'r', encoding='utf-8') as site_f:
										for lines in site_f:
												alldata.append(sites+' '+lines)
				
#				os.rename(os.getcwd()+'//123', os.getcwd()+'//PLOTS'+'//123')
#				
#				os.chdir(os.getcwd()+'//PLOTS')
#				
#				for files in alldata:
#						allyear = str(files.split()[1])
#						if 00 <= int(allyear[0:2]) <=80:
#								year='20'+allyear[0:2]
#						else:
#								year='19'+allyear[0:2]
#						day = int(allyear[2:5])/365.25
#						date = int(year)+day
#						sitenames = files.split()[0]
#						coorde = str(files.split()[2])
#						coordn = str(files.split()[3])
#						coordu = str(files.split()[4])
#						if os.path.isfile(os.getcwd()+'//'+sitenames) is True:
#								sitefile = open(sitenames, 'a')
#								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coorde, coordn, coordu))
#						if os.path.isfile(os.getcwd()+'//'+sitenames) is False:
#								sitefile = open(sitenames, 'w')
#								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coorde, coordn, coordu))
				
				print('\n \t DONE! ')
				time.sleep(3)
				
		getxyz()
		transform()
		getenu()
		plotfiles()

if __name__ == "__main__":
		start()
