import glob, os, numpy

input('Press Enter to continue')
print('Getting xyz coordinates...')
for files in glob.glob('*.CRD'):
		with open(files) as lines:
				for i in range(5):
						next(lines)
				for line in lines:
						x = line.split()
						if len(line.split()) >= 6:
								f = open('XYZ', 'a+')
								f.write('{:.4s}  {:.5s}  {:>13}  {:>13}  {:>13}\n'.format(x[1], files[2:7], x[3], x[4], x[5]))
								f.close()
								print(x[1]+' '+files[2:7])
						else:
								f = open('XYZ', 'a+')
								f.write('----------------------------------------------------------\n')
								f.close()