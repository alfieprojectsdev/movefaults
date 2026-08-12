import glob, os, numpy
import pymap3d

print('Transforming XYZ to geodetic coordinates...')

for lines in open('XYZ'):
		a = lines.split()
		if len(lines.split()) == 5:
				X = float(a[2])
				Y = float(a[3])
				Z = float(a[4])
				lat, lon, alt = pymap3d.ecef2geodetic(X, Y, Z, deg=True)
				f = open('LLA', 'a')
				f.write('{:4s}  {:5s}  {:.8f}  {:.8f}  {:.8f}\n'.format(a[0], a[1], lon, lat, alt))
				f.close()
		else:
				f = open('LLA', 'a+')
				f.write('-----------------------------------------------\n')
				f.close()