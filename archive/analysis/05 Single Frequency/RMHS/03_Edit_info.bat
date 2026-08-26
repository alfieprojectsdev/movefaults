for %%f in (???????0.??O) do (
	teqc_2018_12.exe -O.at "UBLOX " -O.rt "UBLOX " -O.mo "RMHS" -O.mn "RMHS" -O.ag "PHIVOLCS" -O.o "GPS Team" -R -S -E -C -J -O.dec 30 %%~nf%%~xf > %%~nf%%~xfA
	REM teqc_2018_12.exe -O.at "UBLOX " -O.rt "UBLOX " -O.mo "PRJ4" -O.mn "PRJ4" -O.ag "PHIVOLCS" -O.o "GPS Team" -R -S -E -C -J -O.dec 30 %%~nf%%~xf > %%~nf%%~xfA
	REM teqc_2018_12.exe -O.at "UBLOX " -O.rt "UBLOX " -O.mo "ADMA" -O.mn "ADMA" -O.ag "PHIVOLCS" -O.o "GPS Team" -R -S -E -C -J -O.dec 30 %%~nf%%~xf > %%~nf%%~xfA
)

mkdir tmp
move ???????0.??O tmp
REM Dear Operator: Please inspect decimated RINEX; compare against original undecimated RINEX