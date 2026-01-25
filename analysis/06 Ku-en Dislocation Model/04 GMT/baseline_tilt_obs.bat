gmt set FONT_LABEL 11p,Helvetica
gmt set FONT_ANNOT_PRIMARY 11p,Helvetica

rem gmt grdimage PH_topo_hr.nc -R122.50/124.50/11.63/13.10 -IPH_topo_hr.grad -Cgray_luzon.cpt -JM18 -P -K > baseline_tilt_obs.ps
gmt pscoast -R122.50/124.50/11.63/13.10 -JM18 -W0.2p,black -Swhite -Df -P -Ba1f1 -BWSne -Lf123.00/11.75/5.0/5.0/50+l --FONT_LABEL=10 -K > baseline_tilt_obs.ps

gmt psxy faultlines_updated2020.gmt -R -J -Sf0.01/0.01+f -W0.1p,black -O -K -P >> baseline_tilt_obs.ps
gmt psxy faultlines_masbate.gmt -R -J -Sf0.01/0.01+f -W1.4p,red -O -K -P >> baseline_tilt_obs.ps

rem echo 122.6875124 12.3684212   SIBI | gmt psxy -R -J -Sa1.0 -W0.5p,black -Gblue -K -O -P >> baseline_tilt_obs.ps
echo 124.00   12.10  Masbate Fault | pstext -JM -R -N -F+a305+f9p,Helvetica -K -O -V >> baseline_tilt_obs.ps
echo 122.50   13.10  16  0  1  LT Observation | pstext -J -R -K -O -D0.1i/-0.1i -V >> baseline_tilt_obs.ps

rem gmt psvelo Vel_cont_masbate_wrtSIBI.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -K -O -P -V >> baseline_tilt_obs.ps
rem gmt psvelo Vel_camp_masbate_wrtSIBI.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -K -O -P -V >> baseline_tilt_obs.ps

gmt psxy baseline_obs_2-1.gmt -J -R -W4p,black -K -O -V >> baseline_tilt_obs.ps
gmt psxy baseline_obs_2-2.gmt -J -R -W3p+cl -Celg.cpt -Sv1p+s -K -O -V >> baseline_tilt_obs.ps

gmt psxy coordinates.xy -R -J -St0.3 -W0.5p,black -Gblack -K -O -P >> baseline_tilt_obs.ps

rem gmt pslegend legend_rb.txt -R -J -Dg124.10/12.90+w1.2i/0.2i -K -O -P -V >> baseline_tilt_obs.ps
rem gmt pslegend legend.txt -R -J -Dg123.96/12.96+w1.8i/0.35i -F+gwhite+p0.8p,black -K -O -P -V >> baseline_tilt_obs.ps
gmt psscale -B0.2+l"vertical tilt rate (\265strain/yr)" -Dx3.1i/-0.35i+w6.1i/0.12i+jTC+h -Celg.cpt -O -V >> baseline_tilt_obs.ps
rem gmt psvelo legend_vector.txt -R -J -Se0.10/0.90/0 -W0.5p,black -A0.10/0.20/0.16 -Gblack -O -P -V >> baseline_tilt_obs.ps

gmt psconvert baseline_tilt_obs.ps -A -Tj