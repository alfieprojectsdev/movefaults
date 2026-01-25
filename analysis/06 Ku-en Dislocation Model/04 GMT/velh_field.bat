gmt set FONT_LABEL 9p,Helvetica
gmt set FONT_ANNOT_PRIMARY 11p,Helvetica

gmt grdimage PH_topo_hr.nc -R122.50/124.50/11.63/13.10 -IPH_topo_hr.grad -Cgray_luzon.cpt -JM18 -P -K > velh_field.ps
gmt pscoast -R122.50/124.50/11.63/13.10 -JM18 -W0.2p,black -Swhite -Df -P -Ba1f1 -BWSne -Lf123.00/11.75/5.0/5.0/50+l --FONT_LABEL=10 -O -K >> velh_field.ps

gmt psxy faultlines_updated2020.gmt -R -J -Sf0.01/0.01+f -W0.1p,black -O -K -P >> velh_field.ps
gmt psxy faultlines_masbate.gmt -R -J -Sf0.01/0.01+f -W1.4p,red -O -K -P >> velh_field.ps

gmt psxy coordinates.xy -R -J -St0.3 -W0.5p,black -Gblack -K -O -P >> velh_field.ps
echo 122.6875124 12.3684212   SIBI | gmt psxy -R -J -Sa1.0 -W0.5p,black -Gblue -K -O -P >> velh_field.ps
echo 124.00   12.10  Masbate Fault | pstext -JM -R -N -F+a305+f9p,Helvetica -K -O -V >> velh_field.ps

gmt psvelo Vel_cont_masbate_wrtSIBI.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblue -K -O -P -V >> velh_field.ps
gmt psvelo Vel_camp_masbate_wrtSIBI_replot.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gyellow -K -O -P -V >> velh_field.ps

gmt pslegend legend_rb.txt -R -J -Dg124.10/12.90+w1.2i/0.2i -K -O -P -V >> velh_field.ps
gmt pslegend legend.txt -R -J -Dg123.96/12.96+w1.8i/0.35i -F+gwhite+p0.8p,black -K -O -P -V >> velh_field.ps
gmt psvelo legend_vector.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -O -P -V >> velh_field.ps

gmt psconvert velh_field.ps -A -Tj