@echo off
REM  decompressing the *.99e to *.99o automatically:
REM
REM  decompressing     *.99e to *.99d
REM  restore           *.99d to *.99o
REM
     del  crz2x.tmp
     del  crz2x.bat
     for %%f in (*.9?E) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.0?E) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.1?E) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.2?E) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.3?E) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.9?d) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.0?d) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.1?d) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.2?d) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.3?d) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.0?x) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.1?x) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.2?x) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.3?x) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.9?z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.0?z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.1?z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.2?z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.3?z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.9?d.Z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.0?d.Z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.1?d.Z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.2?d.Z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     for %%f in (*.3?d.Z) do ECHO call crz2rnx1 %%f >> crz2x.tmp
     sort<crz2x.tmp>crz2x.bat
REM  c:\pe2\pe2 crz2x.bat
     call crz2x.bat
REM
REM  for %%f in (*.9?z) do ECHO call crz2rnx1 %%f >> CRZ2X.BAT
REM
REM  decompressing the *.99z to *.99o automatically:
REM
REM  decompressing     *.99z to *.99o
REM
