#Date created: May 2020
#Date edited: November 2021
#Change y axis
import numpy, os, glob, msvcrt, time
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
	regression_e = []
	regression_n = []
	regression_u = []
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
		if 'COSEISMIC' in lines:
			break
		elif len(lines.split()) == 4:
			t.append(float(lines.split()[0]))
			e.append(float(lines.split()[1]))
			n.append(float(lines.split()[2]))
			u.append(float(lines.split()[3]))
			
	for lines in open(names):
		if 'COSEISMIC' in lines:
			seismic_t.append(float(lines.split()[1]))
			seismic_e.append(float(lines.split()[2]))
			seismic_n.append(float(lines.split()[3]))
			seismic_u.append(float(lines.split()[4]))
			
	all_e = e + seismic_e
	all_n = n + seismic_n
	all_u = u + seismic_u
	all_t = t + seismic_t
    
	seismic_e = (seismic_e - numpy.mean(e)) * 100
	seismic_n = (seismic_n - numpy.mean(n)) * 100
	seismic_u = (seismic_u - numpy.mean(u)) * 100
	all_e = (all_e - numpy.mean(e)) * 100
	all_n = (all_n - numpy.mean(n)) * 100
	all_u = (all_u - numpy.mean(u)) * 100
	e = (e - numpy.mean(e)) * 100
	n = (n - numpy.mean(n)) * 100
	u = (u - numpy.mean(u)) * 100

	if len(t) < 3:
		print('\t The site '+names+' cannot be plotted!')
		return
	else:
		pass

	d = numpy.zeros((len(t), 4))
	d[:,0] = e
	d[:,1] = n
	d[:,2] = u
	d[:,3] = t

	me = (((mean(d[:,3])*mean(d[:,0])) - mean((d[:,3])*(d[:,0]))) / (((mean(d[:,3]))*(mean(d[:,3]))) - mean((d[:,3])*(d[:,3]))))
	be = mean(d[:,0]) - me*mean(d[:,3])
	mn = (((mean(d[:,3])*mean(d[:,1])) - mean((d[:,3])*(d[:,1]))) / (((mean(d[:,3]))*(mean(d[:,3]))) - mean((d[:,3])*(d[:,3]))))
	bn = mean(d[:,1]) - mn*mean(d[:,3])
	mu = (((mean(d[:,3])*mean(d[:,2])) - mean((d[:,3])*(d[:,2]))) / (((mean(d[:,3]))*(mean(d[:,3]))) - mean((d[:,3])*(d[:,3]))))
	bu = mean(d[:,2]) - mu*mean(d[:,3])
	for time in d[:,3]:
		regression_e.append((me*time)+be)
		regression_n.append((mn*time)+bn)
		regression_u.append((mu*time)+bu)
	
	G = numpy.zeros((len(all_t), 4))
	G[:,0] = all_e
	G[:,1] = all_n
	G[:,2] = all_u
	G[:,3] = all_t

	for event in seismic_t:
		i = -1
		j = -1
		k = -1
		predict_e = (me*event)+be
		predict_n = (mn*event)+bn
		predict_u = (mu*event)+bu
		print('\t DATE OF EVENT: ' + str(event))
		index_t = seismic_t.index(event)
		for actual_e in seismic_e:
			i += 1
			displacement_e = actual_e - predict_e
			#print('EAST: '+ str(displacement_e) +' cm')
			file = open('East', 'a+')
			file.write('{:2s}  {:4s}   {:.4f}   {:.10f}\n'.format(str(i), names, event, displacement_e))
			file.close()
		for actual_n in seismic_n:
			j += 1
			displacement_n = actual_n - predict_n
			#print('NORTH: '+ str(displacement_n) +' cm')
			file = open('North', 'a+')
			file.write('{:2s}  {:4s}   {:.4f}   {:.10f}\n'.format(str(j), names, event,displacement_n))
			file.close()
		for actual_u in seismic_u:
			k += 1
			displacement_u = actual_u - predict_u
			#print('UP: '+ str(displacement_u) +' cm')
			file = open('Up', 'a+')
			file.write('{:2s}  {:4s}   {:.4f}   {:.10f}\n'.format(str(k), names, event,displacement_u))
			file.close()
			
	for event in seismic_t:	
		index_t = seismic_t.index(event)
		l = int(index_t)
		with open('East') as lines:
			for line in lines:
				x = line.split()
				if float(x[2]) == float(event):
					if int(x[0]) == l:
						aa.append(x[0])
						ab.append(x[1]+'  '+x[2])
						ae.append(x[3])
	
	for event in seismic_t:	
		index_t = seismic_t.index(event)
		m = int(index_t)
		with open('North') as lines:
			for line in lines:
				y = line.split()
				if float(y[2]) == float(event):
					if int(y[0]) == m:
						an.append(y[3])

	for event in seismic_t:	
		index_t = seismic_t.index(event)
		n = int(index_t)
		with open('Up') as lines:
			for line in lines:
				z = line.split()
				if float(z[2]) == float(event):
					if int(z[0]) == n:
						au.append(z[3])
	
	with open(names+"_D", 'a+') as file:
		for (aa, ab, ae, an, au) in zip(aa, ab, ae, an, au):
			aa1, ae1, an1, au1=['{:2.10s}'.format(e) for e in (aa, ae, an, au)]
			file.write("{:>2}  {}      {:>13}        {:>13}       {:>13}\n".format(aa, ab, ae, an, au))
	
	if os.path.isfile(os.getcwd()+'\\East') is True:
		os.remove(os.getcwd()+'\\East')
	
	if os.path.isfile(os.getcwd()+'\\North') is True:
		os.remove(os.getcwd()+'\\North')
	
	if os.path.isfile(os.getcwd()+'\\Up') is True:
		os.remove(os.getcwd()+'\\Up')
	
	with open(names+"_D") as file:
		for f in file:
			if len(f) >= 78 and len(f) <= 84:
				r = f.split()
				if r[1] == names:
					ee.append(float(r[3]))
					nn.append(float(r[4]))
					uu.append(float(r[5]))
					tt.append(float(r[2]))
					dm_e = numpy.mean(ee)
					dm_n = numpy.mean(nn)
					dm_u = numpy.mean(uu)
					dm_t = numpy.mean(tt)
					am_e = numpy.mean(seismic_e)
					am_n = numpy.mean(seismic_n)
					am_u = numpy.mean(seismic_u)
					am_t = numpy.mean(seismic_t)
	
	file = open(names+"_D", 'a+')
	file.write('    {:4s}  {:.4f}    {:.13f}      {:.13f}    {:.13f}\n'.format('MEAN', dm_t, dm_e, dm_n, dm_u))
	file.write('=====================================================================================\n')
	file.close()
	
	pm_e = (me*am_t)+be
	pm_n = (mn*am_t)+bn
	pm_u = (mu*am_t)+bu
	
	points_e.append(pm_e)
	points_e.append(am_e)
	points_n.append(pm_n)
	points_n.append(am_n)
	points_u.append(pm_u)
	points_u.append(am_u)
	points_t.append(am_t)
	points_t.append(am_t)
	
	t.append(event)
	regression_e.append(predict_e)
	regression_n.append(predict_n)
	regression_u.append(predict_u)

	m = numpy.zeros((1, 4))
	m[:,0] = am_e
	m[:,1] = am_n
	m[:,2] = am_u
	m[:,3] = am_t
	
	f = plt.figure(figsize=(9,7))
	
	ax1 = f.add_subplot(311)
	col1 = ax1.scatter(G[:,3], G[:,0], s=[50]*len(G[:,3]), facecolors=['none']*len(G[:,3]), edgecolors=['b']*len(G[:,3]))
	col11 = ax1.scatter(m[:,3], m[:,0], s=[50]*1, facecolors=['none']*1, edgecolors=['r']*1, label= 'displacement = {:.2f} cm'.format(dm_e))
	ax1.set_ylabel('East (cm)', size=14)
	ax1.legend(loc='upper right', bbox_to_anchor=(1,1.21), edgecolor = 'none', facecolor='none', handletextpad=0.1)
	ax1.set_title(names, fontweight='bold', loc='center', size=24)
	#ax1.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
	ax1.plot(t, regression_e, c='chartreuse', linewidth=1)
	ax1.plot(points_t, points_e, c='red', linewidth=1.2)
	ax1.grid(linestyle='dotted')
	
	ax2 = f.add_subplot(312)
	col2 = ax2.scatter(G[:,3], G[:,1], s=[50]*len(G[:,3]), facecolors=['none']*len(G[:,3]), edgecolors=['b']*len(G[:,3]))
	col22 = ax2.scatter(m[:,3], m[:,1], s=[50]*1, facecolors=['none']*1, edgecolors=['r']*1, label= 'displacement = {:.2f} cm'.format(dm_n))
	ax2.set_ylabel('North (cm)', size=14)
	ax2.legend(loc='upper right', bbox_to_anchor=(1,1.21), edgecolor = 'none', facecolor='none', handletextpad=0.1)
	#ax2.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
	ax2.plot(t, regression_n, c='chartreuse', linewidth=1)
	ax2.plot(points_t, points_n, c='red', linewidth=1.2)
	ax2.grid(linestyle='dotted')
	
	ax3 = f.add_subplot(313)
	col3 = ax3.scatter(G[:,3], G[:,2], s=[50]*len(G[:,3]), facecolors=['none']*len(G[:,3]), edgecolors=['b']*len(G[:,3]))
	col33 = ax3.scatter(m[:,3], m[:,2], s=[50]*1, facecolors=['none']*1, edgecolors=['r']*1, label= 'displacement = {:.2f} cm'.format(dm_u))
	ax3.set_ylabel('Up (cm)', size=14)
	ax3.legend(loc='upper right', bbox_to_anchor=(1,1.21), edgecolor = 'none', facecolor='none', handletextpad=0.1)
	ax3.set_xlabel('TIME', size=14)
	#ax3.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
	ax3.plot(t, regression_u, c='chartreuse', linewidth=1)
	ax3.plot(points_t, points_u, c='red', linewidth=1.2)
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