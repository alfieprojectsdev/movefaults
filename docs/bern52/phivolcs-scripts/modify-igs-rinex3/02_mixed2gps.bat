for %%i in (*01D_30S_MO.rnx) do (
	gfzrnx -finp %%~ni%%~xi -fout %%~ni_G%%~xi -satsys G
	rnx2crx %%~ni_G%%~xi -f
)
move *01D_30S_MO.rnx tmp
move *01D_30S_MO_G.rnx tmp
ren ????00???_R_20?????0000_01D_30S_MO_G.crx ????00???_R_20?????0000_01D_30S_MO.crx