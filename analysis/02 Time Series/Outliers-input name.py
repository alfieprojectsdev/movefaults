import numpy
import matplotlib.ticker as tick
import matplotlib.pyplot as plt

    
def matplot():
    names = input('Input filename: ')
    names = names.upper()
    t = []
    n = []
    e = []
    u = []
    alldata = []
    for lines in open(names):
        t.append(float(lines.split()[0]))
        e.append(float(lines.split()[1]))
        n.append(float(lines.split()[2]))
        u.append(float(lines.split()[3]))
        alldata.append(lines)

    e = (e - numpy.mean(e)) * 100
    n = (n - numpy.mean(n)) * 100
    u = (u - numpy.mean(u)) * 100

    if len(t) < 3:
        print('    '+names+' cannot be plotted!')
        return
    else:
        pass
    #----Compute by matrix----
    #-------------------------
    d = numpy.zeros((len(t), 3))
    d[:,0] = e
    d[:,1] = n
    d[:,2] = u

    G = numpy.zeros((len(t), 2))
    G[:,0] = 1
    G[:,1] = t
    model = numpy.zeros((2,3))
    dhat = numpy.zeros((len(t), 3))
    residual = numpy.zeros((len(t), 3))

    gT = G.conj().transpose()
    gInv = numpy.linalg.inv(numpy.dot(gT, G))
    gDotInv = numpy.dot(gInv, gT)

    for ijk in range(0,3):
        model[0:2, ijk] = numpy.dot(gDotInv, d[:,ijk])
        dhat[:, ijk] = numpy.dot(G, model[:,ijk])
        residual[:,ijk] = d[:,ijk]-dhat[:,ijk]

    varM = gInv
    rnorm = numpy.zeros((1,3))
    sig_m = numpy.zeros((1,3))

    for lmn in range(0, 3):
        rnorm[:,lmn] = (numpy.dot(residual[:,lmn].conj().transpose(),residual[:,lmn]))/(len(residual)-2)
        sig_m[:,lmn] = numpy.sqrt(varM[1,1]*rnorm[:,lmn])

    #----Print values----
    #--------------------
    #print('Ve = {:.5f} +- {:.3f} Vn = {:.5f} +- {:.3f} Vu = {:.5f} +- {:.3f}'.format(model[1,0],sig_m[1,0],model[1,1],sig_m[1,1],model[1,2],sig_m[1,2]))    

    #----Start plotting----
    #----------------------
    f = plt.figure(figsize=(9,7))

    #----Plot EAST (subplot number 1)----
    ax1 = f.add_subplot(311)
    col1 = ax1.scatter(t, e, s=[20]*len(t), facecolors=['none']*len(t), edgecolors=['b']*len(t), label= 'v = {0:2.0f} mm/yr'.format(model[1,0]*10), picker=True)
    ax1.set_ylabel('East (cm)', size=10)
    ax1.legend(loc='upper right', bbox_to_anchor=(1,1.2))
    ax1.set_title(names, fontweight='bold', loc='center', size=20) #plot title as variable 'names'
    #y_fmt = tick.FormatStrFormatter('%.3f')
    #ax1.xaxis.set_major_formatter(y_fmt)
    #new = abs(ax1.get_xticks()[1]-ax1.get_xticks()[2])/2
    #new1 = ax1.get_xticks()[:-1]+new
    ax1.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
    ax1.plot(t, dhat[:,0], c='chartreuse', linewidth=1)


    #----Plot NORTH (subplot number 2)----
    ax2 = f.add_subplot(312)
    col2 = ax2.scatter(t, n, s=[20]*len(t), facecolors=['none']*len(t), edgecolors=['b']*len(t), label= 'v = {0:2.0f} mm/yr'.format(model[1,1]*10), picker=True)
    ax2.set_ylabel('North (cm)')
    ax2.legend(loc='upper right', bbox_to_anchor=(1,1.2))
    #y_fmt = tick.FormatStrFormatter('%.3f')
    #ax2.xaxis.set_major_formatter(y_fmt)
    #new = abs(ax2.get_xticks()[1]-ax2.get_xticks()[2])/2
    #new1 = ax2.get_xticks()[:-1]+new
    #ax2.set_xticks(list(ax2.get_xticks()[1:-1])+list(new1))
    ax2.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
    ax2.plot(t, dhat[:,1], c='chartreuse', linewidth=1)

    #----Plot UP (subplot number 3)----
    ax3 = f.add_subplot(313)
    col3 = ax3.scatter(t, u, s=[20]*len(t), facecolors=['none']*len(t), edgecolors=['b']*len(t), label= 'v = {0:2.0f} mm/yr'.format(model[1,2]*10), picker=True)
    ax3.set_ylabel('Up (cm)')
    ax3.legend(loc='upper right', bbox_to_anchor=(1,1.2))
    ax3.set_xlabel('TIME', size=15)
    #y_fmt = tick.FormatStrFormatter('%.3f')
    #ax3.xaxis.set_major_formatter(y_fmt)
    #new = abs(ax3.get_xticks()[1]-ax3.get_xticks()[2])/2
    #new1 = ax3.get_xticks()[:-1]+new
    #ax3.set_xticks(list(ax3.get_xticks()[1:-1])+list(new1))
    ax3.tick_params(direction='in', top='on', labeltop='off', size=5, labelsize=9)
    ax3.plot(t, dhat[:,2], c='chartreuse', linewidth=1)

    f.tight_layout()
    f.subplots_adjust(hspace=0.27)
    #f.savefig(names+'.png', dpi=300) #save file as variable 'names'+.png


    def onpick(event):
        if event.mouseevent.button == 3:
            ind = event.ind
            x = str((float(numpy.take(t,ind))))
            print('Timestamp of picks: {:}'.format(x))
            zxc = open('OUTLIERS.txt', 'a')
            zxc.write('{:4} {:}\n'.format(names, x))
            col1._edgecolors[event.ind] = (1,0,0,1)
            col2._edgecolors[event.ind] = (1,0,0,1)
            col3._edgecolors[event.ind] = (1,0,0,1)
            f.canvas.draw()
        else:
            pass

    cid = f.canvas.mpl_connect('pick_event', onpick)
    plt.show()

print('Starting matplot.Yon...')
print('-----------------------')
print('Welcome to VELPLOT for CHECKING!')
print('Click the outliers you wish to remove and see the details at OUTLIERS.TXT\n')
while True:
    matplot()
