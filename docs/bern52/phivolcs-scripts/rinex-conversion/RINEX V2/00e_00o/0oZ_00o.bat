@echo off
REM  decompressing the *.03o.gz to *.03o automatically:
REM
REM  rename *.03o.gz to *.99z for running 00e_00o.bat
REM

REM rename ????????.??o.Z ???????0.??z

gzip -d *o.Z

call 00e_00o.bat