@echo off
setlocal enabledelayedexpansion

set "search=X -Z"
set "replace=^>"

set "textFile1=baseline_cal_1.gmt"
set "textFile1-1=baseline_cal_1-1.gmt"
for /f "tokens=* delims=" %%i in ('type "%textFile1%"') do (
    set "line=%%i" 
    >>"%textFile1-1%" echo(!line:%search%=%replace%!)
)

set "textFile2=baseline_obs_1.gmt"
set "textFile2-1=baseline_obs_1-1.gmt"
for /f "tokens=* delims=" %%i in ('type "%textFile2%"') do (
    set "line=%%i"
    >>"%textFile2-1%" echo(!line:%search%=%replace%!)
)

set "textFile3=baseline_res_1.gmt"
set "textFile3-1=baseline_res_1-1.gmt"
for /f "tokens=* delims=" %%i in ('type "%textFile3%"') do (
    set "line=%%i"
    >>"%textFile3-1%" echo(!line:%search%=%replace%!)
)

set "search=X -Z    "
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