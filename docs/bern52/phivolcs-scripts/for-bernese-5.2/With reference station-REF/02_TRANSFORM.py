import glob, os, numpy
import pymap3d

refsite = input('Input reference station: ')
refsite = refsite.upper()

print('Transforming XYZ coordinates to local ENU...')

for files in glob.glob('*.CRD'):
		with open(files) as lines:
				for i in range(6):
						next(lines)
				for line in lines:
						a = line.split()
						if len(line.split()) >= 6 and a[1] == refsite:
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
																if len(lines.split()) >= 6 and r[1] != refsite:
																		X = float(r[3])
																		Y = float(r[4])
																		Z = float(r[5])
																		east, north, up = pymap3d.ecef2enu(X, Y, Z, lat, lon, alt, deg=True)
																		f = open('ENU', 'a')
																		f.write('{:4s}  {:4s}  {:5s}  {:.4f}  {:.4f}  {:.4f}\n'.format(r[1], refsite, file[2:7], east, north, up))
																		f.close()
																elif len(lines.split()) >= 6 and r[1] == refsite:
																		pass
																else:
																		f = open('ENU', 'a+')
																		f.write('----------------------------------------------------------\n')
																		f.close()