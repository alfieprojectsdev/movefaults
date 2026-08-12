import glob, os, numpy
import pymap3d

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