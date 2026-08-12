@echo off
REM  decompressing the *.03o.gz to *.03o automatically:
REM
REM  rename *.03o.gz to *.99z for running 00e_00o.bat
REM

gzip -d *d.Z
gzip -d *p.Z
gzip -d *n.Z
gzip -d *b.Z

call 00e_00o.bat