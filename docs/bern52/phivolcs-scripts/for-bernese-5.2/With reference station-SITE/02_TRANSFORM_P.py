import glob, os, numpy
import pymap3d

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
				print(sitename+' '+str(lat)+' '+str(lon)+' '+str(alt))

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