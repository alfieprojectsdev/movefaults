ECHO off
rem --------------------------------------------------------
rem
rem Copyright:   Leica Geosystems AG
rem Author:      Networks and Reference Stations
rem Creation:    24.02.2012
rem Last change: 24.02.2012
rem
rem Info:
rem The following application are needed:
rem - Leica MdbConverter
rem - mdb2rnx3.vbs
rem If not installed to the default directories, the PATH
rem and SCRIPTNAME variable need to be modified below.
rem More info can be found in section Syntax or via /?
rem --------------------------------------------------------

rem --------------------------------------------------------
rem check syntax and print some help if syntax is incorrect
cls
IF [%1]==[] GOTO Syntax
IF [%1]==[/?] GOTO Syntax
IF [%1]==[/h] GOTO Syntax
IF [%1]==[/help] GOTO Syntax
IF [%2]==[] GOTO Syntax
IF [%3]==[] GOTO Syntax

if not exist %1 (
	echo.
	echo Bad first input argument!
	echo Source directory does not exist
	echo.
	echo Your input: %1
	echo.
	goto Error
)
if not exist %3 (
	echo.
	echo Bad third input argument!
	echo Target directory does not exist
	echo.
	echo Your input: %3
	echo.
	goto Error
)

rem --------------------------------------------------------
rem Always Win64 
set PathCScript=c:\Windows\System32
set PathProgramFiles="c:\Program Files"

rem --------------------------------------------------------
rem expand path variable with path to used tools
set PATH=%PATH%;%PathProgramFiles%"\Leica Geosystems\MdbConverter\"
set SCRIPTNAME=%PathProgramFiles%"\Leica Geosystems\MdbConverter\mdb2rnx3.vbs"
rem --------------------------------------------------------

rem --------------------------------------------------------
rem need to copy input paths into other variable
set LeftPath=%1%
set FileNamePattern=%2%
set RightPath=%3%

rem --------------------------------------------------------
rem get all files with matching pattern in all subdirs (first path)
dir /s /b %LeftPath%\%FileNamePattern% > filelist.tmp
rem use "delims=!" to allow blanks in file name 
rem (! is not allowed in file name and therefore can't be found)
for /f "delims=!" %%i in (filelist.tmp) do (
	echo processing "%%i"...
	%PathCScript%\cscript %SCRIPTNAME% "%%i" %RightPath%
)
del filelist.tmp

rem --------------------------------------------------------
GOTO Success

:Syntax
echo.
echo %~n0 SOURCE_PATH FILE_NAME_PATTERN TARGET_PATH
echo.
echo Converts all files matching the file name pattern FILE_NAME_PATTERN
echo from all subdirectories of SOURCE_PATH to RINEX v2 format and 
echo stores output in the directory TARGET_PATH.
echo. 
echo Options:
echo. 
echo Example: %0% ^. *.m00 ^.
echo.
rem SET /P VarEnd=Press ENTER.
GOTO End

:Error
ECHO +++++++++++++++++++++++++++++++++++++++++++++
ECHO + Attention: Error during process!
ECHO + See error message above.
ECHO +++++++++++++++++++++++++++++++++++++++++++++
SET /P VarEnd=Press ENTER.
GOTO End

:Success
ECHO ---------------------------------------------
ECHO ... successfully!
ECHO ---------------------------------------------
GOTO End

:End
