# Date created: March 2020

import glob
import os
import time

import pymap3d


def start():
    def getxyz():
        print("\t ======================================================================== \n")
        print("\t \t \t \t WELCOME GPS TEAM! :) \n")
        print("\t Transform ECEF (XYZ) to ENU (East-North-Up) coordinates using PYMAP3D \n")
        print(
            "\t About this version: The local ENU coordinates are fixed to your input \n \t \t \t \t LLA coordinates."
        )
        print("\t \t INPUT: CRD files \t \t OUTPUT: PLOT files \n")
        print("\t ======================================================================== \n")
        input("\t Press Enter to continue \n")
        print("\t ========================= Getting XYZ coordinates ====================== \n")
        for files in glob.glob("*.KIN"):
            with open(files) as lines:
                for _ in range(5):
                    next(lines)
                for line in lines:
                    x = line.split()
                    if len(line.split()) == 8:
                        with open("XYZ", "a+") as f:
                            f.write(
                                f"{x[0]:4s}  {files[4:9]:5s}  {x[3]:.6}  {x[4]:>13}  {x[5]:>13}  {x[6]:>13}\n"
                            )
                        print("\t " + x[0] + " " + files[4:9])
                    else:
                        with open("XYZ", "a+") as f:
                            f.write("----------------------------------------------------------\n")

    def transform():
        print("\n \t ============== Transforming XYZ coordinates to local ENU =============== \n")

        lat = input("\t Input latitude (DD): ")
        lon = input("\t Input longitude (DD): ")
        alt = input("\t Input altitude (m): ")

        if os.path.exists("XYZ"):
            with open("XYZ") as f_xyz:
                for file in f_xyz:
                    r = file.split()
                    if len(r) == 6:
                        X = float(r[3])
                        Y = float(r[4])
                        Z = float(r[5])
                        east, north, up = pymap3d.ecef2enu(
                            X, Y, Z, float(lat), float(lon), float(alt), deg=True
                        )
                        with open("ENU", "a+") as f:
                            f.write(
                                f"{r[0]:4s}  {r[1]:5s}  {r[2]:6s}  {east:.4f}  {north:.4f}  {up:.4f}\n"
                            )
                    else:
                        with open("ENU", "a+") as f:
                            f.write("----------------------------------------------------------\n")
        else:
            print("File 'XYZ' not found.")

    def getenu():
        print("\n \t ==================== Getting local ENU coordinates ===================== \n")

        sname = []

        if os.path.exists("ENU"):
            with open("ENU") as f_enu:
                for lines in f_enu:
                    x = lines.split()
                    if len(x[0]) == 4:
                        if len(sname) == 0:
                            sname.append(x[0])
                        elif len(sname) == 1:
                            del sname[0]
                            sname.append(x[0])

                        with open(sname[0], "a+") as f_sname:
                            f_sname.write(x[1] + "  " + x[2] + "," + x[3] + "," + x[4] + "," + x[5])
                            f_sname.write("\n")
                    else:
                        pass
        else:
            print("File 'ENU' not found.")

    def plotfiles():
        input("\t To create PLOT files, press Enter")

        print("\t Running...")

        dirName = "PLOTS"
        if not os.path.exists(dirName):
            os.mkdir(dirName)
            print("\t Directory", dirName, "created")
        else:
            print("\t Directory", dirName, "already exists")
            pass

        print("\n \t ======================= Creating PLOT files ============================")

        print("\n \t List of sites: ")

        for sites in glob.glob("????"):
            print("\t " + sites)
            with open("123", "a+") as f:
                f.write(sites + "\n")
            # Removed unused loop populating alldata

        print("\n \t DONE! ")
        time.sleep(3)

    getxyz()
    transform()
    getenu()
    plotfiles()


if __name__ == "__main__":
    start()
