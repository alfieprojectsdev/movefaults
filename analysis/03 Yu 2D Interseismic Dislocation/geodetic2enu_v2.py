#Install PyMap3d and PyGeodesy (python -m pip install "module")
#REFERENCES: https://github.com/mrJean1/PyGeodesy; https://www.mathworks.com/help/map/ellipsoid-geoid-and-orthometric-height.html
#https://stackoverflow.com/questions/22564727/evaluating-geoid-heights-using-egms-in-python

import pymap3d
import pygeodesy
from pygeodesy import GeoidKarney as GeoidXyz
from pygeodesy.ellipsoidalKarney import LatLon

# EDIT HERE ##############################
#local point
lat = 12.56773409; #latitude
lon = 122.13319276; #longitude
alt = 10; #orthometric height https://www.dcode.fr/earth-elevation
##########################################

#s01r
X = -2886620.16895;
Y = 5082944.81347;
Z = 2543377.25908;

ginterpolator = GeoidXyz("C:\ProgramData\GeographicLib\geoids\egm2008-1.pgm")
gh = ginterpolator(LatLon(lat,lon))
eH = gh + alt #meters

lat0, lon0, alt0 = pymap3d.ecef2geodetic(X, Y, Z, deg=True)

east, north, up = pymap3d.geodetic2enu(lat, lon, eH, lat0, lon0, alt0)

print(east)
print(north)
print(up)

input('Press ENTER to exit')