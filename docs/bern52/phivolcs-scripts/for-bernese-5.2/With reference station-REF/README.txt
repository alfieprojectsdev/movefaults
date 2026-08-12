BERNESE 5.2: TIME SERIES
TO INPUT REFERENCE STATION (which will be the coordinate system origin)
INPUT: F1*.CRD
1. Copy all F1*.CRD files to a single folder. e.g  c:\PIVSCRD\
2. Copy 00_CRD and RUN_v2 to the folder you created. e.g to c:\PIVSCRD\
3. RUN 00_CRD by double clicking the BAT file. You can delete the F1CRD folder after.
	Choose NAMRIA: If the IGS stations are AIRA, ALIC, BTNG, CUSV, DAEJ, DARW, GUUG, MCIL, NTUS, PIMO, PNGM & TNML
	Choose PIVS: If the IGS stations are ALIC, BAKO, DAEJ, DARW, GUAM, KUNM, NTUS, PERT, PIMO, PTAG, SHAO, TNML, TSKB, TWTF, USUD & WUHN
4. RUN RUNX.py by double clicking the PY file. Input S01R for the reference station.
5. Copy vel_line_v1.m to PLOTS folder. e.g to c:\PIVSCRD\PLOTS Edit list of sites in 123 file. Open Octave software. Change current directory. Type vel_line in the command window then press ENTER.
OUTPUT: SITE.jpg and Velocity_rover(regress)_10

Done! :)

For vel_line version 2 or later,
Dashed lines means:
Black = Transition from Bernese 5.0 to 5.2
Blue = Manually entered/antenna changes based on site logs


LAST UPDATE: JULY 19, 2021 10:08 AM
