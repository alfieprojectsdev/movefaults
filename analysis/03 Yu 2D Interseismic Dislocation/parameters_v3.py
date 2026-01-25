maxrchi = float(input("Input the maximum r_chi2 value: "))
f = open("parameters_new.txt", 'w+')
f.write('EAST'+'  '+'DEPTH'+'   '+'WIDTH'+'    '+'DIP'+'    '+'RESIDUAL'+'     '+'RATE'+'   '+'SLIP RATE'+'   '+'REDUCED_CHI2'+'   '+'CHI2'+' \n')
f.close()
with open("parameters.txt") as lines:
    for i in range(1):
        next(lines)
    for line in lines:
        x = line.split()
        if float(x[7]) < maxrchi and 0 <= float(x[6]) <= float(x[5]):
            f = open("parameters_new.txt", 'a+')
            f.write(x[0]+'    '+x[1]+'     '+x[2]+'     '+x[3]+'  '+x[4]+' '+x[5]+'  '+x[6]+'  '+x[7]+'  '+x[8]+'\n')
            f.close()

