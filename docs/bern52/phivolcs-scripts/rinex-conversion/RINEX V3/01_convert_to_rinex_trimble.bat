for %%f in (*.t??) do (
 	gfzrnx -finp %%~nf%%~xf -fout ::RX3::00,PHL -sei in
)