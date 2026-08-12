@ECHO OFF
rem      IF "%2" == "" GOTO ERROR
rem
      ECHO Decompressing file %2 from file %1
      gzip -d %1
rem
      GOTO END
:ERROR
      ECHO Usage: DECOMPR filinp filout
:END
