import glob, os, numpy

input('To create plot files, press Enter')
print('Running...')
				
dirName = 'PLOTS'
if not os.path.exists(dirName):
		os.mkdir(dirName)
		print('Directory', dirName, 'created')
else:
		print('Directory', dirName, 'already exists')
		pass
				
alldata = []
print("List of sites:")

for sites in glob.glob('????'):
		print(sites)
		f = open('123', 'a+')
		f.write(sites + '\n')
		f.close()
		for lines in open(sites):
				alldata.append(sites+'  '+lines)
				
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
		coordn = str(files.split()[2])
		coorde = str(files.split()[3])
		coordu = str(files.split()[4])
		if os.path.isfile(os.getcwd()+'//'+sitenames) is True:
				sitefile = open(sitenames, 'a')
				sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coordn, coorde, coordu))
		if os.path.isfile(os.getcwd()+'//'+sitenames) is False:
				sitefile = open(sitenames, 'w')
				sitefile.write('{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coordn, coorde, coordu))