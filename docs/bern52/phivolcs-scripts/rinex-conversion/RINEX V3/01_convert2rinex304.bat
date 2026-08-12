for %%f in (*.??o) do (
gfzrnx -finp %%~nf%%~xf -fout "::RX3::00,PHL" -smp 30
)