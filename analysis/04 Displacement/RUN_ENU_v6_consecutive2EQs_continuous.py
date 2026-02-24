#Date created: May 2020
#Date edited: December 2022
#For series of earthquake events
import numpy, os, glob, time
from statistics import mean
import matplotlib.pyplot as plt
from matplotlib import style
from matplotlib import rc
plt.rcParams['font.sans-serif'] = "Arial"
plt.rcParams['font.family'] = "sans-serif"
plt.rcParams.update({'font.size': 12})

def header():
	header = """-------------------------------------------------------------------------------------
    SITE     DATE           EAST (cm)           NORTH (cm)            UP (cm)
-------------------------------------------------------------------------------------\n"""
	file = open(names+"_D", 'w+')
	file.write(header)
	file.close()

def regressline():
	t = []
	e = []
	n = []
	u = []
	seismic_t = []
	seismic_e = []
	seismic_n = []
	seismic_u = []
	eq_t = []
	eq_e = []
	eq_n = []
	eq_u = []
	regress_e = []
	regress_n = []
	regress_u = []
	regress2_e = []
	regress2_n = []
	regress2_u = []
	points_e = []
	points_n = []
	points_u = []
	points_t = []
	ee = []
	nn = []
	uu = []
	tt = []
	aa = []
	ab = []
	ae = []
	an = []
	au = []
	
	for lines in open(names):
		if 'JUL' in lines: #stopped if JUL is encountered
			break
		elif len(lines.split()) == 4: #time series during interseismic
			t.append(float(lines.split()[0]))
			e.append(float(lines.split()[1]))
			n.append(float(lines.split()[2]))
			u.append(float(lines.split()[3]))
			
	for lines in open(names):
		if 'JUL' in lines: #time series of first event
			seismic_t.append(float(lines.split()[1]))
			seismic_e.append(float(lines.split()[2]))
			seismic_n.append(float(lines.split()[3]))
			seismic_u.append(float(lines.split()[4]))

	for lines in open(names):
		if 'OCT' in lines: #for second event
			eq_t.append(float(lines.split()[1]))
			eq_e.append(float(lines.split()[2]))
			eq_n.append(float(lines.split()[3]))
			eq_u.append(float(lines.split()[4]))

#combining all for the y-axis values
	all_e = e + seismic_e + eq_e
	all_n = n + seismic_n + eq_n
	all_u = u + seismic_u + eq_u
	all_t = t + seismic_t + eq_t
#getting the change in position
	e = (e - numpy.mean(all_e)) * 100 #cm
	n = (n - numpy.mean(all_n)) * 100 #cm
	u = (u - numpy.mean(all_u)) * 100 #cm
	seismic_e = (seismic_e - numpy.mean(all_e)) * 100 #cm
	seismic_n = (seismic_n - numpy.mean(all_n)) * 100 #cm
	seismic_u = (seismic_u - numpy.mean(all_u)) * 100 #cm
	eq_e = (eq_e - numpy.mean(all_e)) * 100 #cm
	eq_n = (eq_n - numpy.mean(all_n)) * 100 #cm
	eq_u = (eq_u - numpy.mean(all_u)) * 100 #cm
	all_e = (all_e - numpy.mean(all_e)) * 100 #cm
	all_n = (all_n - numpy.mean(all_n)) * 100 #cm
	all_u = (all_u - numpy.mean(all_u)) * 100 #cm
#assigning interseismic to matrix
	d = numpy.zeros((len(t), 4))
	d[:,0] = e
	d[:,1] = n
	d[:,2] = u
	d[:,3] = t
#assigning first event to matrix
	p = numpy.zeros((len(seismic_t), 4))
	p[:,0] = seismic_e
	p[:,1] = seismic_n
	p[:,2] = seismic_u
	p[:,3] = seismic_t
#getting the slopes and intercepts for interseismic and first event
	me = (((mean(d[:,3])*mean(d[:,0])) - mean((d[:,3])*(d[:,0]))) / (((mean(d[:,3]))*(mean(d[:,3]))) - mean((d[:,3])*(d[:,3]))))
	me2 = (((mean(p[:,3])*mean(p[:,0])) - mean((p[:,3])*(p[:,0]))) / (((mean(p[:,3]))*(mean(p[:,3]))) - mean((p[:,3])*(p[:,3]))))
	be = mean(d[:,0]) - me*mean(d[:,3])
	be2 = mean(p[:,0]) - me2*mean(p[:,3])
	mn = (((mean(d[:,3])*mean(d[:,1])) - mean((d[:,3])*(d[:,1]))) / (((mean(d[:,3]))*(mean(d[:,3]))) - mean((d[:,3])*(d[:,3]))))
	mn2 = (((mean(p[:,3])*mean(p[:,1])) - mean((p[:,3])*(p[:,1]))) / (((mean(p[:,3]))*(mean(p[:,3]))) - mean((p[:,3])*(p[:,3]))))
	bn = mean(d[:,1]) - mn*mean(d[:,3])
	bn2 = mean(p[:,1]) - mn2*mean(p[:,3])
	mu = (((mean(d[:,3])*mean(d[:,2])) - mean((d[:,3])*(d[:,2]))) / (((mean(d[:,3]))*(mean(d[:,3]))) - mean((d[:,3])*(d[:,3]))))
	mu2 = (((mean(p[:,3])*mean(p[:,2])) - mean((p[:,3])*(p[:,2]))) / (((mean(p[:,3]))*(mean(p[:,3]))) - mean((p[:,3])*(p[:,3]))))
	bu = mean(d[:,2]) - mu*mean(d[:,3])
	bu2 = mean(p[:,2]) - mu2*mean(p[:,3])
#getting the regression line for interseismic and first event
	for time in d[:,3]:
		regress_e.append((me*time)+be)
		regress_n.append((mn*time)+bn)
		regress_u.append((mu*time)+bu)
	for time2 in p[:,3]:
		regress2_e.append((me2*time2)+be2)
		regress2_n.append((mn2*time2)+bn2)
		regress2_u.append((mu2*time2)+bu2)
#getting the predicted points at first event
#	for event in seismic_t:
#		t.append(event)
#		regress_e.append((me*event)+be)
#		regress_n.append((mn*event)+bn)
#		regress_u.append((mu*event)+bu)
#getting the predicted points at second event using the regression line from first event
	for event2 in eq_t:        
		i = -1
		j = -1
		k = -1
		predict2_e = (me2*event2)+be2
		predict2_n = (mn2*event2)+bn2
		predict2_u = (mu2*event2)+bu2
		print('\t DATE OF EVENT: ' + str(event2))
		index_t = eq_t.index(event2)
#getting the displacement and writing it to temporary text files
		for actual_e in eq_e:
			i += 1
			displacement_e = actual_e - predict2_e           
			file = open('East', 'a+')
			file.write('{:2s}  {:4s}   {:.4f}   {:.10f}\n'.format(str(i), names, event2, displacement_e))
			file.close()
		for actual_n in eq_n:
			j += 1
			displacement_n = actual_n - predict2_n
			file = open('North', 'a+')
			file.write('{:2s}  {:4s}   {:.4f}   {:.10f}\n'.format(str(j), names, event2,displacement_n))
			file.close()
		for actual_u in eq_u:
			k += 1
			displacement_u = actual_u - predict2_u
			file = open('Up', 'a+')
			file.write('{:2s}  {:4s}   {:.4f}   {:.10f}\n'.format(str(k), names, event2,displacement_u))
			file.close()
#assigning value to separate variables			
	for event2 in eq_t:	
		index_t = eq_t.index(event2)
		l = int(index_t)
		with open('East') as lines:
			for line in lines:
				x = line.split()
				if float(x[2]) == float(event2):
					if int(x[0]) == l:
						aa.append(x[0])
						ab.append(x[1]+'  '+x[2])
						ae.append(x[3])
	
	for event2 in eq_t:	
		index_t = eq_t.index(event2)
		m = int(index_t)
		with open('North') as lines:
			for line in lines:
				y = line.split()
				if float(y[2]) == float(event2):
					if int(y[0]) == m:
						an.append(y[3])

	for event2 in eq_t:	
		index_t = eq_t.index(event2)
		n = int(index_t)
		with open('Up') as lines:
			for line in lines:
				z = line.split()
				if float(z[2]) == float(event2):
					if int(z[0]) == n:
						au.append(z[3])
#rewriting the temporary files to a text file
	with open(names+"_D", 'a+') as file:
		for (aa, ab, ae, an, au) in zip(aa, ab, ae, an, au):
			aa1, ae1, an1, au1=['{:2.10s}'.format(e) for e in (aa, ae, an, au)]
			file.write("{:>2}  {}      {:>13}        {:>13}       {:>13}\n".format(aa, ab, ae, an, au))
#deleting the temporary files
	if os.path.isfile(os.getcwd()+'\\East') is True:
		os.remove(os.getcwd()+'\\East')
	
	if os.path.isfile(os.getcwd()+'\\North') is True:
		os.remove(os.getcwd()+'\\North')
	
	if os.path.isfile(os.getcwd()+'\\Up') is True:
		os.remove(os.getcwd()+'\\Up')
#averaging the displacements
	with open(names+"_D") as file:
		for f in file:
			if len(f) >= 78 and len(f) <= 82:
				r = f.split()
				dm_e = 0
				dm_n = 0
				dm_u = 0
				dm_t = 0
				am_e = 0
				am_n = 0
				am_u = 0
				am_t = 0
				if r[1] == names:
					ee.append(float(r[3]))
					nn.append(float(r[4]))
					uu.append(float(r[5]))
					tt.append(float(r[2]))
					dm_e = numpy.mean(ee)
					dm_n = numpy.mean(nn)
					dm_u = numpy.mean(uu)
					dm_t = numpy.mean(tt)
					am_e = numpy.mean(eq_e)
					am_n = numpy.mean(eq_n)
					am_u = numpy.mean(eq_u)
					am_t = numpy.mean(eq_t)
#writing the mean displacement
	file = open(names+"_D", 'a+')
	file.write('    {:4s}  {:.4f}    {:.13f}      {:.13f}    {:.13f}\n'.format('MEAN', dm_t, dm_e, dm_n, dm_u))
	file.write('=====================================================================================\n')
	file.close()
#getting the projected point for the average time	
	pm_e = (me2*am_t)+be2
	pm_n = (mn2*am_t)+bn2
	pm_u = (mu2*am_t)+bu2
#putting the actual average points and the projected point to a list	
	points_e.append(pm_e)
	points_e.append(am_e)
	points_n.append(pm_n)
	points_n.append(am_n)
	points_u.append(pm_u)
	points_u.append(am_u)
	points_t.append(am_t)
	points_t.append(am_t)
#extending the regression line to the second event
	seismic_t.append(event2)
	regress2_e.append(predict2_e)
	regress2_n.append(predict2_n)
	regress2_u.append(predict2_u)
#assigning the actual average points to a matrix
	m = numpy.zeros((1, 4))
	m[:,0] = am_e
	m[:,1] = am_n
	m[:,2] = am_u
	m[:,3] = am_t
#assigning all points to a matrix
	G = numpy.zeros((len(all_t), 4))
	G[:,0] = all_e
	G[:,1] = all_n
	G[:,2] = all_u
	G[:,3] = all_t

	f = plt.figure(figsize=(9,7))
	
	ax1 = f.add_subplot(311)
	col1 = ax1.scatter(G[:,3], G[:,0], s=[50]*len(G[:,3]), facecolors=['none']*len(G[:,3]), edgecolors=['b']*len(G[:,3]))
	col11 = ax1.scatter(m[:,3], m[:,0], s=[50]*1, facecolors=['none']*1, edgecolors=['r']*1, label= 'displacement = {:.2f} cm'.format(dm_e))
	ax1.set_ylabel('East (cm)', size=14)
	ax1.legend(loc='upper right', bbox_to_anchor=(1,1.21), edgecolor = 'none', facecolor='none', handletextpad=0.1)
	ax1.set_title(names, fontweight='bold', loc='center', size=24)
	#ax1.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
	ax1.plot(t, regress_e, c='chartreuse', linewidth=1)
	ax1.plot(points_t, points_e, c='red', linewidth=1.2)
	ax1.plot(seismic_t, regress2_e, c='chartreuse', linewidth=1)
	ax1.grid(linestyle='dotted')
	
	ax2 = f.add_subplot(312)
	col2 = ax2.scatter(G[:,3], G[:,1], s=[50]*len(G[:,3]), facecolors=['none']*len(G[:,3]), edgecolors=['b']*len(G[:,3]))
	col22 = ax2.scatter(m[:,3], m[:,1], s=[50]*1, facecolors=['none']*1, edgecolors=['r']*1, label= 'displacement = {:.2f} cm'.format(dm_n))
	ax2.set_ylabel('North (cm)', size=14)
	ax2.legend(loc='upper right', bbox_to_anchor=(1,1.21), edgecolor = 'none', facecolor='none', handletextpad=0.1)
	#ax2.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
	ax2.plot(t, regress_n, c='chartreuse', linewidth=1)
	ax2.plot(points_t, points_n, c='red', linewidth=1.2)
	ax2.plot(seismic_t, regress2_n, c='chartreuse', linewidth=1)
	ax2.grid(linestyle='dotted')
	
	ax3 = f.add_subplot(313)
	col3 = ax3.scatter(G[:,3], G[:,2], s=[50]*len(G[:,3]), facecolors=['none']*len(G[:,3]), edgecolors=['b']*len(G[:,3]))
	col33 = ax3.scatter(m[:,3], m[:,2], s=[50]*1, facecolors=['none']*1, edgecolors=['r']*1, label= 'displacement = {:.2f} cm'.format(dm_u))
	ax3.set_ylabel('Up (cm)', size=14)
	ax3.legend(loc='upper right', bbox_to_anchor=(1,1.21), edgecolor = 'none', facecolor='none', handletextpad=0.1)
	ax3.set_xlabel('TIME', size=14)
	#ax3.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
	ax3.plot(t, regress_u, c='chartreuse', linewidth=1)
	ax3.plot(points_t, points_u, c='red', linewidth=1.2)
	ax3.plot(seismic_t, regress2_u, c='chartreuse', linewidth=1)
	ax3.grid(linestyle='dotted')
	
	f.tight_layout()
	f.subplots_adjust(hspace=0.35)
	f.savefig(names+'_D.png')

def interrupt():
	flow = input('\n \t Get displacement of another site? \n \t Y = If YES, N = To STOP : ')
	flow = flow.upper()
	if flow == 'Y':
		start()
		interrupt()
	elif flow == 'N':
		print('\n \t DONE! ')
		time.sleep(3)
		exit()

def entersite():
	global names
	names = input('\t Input filename: ')
	names = names.upper()
	names = os.path.basename(names)

print('\t ======================================================================== \n')
print('\t \t \t \t WELCOME GPS TEAM! :) \n')
print('\t \t Determine the coseismic displacement from ENU coordinates \n')
print('\t Instructions: Input the name of the site. ')
print('\t \t INPUT: PLOT files \t OUTPUT: PNG and Displacement files \n')
print('\t ======================================================================== \n')
input('\t Press Enter to continue \n')
def start():
	entersite()
	header()
	regressline()
	interrupt()
start()