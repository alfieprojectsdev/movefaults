maxlon = float(input("Input the maximum longitude: "))
minlon = float(input("Input the minimum longitude: "))
maxlat = float(input("Input the maximum latitude: "))
minlat = float(input("Input the minimum latitude: "))
faultname = input("Name of the fault: ")
f = open('faultlines_'+faultname+'.gmt', 'w+')
f.close()
with open("faultlines_updated2020.gmt") as lines:
	for i in range(3):
		next(lines)
	for line in lines:
		x = line.split()
		if len(x) == 1:
				f = open('faultlines_'+faultname+'.gmt', 'a+')
				f.write(x[0]+'\n')
				f.close()
		if len(x) == 2:
			if minlon < float(x[0]) < maxlon and minlat < float(x[1]) < maxlat:
				f = open('faultlines_'+faultname+'.gmt', 'a+')
				f.write(x[0]+' '+x[1]+'\n')
				f.close()

