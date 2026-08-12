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
				sitename = input('Enter site name: ')
				sitename = sitename.upper()

				print('Transforming XYZ coordinates to local ENU...')

				X = []
				Y = []
				Z = []
				finalXsum = 0
				finalYsum = 0
				finalZsum = 0
				sname = []

				for lines in open('XYZ'): 
						a = lines.split()
						if len(lines.split()) == 5 and a[0] == sitename:
								X.append(a[2])
								Y.append(a[3])
								Z.append(a[4])
								finalXsum = finalXsum + float(a[2])
								finalYsum = finalYsum + float(a[3])
								finalZsum = finalZsum + float(a[4])
								finalXmean = finalXsum / len(X)
								finalYmean = finalYsum / len(Y)
								finalZmean = finalZsum / len(Z)
								lat, lon, alt = pymap3d.ecef2geodetic(finalXmean, finalYmean, finalZmean, deg=True)

				for file in glob.glob('*.CRD'):
						with open(file) as line:
								for i in range(6):
										next(line)
								for lines in line:
										r = lines.split()
										if len(lines.split()) == 7 and r[1] == sitename:
												X = float(r[3])
												Y = float(r[4])
												Z = float(r[5])
												east, north, up = pymap3d.ecef2enu(X, Y, Z, lat, lon, alt, deg=True)
												f = open('ENU', 'a')
												f.write('{:4s}  {:4s}  {:5s}  {:.4f}  {:.4f}  {:.4f}\n'.format(r[1], sitename, file[2:7], east, north, up))
												f.close()
										else:
												pass

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
								open(sname[0], 'a').write(x[2]+'  '+x[3]+'  '+x[4]+'  '+x[5])
								open(sname[0], 'a').write('\n')
						
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
								sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coorde, coordn, coordu))
		
		def interrupt():
				flow = input('Transform another site? \nY = To return, N = To proceed ')
				flow = flow.upper()
				if flow == 'Y':
						transform()
						interrupt()
				elif flow == 'N':
						getenu()
						plotfiles()
		
		getxyz()
		transform()
		interrupt()
		
start()
