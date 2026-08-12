for %%k in (*01D_30S_MO.crx) do (
	7z a -tgzip %%~nk%%~xk.gz %%~nk%%~xk
)
del *01D_30S_MO.crx