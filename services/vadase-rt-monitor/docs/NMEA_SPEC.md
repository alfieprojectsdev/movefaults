LDM is a Leica Displacement Measurement and LVM is a Leica Velocity Measurement.

…and it should be correct the EVENT Viewer will indicate the start of when a significant event has started and when it returns to the background value.

There is a NEW firmware just released that will Automatically generate an EMAIL based upon these VADASE thresholds being exceeded.

 **LDM** **- Leica Displacement Measurement**

**Syntax**

$--LDM,hhmmss.ss, mmddyy, hhmmss.ss , mmddyy, E.EEEE, N.NNNN, U.UUUU, v.v, v.v, v.v, c.c , c.c , c.c, q.q, xx, a, a, a \*hh<CR><LF>

**Description of fields**

| **Field** | **Description** |
| --- | --- |
| $--LDM | Header including talker ID |
| hhmmss.ss | UTC time of displacement (Check official NMEA section 6.2.1) |
| mmddyy | UTC date of displacement |
| hhmmss.ss | UTC time of start of displacement computation. This time refers to the time when the displacement is reset to 0, i.e. after enabling the stream, or changing the receiver reference position. |
| mmddyy | UTC date of start of displacement computation. |
| E.EEEE | East component of the receiver’s displacement, \[m\] |
| N.NNNN | North component of the receiver’s displacement, \[m\] |
| U.UUUU | Up component of the receiver’s displacement, \[m\] |
| v.v | Variance of the East displacement component, \[m2\] |
| v.v | Variance of the North displacement component, \[m2\] |
| v.v | Variance of the Up displacement component, \[m2\] |
| c.c | Covariance between the East and North displacement components, \[m2\] |
| c.c | Covariance between the East and Up displacement components, \[m2\] |
| c.c | Covariance between the Up and North displacement components, \[m2\] |
| q.q | 3D displacement Component Quality (CQ<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[1]</span></sup>), \[m\] |
| xx | Number of satellites whose observations have been used to calculate the velocity used to compute the displacement value |
| a | Last displacement reset indicator: 0 = Last reset happened after enabling the NMEA stream 1 = Last reset happened after changing receiver reference position |
| a.a<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[2]</span></sup> | Epoch to epoch data completeness ratio. It indicates the ratio of available observations for displacement computation divided by the number of complete observations between the last and current epoch. Range from 0 to 1:  0: No observations are available  0.x: Parts of observations are available  1: All observations are available |
| a.a<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[3]</span></sup> | Overall data completeness ratio. It indicates the ratio of available observations for displacement computation divided by the number of complete observations between the start of displacement computation and the current epoch. Range from 0 to 1:  0: No observations are available  0.x: Parts of observations are available  1: All observations are available |
| \*hh | Checksum |
| <CR> | **C**arriage **R**eturn |
| <LF> | **L**ine **F**eed |

<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[1]</span></sup>   CQ stands for Component Quality and is given by the sum of the standard deviation and of the contribution of empirical assumptions. Therefore, CQ accounts for measurements noise, environmental conditions (e.g. tropospheric and ionospheric delay) and for the influence of the different constellations on the components.

<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[2]</span></sup>   If the user configures a NMEA LDM stream with a rate equal to the receiver positioning rate, then for each epoch one observation is used for displacement calculation. In this case, the epoch to epoch data completeness ratio will be equal to 1, i.e. observation is available and used for displacement computation, or 0, i.e. no observation is available and no displacement is computed at this epoch. If the user configures a 1 Hz epoch rate NMEA LDM stream and the receiver positioning rate is 20 Hz, then for each epoch 20 observations are used for displacement calculation. In this case, the epoch to epoch data completeness ratio can be equal to 1, i.e. all 20 observations are available and used for displacement computation, or 0, i.e. no observations are available and no displacement is computed at this epoch, or any value between 0 and 1, e.g. 0.2, i.e. 4 observations out of 20 possible are used for displacement computation.

<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[3]</span></sup>   Overall data completeness ratio is reset after changing the reference position or enabling/disabling the Velocity & Displacement Engine.

**Example**

**Standard Talker ID**

$GNLDM,113805.50,030215,113805.50,030215,0.0101,0.0204,0.0459,0.0021,0.0020,0.0041,0.00021,0.00023,0.00041,0.05,19,0,1,1\*47

**LVM** **- Leica Velocity Measurement**

**Syntax**

$--LVM, hhmmss.ss, mmddyy, E.EEEE, N.NNNN, U.UUUU, v.v, v.v, v.v, c.c , c.c , c.c, q.q, xx\*hh<CR><LF>

**Description of fields**

| **Field** | **Description** |
| --- | --- |
| $--LVM | Header including talker ID |
| hhmmss.ss | UTC time of velocity (Check official NMEA section 6.2.1) |
| mmddyy | UTC date of velocity |
| E.EEEE | East component of the receiver’s velocity, \[m/s\] |
| N.NNNN | North component of the receiver’s velocity, \[m/s\] |
| U.UUUU | Up component of the receiver’s velocity, \[m/s\] |
| v.v | Variance of the East velocity component, \[m2/s2\] |
| v.v | Variance of the North velocity component, \[m2/s2\] |
| v.v | Variance of the Up velocity component, \[m2/s2\] |
| c.c | Covariance between the East and North velocity components, \[m2/s2\] |
| c.c | Covariance between the East and Up velocity components, \[m2/s2\] |
| c.c | Covariance between the Up and North velocity components, \[m2/s2\] |
| q.q | 3D velocity Component Quality (CQ<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[1]</span></sup>), \[m/s\] |
| xx | Number of satellites whose observations have been used to calculate the velocity values |
| \*hh | Checksum |
| <CR> | **C**arriage **R**eturn |
| <LF> | **L**ine **F**eed |

<sup><span style="font-size:6pt;font-family:Arial,sans-serif;color:black">[1] &nbsp;&nbsp;</span></sup>   CQ stands for Component Quality and is given by the sum of the standard deviation and of the contribution of empirical assumptions. Therefore, CQ accounts for measurements noise, environmental conditions (e.g. tropospheric and ionospheric delay) and for the influence of the different constellations on the components.

**Example**

**Standard Talker ID**

$GNLVM,113805.50,030215,0.0011,0.0021,0.0015,0.0023,0.0040,0.0092, 0.00012,0.00015,0.00035,0.043561,19\*47