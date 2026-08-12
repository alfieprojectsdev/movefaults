REM step 1: copy all s01r???0.??d.Z files into this folder:
REM c:\Users\PHIVOLCS\Local Programs\RNXCMP_4.0.7_Windows_bcc\bin\COMPRESS.EXE
REM c:\Users\PHIVOLCS\Local Programs\RNXCMP_4.0.7_Windows_bcc\bin\crx2rnx.exe
REM c:\Users\PHIVOLCS\Local Programs\RNXCMP_4.0.7_Windows_bcc\bin\rnx2crx.exe
REM c:\Users\PHIVOLCS\Local Programs\RNXCMP_4.0.7_Windows_bcc\bin\splname.exe
REM might also need to: rename S01R???0.??e to S01R???0.??d.Z

REM step 2: decompress *.Z to Hatanaka
REM Note: sometimes need to rename S01R????.??e to S01R????.??e.Z for this step
REM gzip package available at http://getgnuwin32.sourceforge.net/
>gzip -df s01r*0.??d.Z

REM step 3: convert from Hatanaka format to RINEX
REM .\CRZ2RNX.BAT *.??e

REM executed successfully: 2022/04/25
>.\CRZ2RNX.BAT *.??d

REM step 4: compress regular RINEX files
>gzip s01r*0.??o

REM step 5: move / copy to shared google drive and inform Abs/Cass