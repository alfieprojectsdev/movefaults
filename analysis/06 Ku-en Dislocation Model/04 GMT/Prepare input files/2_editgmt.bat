@echo off
setlocal enabledelayedexpansion

set "search=^> -Z "
set "replace=^> -Z"

set "textFile4=gmt_faultslip_plane_1.gmt"
for /f "delims=" %%i in ('type "%textFile4%" ^& break ^> "%textFile4%" ') do (
    set "line=%%i"
    >>"%textFile4%" echo(!line:%search%=%replace%!)
)

set "textFile5=gmt_faultslip_xy_1.gmt"
for /f "delims=" %%i in ('type "%textFile5%" ^& break ^> "%textFile5%" ') do (
    set "line=%%i"
    >>"%textFile5%" echo(!line:%search%=%replace%!)
)

set "textFile6=gmt_faultslip_xyz_1.gmt"
for /f "delims=" %%i in ('type "%textFile6%" ^& break ^> "%textFile6%" ') do (
    set "line=%%i"
    >>"%textFile6%" echo(!line:%search%=%replace%!)
)

endlocal