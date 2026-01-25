gmt set FONT_ANNOT_PRIMARY 10p, Helvetica
gmt set TICK_LENGTH 0.055i 
gmt set FONT_LABEL 12p, Helvetica

makecpt -Chot -I -D -T0/40/1 -Z -V > slip.cpt

gmt psxyz gmt_faultslip_xyz_1.gmt -R0/120/-30/100/0/20  -Jx0.035i/0.035i -Jz-0.035i -E235/25 -W1p,black -L -P -Cslip.cpt -B10:"East (km)":/10:"North (km)":/5:"Depth (km)":SneWZ -K -X1i -Y3i > fault_3d.ps
gmt psxyz gmt_faultslip_xyz_2.gmt -R0/120/-30/100/0/20  -Jx0.035i/0.035i -Jz-0.035i -E235/25 -W1p,black -L -P -Cslip.cpt -O -K >> fault_3d.ps


gmt set ANNOT_FONT_SIZE 10p TICK_LENGTH 0.055i LABEL_FONT_SIZE 9p ANNOT_OFFSET 0.025i LABEL_OFFSET 0.0325i
gmt psscale -B5+l"Backslip rate (mm/yr)" -Dx6.45i/0.00i+w3i/0.2i+v -Cslip.cpt -O -V >> fault_3d.ps

gmt psconvert fault_3d.ps -A -Tj