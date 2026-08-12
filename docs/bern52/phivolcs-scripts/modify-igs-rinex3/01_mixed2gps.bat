mkdir tmp

for %%f in (*.gz) do (
	7z e -tgzip %%~nf%%~xf
	for %%f in (*01D_30S_MO.crx) do (
		crx2rnx %%~nf%%~xf -f
	)
)

move *_01D_30S_MO.crx.gz tmp
move *_01D_30S_MO.crx tmp