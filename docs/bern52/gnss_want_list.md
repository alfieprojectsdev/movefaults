# GNSS want-list — what the inventory says is still missing

**955 site-years across 271 sites.** Campaign 870, continuous 85.

Generated from `bern52_inventory.csv`, where these are cells whose **fill colour** means *Data to be retrieved* — the surveyors' own judgement recorded at the time. Regenerate with:

```bash
python3 scripts/gnss_want_list.py
```

> **What this is not.** It records what was *said* to be missing, not what is absent from the datapool today. Some of it was never collected and will not be on any drive. Cross-check against what is actually on disk with `rinex-completeness`.


## Check these first — the colour and the note disagree

**8 sites** are filled *Data to be retrieved* while carrying a text note saying the opposite (`Complete`, `Finished`, `Data complete`).

Either the data arrived and the fill was never updated, or the note is aspirational. **The first case costs nothing to confirm and shrinks the list**, so start here rather than at the top of the ranking below.

| site | years | note |
|---|---|---|
| `MALG` | 2012-2013 | Data complete; Finished |
| `MAMB` | 2010, 2012-2013 | Data complete; Finished |
| `MASI` | 1997, 1999, 2002-2004, 2009-2010, 2012, 2014 | Complete; Finished |
| `NVY2` | 2008-2009, 2011, 2013 | Complete; Finished |
| `SINA` | 2009-2010, 2012 | Complete; Finished |
| `SOLD` | 2004, 2006, 2009-2012 | Complete; Finished |
| `SOMD` | 2007, 2010-2011 | Complete; Finished |
| `TNDG` | 2013 | Finished; To retrieve |

## Sites, most-missing first

| site | site-years | years | sheet | field notes |
|---|---:|---|---|---|
| `LUZC` | 12 | 1996-2000, 2004, 2008-2009, 2011-2013, 2019 | Campaign |  |
| `LUZD` | 12 | 1996-2000, 2004, 2007, 2009-2013 | Campaign |  |
| `LUZA` | 11 | 1996-2000, 2004, 2007, 2009, 2011-2013 | Campaign | Converting; Pending |
| `LUZG` | 10 | 1996-2000, 2004, 2007, 2009, 2011, 2013 | Campaign |  |
| `LUZH` | 10 | 1996-2000, 2004, 2007, 2009, 2012-2013 | Campaign |  |
| `LUZF` | 9 | 1996-2000, 2004, 2007, 2011, 2013 | Campaign |  |
| `MASF` | 9 | 1997, 1999, 2002-2004, 2009-2010, 2012, 2014 | Campaign |  |
| `MASH` | 9 | 1997, 1999, 2002-2004, 2009-2010, 2014, 2016 | Campaign |  |
| `MASI` | 9 | 1997, 1999, 2002-2004, 2009-2010, 2012, 2014 | Campaign | Complete; Finished |
| `SIBC` | 9 | 2005-2006, 2008, 2010-2014, 2018 | Campaign |  |
| `CMN2` | 8 | 1998-2000, 2004, 2006, 2008, 2010, 2013 | Campaign |  |
| `CMS2` | 8 | 1998-2000, 2004, 2006, 2010-2011, 2013 | Campaign |  |
| `CRIS` | 8 | 1999-2000, 2004, 2008-2009, 2011, 2013, 2019 | Campaign |  |
| `LEYB` | 8 | 1994-1997, 1999, 2001, 2009, 2011 | Campaign |  |
| `LUZE` | 8 | 1996-2000, 2004, 2007, 2011 | Campaign |  |
| `MASG` | 8 | 1997, 1999, 2002-2004, 2009-2010, 2014 | Campaign |  |
| `MASJ` | 8 | 1999, 2002-2004, 2009-2010, 2012, 2014 | Campaign |  |
| `SIBE` | 8 | 2005-2006, 2008, 2010-2013, 2017 | Campaign |  |
| `ITGN` | 7 | 2008-2013, 2019 | Campaign |  |
| `LEYH` | 7 | 1995, 1999, 2001, 2009, 2011-2012, 2014 | Campaign | Converting; Pending |
| `PABL` | 7 | 1999-2000, 2004, 2008-2009, 2011, 2013 | Campaign |  |
| `SOLA` | 7 | 2004-2005, 2009-2012 | Campaign, Continuous |  |
| `BGB1` | 6 | 2000, 2004, 2008-2009, 2011, 2013 | Campaign |  |
| `BUCA` | 6 | 2006, 2008, 2010-2013 | Campaign |  |
| `BURG` | 6 | 2006, 2008, 2010-2013 | Campaign |  |
| `ILO2` | 6 | 1997, 1999, 2002, 2009-2011 | Campaign |  |
| `LEA1` | 6 | 1995, 1997, 1999, 2001, 2009, 2011 | Campaign |  |
| `LEYE` | 6 | 1997, 1999, 2001, 2009, 2011-2012 | Campaign |  |
| `LEYG` | 6 | 1995, 1997, 1999, 2009, 2011-2012 | Campaign |  |
| `MAL1` | 6 | 2002-2004, 2009-2010, 2014 | Campaign |  |
| `MRIK` | 6 | 2008-2009, 2011-2013, 2019 | Campaign |  |
| `N688` | 6 | 2006, 2008, 2010-2011, 2013, 2017 | Campaign |  |
| `QN42` | 6 | 2005-2006, 2008, 2010-2011, 2013 | Campaign |  |
| `SIBF` | 6 | 2005, 2008, 2011, 2013, 2015, 2017 | Campaign | Converting; Pending |
| `SIBK` | 6 | 2005, 2008, 2010-2011, 2013, 2017 | Campaign |  |
| `SIBL` | 6 | 2005, 2008, 2010-2011, 2013, 2017 | Campaign |  |
| `SOLB` | 6 | 2004, 2006, 2009-2012 | Campaign |  |
| `SOLD` | 6 | 2004, 2006, 2009-2012 | Campaign | Complete; Finished |
| `SOLG` | 6 | 2004, 2006, 2009-2012 | Campaign |  |
| `SOLK` | 6 | 2004-2005, 2009-2012 | Campaign |  |
| `TONA` | 6 | 1995, 1997, 1999, 2001, 2009, 2011 | Campaign |  |
| `ANQ0` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `AR17` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `AR30` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `BARA` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `BNBA` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `CEBA` | 5 | 1999, 2001, 2009, 2011-2012 | Campaign |  |
| `CRLN` | 5 | 2008-2009, 2011, 2013, 2019 | Campaign |  |
| `CUYP` | 5 | 2009, 2011-2013, 2019 | Campaign |  |
| `DIPA` | 5 | 2008-2009, 2011, 2013, 2019 | Campaign |  |
| `GUNY` | 5 | 2008, 2010-2013 | Campaign |  |
| `IFG1` | 5 | 1998, 2009-2011, 2013 | Campaign |  |
| `LEYI` | 5 | 1995, 1999, 2001, 2009, 2011 | Campaign |  |
| `LOP2` | 5 | 2006, 2008, 2010-2011, 2017 | Campaign |  |
| `MAA1` | 5 | 1998, 2009-2010, 2012, 2014 | Campaign | Processing; To retrieve |
| `MACR` | 5 | 2008-2009, 2011, 2013, 2019 | Campaign |  |
| `MAE1` | 5 | 2004, 2009-2010, 2012, 2014 | Campaign |  |
| `MAGA` | 5 | 2006, 2008-2009, 2011, 2013 | Campaign |  |
| `N132` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `NLSI` | 5 | 1997, 1999, 2001, 2009, 2011 | Campaign |  |
| `NV47` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `NVY3` | 5 | 1998, 2008-2009, 2011, 2013 | Campaign |  |
| `NVY9` | 5 | 2008-2009, 2011-2013 | Campaign |  |
| `PANC` | 5 | 2009, 2011-2013, 2015 | Campaign |  |
| `PNG5` | 5 | 2009-2011, 2013-2014 | Campaign |  |
| `SIBA` | 5 | 2005, 2008, 2010-2011, 2013 | Campaign |  |
| `SIBB` | 5 | 2005, 2008, 2010-2011, 2013 | Campaign |  |
| `SIBH` | 5 | 2005-2006, 2008, 2011, 2013 | Campaign |  |
| `SIBI` | 5 | 2005, 2008, 2011, 2013, 2017 | Campaign |  |
| `SIBJ` | 5 | 2005, 2008, 2010-2011, 2013 | Campaign |  |
| `SISN` | 5 | 2008-2009, 2011, 2013, 2019 | Campaign |  |
| `SMDS` | 5 | 2009-2013 | Campaign |  |
| `SOLH` | 5 | 2004, 2006, 2009-2011 | Campaign |  |
| `SOMM` | 5 | 2007, 2010-2011, 2013, 2017 | Campaign |  |
| `SUAL` | 5 | 2006, 2008-2009, 2011, 2013 | Campaign |  |
| `ADMI` | 4 | 1997, 1999, 2009, 2011 | Campaign |  |
| `BR14` | 4 | 2009, 2011-2013 | Campaign |  |
| `COTA` | 4 | 2009-2010, 2012-2013 | Campaign |  |
| `COTB` | 4 | 2009-2010, 2012-2013 | Campaign |  |
| `COTC` | 4 | 2009-2010, 2012-2013 | Campaign |  |
| `COTD` | 4 | 2009-2010, 2012, 2014 | Campaign |  |
| `COTG` | 4 | 2009-2010, 2012-2013 | Campaign | Pending; To retrieve |
| `CTE1` | 4 | 2009-2010, 2012-2013 | Campaign |  |
| `DINA` | 4 | 2008, 2011-2013 | Campaign |  |
| `ILN3` | 4 | 2009, 2011-2013 | Campaign |  |
| `ISB4` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `KA08` | 4 | 2009, 2011-2013 | Campaign |  |
| `LEYJ` | 4 | 2001, 2009, 2011-2012 | Campaign |  |
| `LUN2` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `MAC2` | 4 | 2009-2010, 2012, 2014 | Campaign |  |
| `NAVA` | 4 | 2001-2002, 2009, 2011 | Campaign |  |
| `NE21` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `NMJA` | 4 | 2010-2013 | Campaign | Processing; Retrieving |
| `NMSF` | 4 | 2010-2012, 2016 | Campaign |  |
| `NOMD` | 4 | 2008, 2010-2011, 2018 | Campaign |  |
| `NOMH` | 4 | 2008, 2010-2011, 2015 | Campaign |  |
| `NOML` | 4 | 2008, 2010-2011, 2017 | Campaign |  |
| `NVY2` | 4 | 2008-2009, 2011, 2013 | Campaign | Complete; Finished |
| `ODON` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `QZN3` | 4 | 2008, 2011-2013 | Campaign |  |
| `S289` | 4 | 2009, 2011-2013 | Campaign |  |
| `SINB` | 4 | 2009-2010, 2012, 2014 | Campaign |  |
| `SLSB` | 4 | 2010-2012, 2014 | Campaign |  |
| `SMAT` | 4 | 2009, 2011-2013 | Campaign |  |
| `SOLC` | 4 | 2004, 2006, 2010-2011 | Campaign |  |
| `SOLE` | 4 | 2004, 2006, 2010-2011 | Campaign |  |
| `SOLF` | 4 | 2004, 2006, 2010-2011 | Campaign |  |
| `SOLJ` | 4 | 2004, 2006, 2010-2011 | Campaign |  |
| `SOMB` | 4 | 2007, 2010-2011, 2017 | Campaign |  |
| `SOME` | 4 | 2007, 2010-2011, 2013 | Campaign |  |
| `SOMG` | 4 | 2007, 2010-2011, 2013 | Campaign |  |
| `SOMJ` | 4 | 2007, 2010-2011, 2017 | Campaign |  |
| `SOMK` | 4 | 2007, 2011, 2016-2017 | Campaign |  |
| `SRQE` | 4 | 2009-2011, 2013 | Campaign |  |
| `TONF` | 4 | 1999, 2001, 2009, 2011 | Campaign |  |
| `TRC3` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `ZBS1` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `ZBS3` | 4 | 2008-2009, 2011, 2013 | Campaign |  |
| `BSCS` | 3 | 2009, 2011, 2013 | Campaign |  |
| `BULA` | 3 | 2010, 2012-2013 | Continuous |  |
| `CALI` | 3 | 2010-2012 | Campaign |  |
| `CATM` | 3 | 2008, 2010-2011 | Campaign |  |
| `CCA5` | 3 | 1998, 2012-2013 | Campaign |  |
| `CEB1` | 3 | 2009, 2011-2012 | Campaign |  |
| `CEBB` | 3 | 1997, 1999, 2001 | Campaign |  |
| `CEBC` | 3 | 2009, 2011-2012 | Campaign |  |
| `CEBD` | 3 | 2009, 2011-2012 | Campaign | Converting; Pending |
| `COTF` | 3 | 2009-2010, 2012 | Campaign |  |
| `JOSE` | 3 | 2010, 2012-2013 | Continuous | Processing; To retrieve |
| `LAG1` | 3 | 1998, 2012-2013 | Campaign |  |
| `LAGW` | 3 | 2012-2013, 2019 | Continuous |  |
| `LEC1` | 3 | 2001, 2009, 2011 | Campaign |  |
| `LEYD` | 3 | 2009, 2011, 2017 | Campaign |  |
| `LUBU` | 3 | 2010-2011, 2013 | Campaign |  |
| `LUN1` | 3 | 2008-2009, 2011 | Campaign | Processing; To retrieve |
| `MAB1` | 3 | 2010, 2012, 2014 | Campaign |  |
| `MAD2` | 3 | 2009-2010, 2014 | Campaign |  |
| `MAMB` | 3 | 2010, 2012-2013 | Continuous | Data complete; Finished |
| `MDQT` | 3 | 2010-2011, 2013 | Campaign |  |
| `NAUJ` | 3 | 2010, 2012-2013 | Continuous |  |
| `NLL2` | 3 | 2009, 2011-2012 | Campaign | Processing; To retrieve |
| `NLSN` | 3 | 2009, 2011-2012 | Campaign |  |
| `NMAB` | 3 | 2010-2012 | Campaign |  |
| `NMCO` | 3 | 2010-2012 | Campaign |  |
| `NMLM` | 3 | 2010-2012 | Campaign |  |
| `NMMB` | 3 | 2010-2012 | Campaign | Converting; Pending |
| `NMSM` | 3 | 2010-2012 | Campaign |  |
| `NOMA` | 3 | 2008, 2010-2011 | Campaign |  |
| `NOMC` | 3 | 2007, 2010-2011 | Campaign |  |
| `NOME` | 3 | 2008, 2010-2011 | Campaign |  |
| `NOMF` | 3 | 2007, 2010-2011 | Campaign |  |
| `NOMG` | 3 | 2007, 2010-2011 | Campaign |  |
| `NOMI` | 3 | 2008, 2010-2011 | Campaign |  |
| `NOMK` | 3 | 2007, 2010-2011 | Campaign |  |
| `NPAK` | 3 | 2010-2012 | Campaign |  |
| `NPAL` | 3 | 2010-2012 | Campaign |  |
| `PUER` | 3 | 2010, 2012-2013 | Continuous |  |
| `RCPS` | 3 | 2010-2012 | Campaign |  |
| `ROXA` | 3 | 2010, 2012-2013 | Continuous |  |
| `SABL` | 3 | 2010, 2012-2013 | Continuous | Pending; To convert |
| `SINA` | 3 | 2009-2010, 2012 | Campaign | Complete; Finished |
| `SINC` | 3 | 2009-2010, 2012 | Campaign |  |
| `SIND` | 3 | 2009-2010, 2012 | Campaign |  |
| `SINE` | 3 | 2009-2010, 2012 | Campaign |  |
| `SINF` | 3 | 2009-2010, 2012 | Campaign |  |
| `SMCP` | 3 | 2010-2012 | Campaign |  |
| `SMDM` | 3 | 2010-2012 | Campaign |  |
| `SMMM` | 3 | 2010-2012 | Campaign |  |
| `SOLI` | 3 | 2009-2011 | Campaign |  |
| `SOMA` | 3 | 2007, 2010-2011 | Campaign |  |
| `SOMC` | 3 | 2007, 2010-2011 | Campaign |  |
| `SOMD` | 3 | 2007, 2010-2011 | Campaign | Complete; Finished |
| `SOMF` | 3 | 2007, 2010-2011 | Campaign |  |
| `SOMH` | 3 | 2007, 2010-2011 | Campaign |  |
| `SOML` | 3 | 2007, 2010-2011 | Campaign |  |
| `TAGB` | 3 | 2008, 2010-2011 | Campaign | Processing; To retrieve |
| `TARL` | 3 | 2006, 2008-2009 | Campaign |  |
| `AB14` | 2 | 2009, 2011 | Campaign |  |
| `AURA` | 2 | 2012-2013 | Continuous |  |
| `BACO` | 2 | 2012-2013 | Continuous |  |
| `BAGU` | 2 | 2012-2013 | Continuous |  |
| `BONT` | 2 | 2012-2013 | Continuous |  |
| `CATA` | 2 | 2012-2013 | Continuous | Pending; To convert |
| `COTH` | 2 | 2009-2010 | Campaign |  |
| `IBAZ` | 2 | 2012-2013 | Continuous |  |
| `JONA` | 2 | 2013, 2017 | Campaign |  |
| `LEB1` | 2 | 2009, 2011 | Campaign |  |
| `LEYC` | 2 | 2009, 2011 | Campaign |  |
| `LEYF` | 2 | 2009, 2011 | Campaign |  |
| `MABN` | 2 | 2012-2013 | Continuous |  |
| `MALG` | 2 | 2012-2013 | Continuous | Data complete; Finished |
| `MARK` | 2 | 2013, 2017 | Continuous |  |
| `MDVS` | 2 | 2010, 2012 | Campaign |  |
| `MPCK` | 2 | 2010, 2014 | Campaign |  |
| `MSW3` | 2 | 2010, 2012 | Campaign |  |
| `NLCE` | 2 | 2009, 2011 | Campaign |  |
| `NLCR` | 2 | 2009, 2011 | Campaign |  |
| `NLL1` | 2 | 2009, 2011 | Campaign |  |
| `NLSB` | 2 | 2009, 2011 | Campaign |  |
| `NOMB` | 2 | 2010-2011 | Campaign |  |
| `NPIE` | 2 | 2010-2011 | Campaign |  |
| `SINH` | 2 | 2010, 2014 | Campaign |  |
| `SMCL` | 2 | 2010-2011 | Campaign |  |
| `SMD1` | 2 | 2010, 2017 | Campaign |  |
| `SMDB` | 2 | 2010-2011 | Campaign |  |
| `SMDT` | 2 | 2010, 2012 | Campaign |  |
| `SMSK` | 2 | 2010, 2012 | Campaign |  |
| `SOLL` | 2 | 2010-2011 | Campaign |  |
| `SOMI` | 2 | 2007, 2011 | Campaign |  |
| `TAWI` | 2 | 2012-2013 | Continuous | Pending; To convert |
| `URDT` | 2 | 2012-2013 | Continuous |  |
| `VIGN` | 2 | 2012-2013 | Continuous |  |
| `VRC4` | 2 | 2007, 2015 | Campaign |  |
| `ALAB` | 1 | 2013 | Continuous |  |
| `ANGT` | 1 | 2013 | Continuous |  |
| `ANTP` | 1 | 2013 | Continuous |  |
| `APAR` | 1 | 2013 | Continuous |  |
| `ATIM` | 1 | 2013 | Continuous |  |
| `BALA` | 1 | 2013 | Continuous |  |
| `BANI` | 1 | 2013 | Campaign |  |
| `BASC` | 1 | 2012 | Continuous |  |
| `BLN2` | 1 | 2012 | Continuous |  |
| `BONG` | 1 | 2012 | Campaign |  |
| `BRGC` | 1 | 2012 | Continuous | Pending; To convert |
| `BTUN` | 1 | 2013 | Continuous |  |
| `BUGS` | 1 | 2013 | Continuous |  |
| `CABN` | 1 | 2019 | Continuous |  |
| `CACA` | 1 | 2013 | Continuous |  |
| `CALC` | 1 | 2013 | Continuous |  |
| `CEBM` | 1 | 2015 | Campaign |  |
| `CLAV` | 1 | 2012 | Continuous |  |
| `CMGN` | 1 | 2013 | Continuous |  |
| `ELNA` | 1 | 2013 | Continuous |  |
| `GUNG` | 1 | 2013 | Continuous |  |
| `INFA` | 1 | 2013 | Continuous | Processing; To retrieve |
| `ITBA` | 1 | 2012 | Continuous |  |
| `KBNK` | 1 | 2015 | Campaign |  |
| `KIBU` | 1 | 2013 | Campaign |  |
| `LABO` | 1 | 2013 | Continuous |  |
| `LEY1` | 1 | 2014 | Campaign |  |
| `LEY5` | 1 | 2014 | Campaign |  |
| `LGYE` | 1 | 2013 | Continuous |  |
| `LUCB` | 1 | 2013 | Continuous |  |
| `LUZN` | 1 | 2012 | Campaign |  |
| `LUZP` | 1 | 2012 | Campaign |  |
| `MACL` | 1 | 2014 | Campaign |  |
| `MALA` | 1 | 2013 | Continuous |  |
| `MALS` | 1 | 2013 | Continuous |  |
| `MASM` | 1 | 2014 | Campaign |  |
| `MASU` | 1 | 2014 | Campaign |  |
| `MATA` | 1 | 2013 | Campaign |  |
| `MAUB` | 1 | 2013 | Continuous |  |
| `MUNT` | 1 | 2013 | Continuous |  |
| `MUNZ` | 1 | 2012 | Continuous |  |
| `PDCS` | 1 | 2014 | Campaign |  |
| `PNBO` | 1 | 2013 | Continuous |  |
| `PTBN` | 1 | 2012 | Continuous |  |
| `PWSU` | 1 | 2012 | Campaign |  |
| `QZN1` | 1 | 2013 | Campaign |  |
| `QZNA` | 1 | 2013 | Campaign |  |
| `SING` | 1 | 2010 | Campaign |  |
| `SJAQ` | 1 | 2010 | Campaign |  |
| `SPAB` | 1 | 2013 | Continuous |  |
| `TANY` | 1 | 2013 | Continuous |  |
| `TCGN` | 1 | 2013 | Continuous |  |
| `TGDN` | 1 | 2012 | Continuous |  |
| `TNDG` | 1 | 2013 | Continuous | Finished; To retrieve |
| `TONU` | 1 | 2001 | Campaign |  |
| `TRLC` | 1 | 2015 | Campaign |  |
| `TUAO` | 1 | 2012 | Continuous |  |
| `TUKU` | 1 | 2010 | Campaign |  |

## Scanning against this

```bash
# every site code, one per line
python3 scripts/gnss_want_list.py --sites

# as a regex, for a single pass over a mounted bay
python3 scripts/gnss_want_list.py --grep

# then, per drive
uv run drive-arch scan /mnt/bay1
```

**Mount anything from the Backup Plus era read-only.** That drive corrupts fresh writes and is retired read-only — see `SETTLED.md`.

