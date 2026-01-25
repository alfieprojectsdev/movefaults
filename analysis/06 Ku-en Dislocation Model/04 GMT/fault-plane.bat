gmt set FONT_LABEL 11p,Helvetica
gmt set FONT_ANNOT_PRIMARY 11p,Helvetica

gmt makecpt -Chot -I -D -T0/40/1 -Z -V > slip.cpt

rem gmt grdimage PH_topo_hr.nc -R122.50/124.50/11.63/13.10 -IPH_topo_hr.grad -Cgray_luzon.cpt -JM18 -P -K > fault-plane.ps
gmt pscoast -R122.50/124.50/11.63/13.10 -JM18 -W0.2p,black -Swhite -Df -P -Ba1f1 -BWSne -Lf123.00/11.75/5.0/5.0/50+l --FONT_LABEL=10 -K > fault-plane.ps

rem gmt psxy faultlines_updated2020.gmt -R -J -Sf0.01/0.01+f -W0.1p,black -O -K -P >> fault-plane.ps
rem gmt psxy faultlines_masbate.gmt -R -J -Sf0.01/0.01+f -W1.4p,red -O -K -P >> fault-plane.ps

rem echo 122.6875124 12.3684212   SIBI | gmt psxy -R -J -Sa1.0 -W0.5p,black -Gblue -K -O -P >> fault-plane.ps
rem echo 124.00   12.10  Masbate Fault | pstext -JM -R -N -F+a305+f9p,Helvetica -K -O -V >> fault-plane.ps

rem gmt psvelo Vel_cont_masbate_wrtSIBI.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -K -O -P -V >> fault-plane.ps
rem gmt psvelo Vel_camp_masbate_wrtSIBI.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -K -O -P -V >> fault-plane.ps

gmt psxy gmt_faultslip_plane_1.gmt -R -J -W0.01p,darkred -G+z -Cslip.cpt -V -K -O -L >> fault-plane.ps
gmt psxy gmt_faultslip_plane_2.gmt -R -J -W0.01p,darkred -G+z -Cslip.cpt -V -K -O -L >> fault-plane.ps
rem gmt psvelo gmt_faultvec_plane_1.gmt -R -J -Se0.005i/0.95/0 -A0.001i/0.02i/0.003i -W0.05p,black -Gblack -K -O -V >> fault-plane.ps
rem gmt psvelo gmt_faultvec_plane_2.gmt -R -J -Se0.005i/0.95/0 -A0.001i/0.02i/0.003i -W0.05p,black -Gblack -K -O -V >> fault-plane.ps

rem gmt psxy coordinates.xy -R -J -St0.3 -W0.5p,black -Gblack -K -O -P >> fault-plane.ps

rem gmt pslegend legend_rb.txt -R -J -Dg124.10/12.90+w1.2i/0.2i -K -O -P -V >> fault-plane.ps
rem gmt pslegend legend.txt -R -J -Dg123.96/12.96+w1.8i/0.35i -F+gwhite+p0.8p,black -K -O -P -V >> fault-plane.ps
gmt psscale -B5+l"Backslip rate (mm/yr)" -Dx3.0i/-0.34i+w6.1i/0.12i+jTC+h -Cslip.cpt -O -V >> fault-plane.ps
rem gmt psvelo legend_vector.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -O -P -V >> fault-plane.ps

gmt psconvert fault-plane.ps -A -Tj