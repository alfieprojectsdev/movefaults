for %%k in (*_30S_MO.crx) do (
	7z a -tgzip %%~nk%%~xk.gz %%~nk%%~xk
)
del *_30S_MO.crx