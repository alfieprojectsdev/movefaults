import glob, os, numpy

input('Press Enter to continue')
print('Getting geocentric (XYZ) coordinates...')
				
sname = []
				
for lines in open('XYZ'):
		x = lines.split()
		if len(x[0]) == 4:
				if len(sname) == 0:
						sname.append(x[0])
				elif len(sname) == 1:
						del sname[0]
						sname.append(x[0])
				open(sname[0], 'a').write(x[1]+'  '+x[2]+'  '+x[3]+'  '+x[4])
				open(sname[0], 'a').write('\n')