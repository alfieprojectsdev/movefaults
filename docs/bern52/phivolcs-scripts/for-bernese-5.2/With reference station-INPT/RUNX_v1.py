#Date created: March 2020

import glob, os, numpy
import pymap3d

def start():

		def getxyz():
				input('Press Enter to continue')
				print('Getting XYZ coordinates...')
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
												print(x[1]+' '+files[2:7])	
										elif len(line.split()) == 6:
												pass
										else:
												f = open('XYZ', 'a+')
												f.write('----------------------------------------------------------\n')
												f.close()
		
		def transform():
				lat = input('Input latitude (DD): ')
				lon = input('Input longitude (DD): ')
				alt = input('Input altitude (m): ')
				
				print('Transforming XYZ coordinates to local ENU...')
				
				for file in open('XYZ'):
						r = file.split()
						if len(r) == 5:
								X = float(r[2])
								Y = float(r[3])
								Z = float(r[4])
								east, north, up = pymap3d.ecef2enu(X, Y, Z, float(lat), float(lon), float(alt), deg=True)
								f = open('ENU', 'a')
								f.write('{:4s}  {:5s}  {:.4f}  {:.4f}  {:.4f}\n'.format(r[0], r[1], east, north, up))
								f.close()
						else:
								f = open('ENU', 'a+')
								f.write('----------------------------------------------------------\n')
								f.close()
						
		def getenu():
				print('Getting local ENU coordinates...')
				
				sname = []
				
				for lines in open('ENU'):
						x = lines.split()
						if len(x[0]) == 4:
								if len(sname) == 0:
										sname.append(x[0])
								elif len(sname) == 1:
										del sname[0]
										sname.append(x[0])
								open(sname[0], 'a').write(x[1]+'  '+x[2]+'  '+x[3]+'  '+x[4])
								open(sname[0], 'a').write('\n')
						else:
								pass
						
		def plotfiles():
				input('To create PLOT files, press Enter')
				
				print('Running...')
				
				alldata = []
				
				dirName = 'PLOTS'
				if not os.path.exists(dirName):
						os.mkdir(dirName)
						print('Directory', dirName, 'created')
				else:
						print('Directory', dirName, 'already exists')
						pass
				
				print('List of sites: ')
				
				for sites in glob.glob('????'):
						print(sites)
						f = open('123', 'a+')
						f.write(sites + '\n')
						f.close()
						for lines in open(sites):
								alldata.append(sites+' '+lines)
								
				print('Creating PLOT files...')
				
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
								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coordn, coordn, coordu))
				
		getxyz()
		transform()
		getenu()
		plotfiles()
start()
