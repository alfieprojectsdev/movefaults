f = open('baseline_cal_1-2.gmt', 'w+')
f.close()

with open('baseline_cal_1-1.gmt') as lines:
    for line in lines:
        x = line.split()
        if x[0] == '>':
            zvalue = x[1]
            f = open('baseline_cal_1-2.gmt', 'a+')
            f.write('\n' + x[0]+' '+x[1]+ '\n')
            f.close()
        if x[0] != '>':
            f = open('baseline_cal_1-2.gmt', 'a+')
            f.write(x[0]+' '+x[1]+' '+ zvalue +' ')
            f.close()
            
f = open('baseline_obs_1-2.gmt', 'w+')
f.close()

with open('baseline_obs_1-1.gmt') as lines:
    for line in lines:
        x = line.split()
        if x[0] == '>':
            zvalue = x[1]
            f = open('baseline_obs_1-2.gmt', 'a+')
            f.write('\n' + x[0]+' '+x[1]+ '\n')
            f.close()
        if x[0] != '>':
            f = open('baseline_obs_1-2.gmt', 'a+')
            f.write(x[0]+' '+x[1]+' '+ zvalue +' ')
            f.close()
            
f = open('baseline_res_1-2.gmt', 'w+')
f.close()

with open('baseline_res_1-1.gmt') as lines:
    for line in lines:
        x = line.split()
        if x[0] == '>':
            zvalue = x[1]
            f = open('baseline_res_1-2.gmt', 'a+')
            f.write('\n' + x[0]+' '+x[1]+ '\n')
            f.close()
        if x[0] != '>':
            f = open('baseline_res_1-2.gmt', 'a+')
            f.write(x[0]+' '+x[1]+' '+ zvalue +' ')
            f.close()