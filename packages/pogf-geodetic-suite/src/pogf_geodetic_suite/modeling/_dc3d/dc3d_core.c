/* dc3d_core.c -- Okada (1992) DC3D: displacement, strain and tilt at depth
 * due to a buried finite rectangular fault in an elastic half-space.
 *
 * PROVENANCE
 *   Algorithm and original Fortran: Y. Okada, "Internal deformation due to
 *   shear and tensile faults in a half-space", Bulletin of the Seismological
 *   Society of America, 82(2), 1018-1040, 1992.  Original DC3D.f coded by
 *   Y. Okada, September 1990, distributed by NIED.
 *
 *   This file is a line-by-line C transliteration of the DC3D, UA, UB, UC,
 *   DCCON0 and DCCON2 subroutines.  The mathematics is Okada's and unchanged;
 *   only the language is different.
 *
 *   The transliteration was made from the copy of Okada's Fortran carried in
 *   Stanford CDFM's dc3dm v0.3 as external/dc3omp.f.  That distribution is
 *   Eclipse Public License 1.0 and adds A.M. Bradley's cancellation-error fix
 *   and OpenMP directives.  NEITHER IS IN THIS FILE.  Bradley's fix is a
 *   separate contribution and lives in dc3d_quadrant.c, which carries its own
 *   licence header; the OpenMP THREADPRIVATE directives are unnecessary here
 *   because the COMMON blocks became explicit structs (see below).
 *
 *   Okada's DC3D is long-standing, freely distributed scientific source with
 *   no copyleft attached.  Keeping it in its own file means this half of the
 *   port carries no licence obligations beyond citing the paper.
 *
 * WHY C, AND WHY NOT f2py
 *   There is no gfortran on the target machines; there is cc.  The sibling
 *   module _disloc/ already established the pattern -- C source compiled to a
 *   shared library on first use and called through ctypes, no build step and
 *   no toolchain beyond a C compiler.  This follows it.
 *
 * DIFFERENCES FROM THE FORTRAN, ALL DELIBERATE
 *   1. The COMMON blocks /C0/ and /C2/ are structs passed by pointer.  The
 *      Fortran needed !$OMP THREADPRIVATE to be usable from more than one
 *      thread; explicit state is thread-safe by construction, which matters
 *      because the whole point of this port is running inversions across the
 *      R740's 24 cores.
 *   2. Arrays are 0-based.  Every Fortran index below is written as
 *      (fortran - 1); the loop strides and the special-cased last block are
 *      the two places where that is easy to get wrong, and both are commented.
 *   3. The Fortran writes a warning to unit 6 for positive Z.  Here it is
 *      reported through the return code instead -- a printf from inside a
 *      library called in a 100,000-sample inversion is not a diagnostic, it
 *      is a denial of service.
 *
 * OUTPUT ORDER (u[12], following the Fortran's U array exactly)
 *   0,1,2   ux,  uy,  uz
 *   3,4,5   uxx, uyx, uzx
 *   6,7,8   uxy, uyy, uzy
 *   9,10,11 uxz, uyz, uzz
 */

#include <math.h>
#include <string.h>

#define PI2 6.283185307179586
#define EPS 1.0e-6
#define DEG2RAD 1.7453292519943295e-2

/* Medium and dip constants -- Fortran COMMON /C0/. */
typedef struct {
    double alp1, alp2, alp3, alp4, alp5;
    double sd, cd, sdsd, cdcd, sdcd, s2d, c2d;
} dc_c0;

/* Station geometry constants -- Fortran COMMON /C2/. */
typedef struct {
    double xi2, et2, q2, r, r2, r3, r5, y, d, tt, alx, ale;
    double x11, y11, x32, y32, ey, ez, fy, fz, gy, gz, hy, hz;
} dc_c2;

/* DCCON0: medium constants and fault-dip constants.
 * CAUTION preserved from the original: if cos(dip) is small it is set to
 * zero and sin(dip) snapped to +/-1.  Removing that "cleanup" reintroduces
 * a singularity at vertical dip, which is the commonest fault geometry we
 * model. */
static void dccon0(double alpha, double dip, dc_c0 *c0)
{
    c0->alp1 = (1.0 - alpha) / 2.0;
    c0->alp2 = alpha / 2.0;
    c0->alp3 = (1.0 - alpha) / alpha;
    c0->alp4 = 1.0 - alpha;
    c0->alp5 = alpha;

    double p18 = PI2 / 360.0;
    c0->sd = sin(dip * p18);
    c0->cd = cos(dip * p18);
    if (fabs(c0->cd) < EPS) {
        c0->cd = 0.0;
        if (c0->sd > 0.0) c0->sd = 1.0;
        if (c0->sd < 0.0) c0->sd = -1.0;
    }
    c0->sdsd = c0->sd * c0->sd;
    c0->cdcd = c0->cd * c0->cd;
    c0->sdcd = c0->sd * c0->cd;
    c0->s2d = 2.0 * c0->sdcd;
    c0->c2d = c0->cdcd - c0->sdsd;
}

/* DCCON2: station geometry constants for a finite source.
 *
 * xi, et and q are passed by pointer because the Fortran modifies them in
 * place -- values below EPS are snapped to exactly zero, and the callers
 * (UA/UB/UC) must see the snapped values.  Passing by value here silently
 * changes results near the fault edges.
 *
 * Returns 0 if r == 0 (the singular case the caller must handle), else 1. */
static int dccon2(double *xi, double *et, double *q, double sd, double cd,
                  int jxi, int jet, dc_c2 *c2)
{
    if (fabs(*xi) < EPS) *xi = 0.0;
    if (fabs(*et) < EPS) *et = 0.0;
    if (fabs(*q) < EPS) *q = 0.0;

    c2->xi2 = *xi * *xi;
    c2->et2 = *et * *et;
    c2->q2 = *q * *q;
    c2->r2 = c2->xi2 + c2->et2 + c2->q2;
    c2->r = sqrt(c2->r2);
    if (c2->r == 0.0) return 0;

    c2->r3 = c2->r * c2->r2;
    c2->r5 = c2->r3 * c2->r2;
    c2->y = *et * cd + *q * sd;
    c2->d = *et * sd - *q * cd;

    c2->tt = (*q == 0.0) ? 0.0 : atan(*xi * *et / (*q * c2->r));

    /* The log/reciprocal terms are singular on the rays the fault edges
     * define.  Okada's substitutions below are the "points iii and iv" of
     * the 1992 Discussion, not an implementation convenience. */
    double rxi = c2->r + *xi;
    if (jxi == 1 && *q == 0.0 && *et == 0.0) {
        c2->alx = 0.0; c2->x11 = 0.0; c2->x32 = 0.0;
    } else if (*xi < 0.0 && *q == 0.0 && *et == 0.0) {
        c2->alx = -log(c2->r - *xi); c2->x11 = 0.0; c2->x32 = 0.0;
    } else {
        c2->alx = log(rxi);
        c2->x11 = 1.0 / (c2->r * rxi);
        c2->x32 = (2.0 * c2->r + *xi) * c2->x11 * c2->x11 / c2->r;
    }

    double ret = c2->r + *et;
    if (jet == 1 && *q == 0.0 && *xi == 0.0) {
        c2->ale = 0.0; c2->y11 = 0.0; c2->y32 = 0.0;
    } else if (*et < 0.0 && *q == 0.0 && *xi == 0.0) {
        c2->ale = -log(c2->r - *et); c2->y11 = 0.0; c2->y32 = 0.0;
    } else {
        c2->ale = log(ret);
        c2->y11 = 1.0 / (c2->r * ret);
        c2->y32 = (2.0 * c2->r + *et) * c2->y11 * c2->y11 / c2->r;
    }

    c2->ey = sd / c2->r - c2->y * *q / c2->r3;
    c2->ez = cd / c2->r + c2->d * *q / c2->r3;
    c2->fy = c2->d / c2->r3 + c2->xi2 * c2->y32 * sd;
    c2->fz = c2->y / c2->r3 + c2->xi2 * c2->y32 * cd;
    c2->gy = 2.0 * c2->x11 * sd - c2->y * *q * c2->x32;
    c2->gz = 2.0 * c2->x11 * cd + c2->d * *q * c2->x32;
    c2->hy = c2->d * *q * c2->x32 + *xi * *q * c2->y32 * sd;
    c2->hz = c2->y * *q * c2->x32 + *xi * *q * c2->y32 * cd;
    return 1;
}

/* UA: part A -- the full-space term. */
static void ua(double xi, double et, double q,
               double disl1, double disl2, double disl3,
               const dc_c0 *c0, const dc_c2 *c2, double *u)
{
    double du[12];
    for (int i = 0; i < 12; i++) u[i] = 0.0;

    double xy = xi * c2->y11;
    double qx = q * c2->x11;
    double qy = q * c2->y11;

    if (disl1 != 0.0) {              /* strike-slip */
        du[0] = c2->tt / 2.0 + c0->alp2 * xi * qy;
        du[1] = c0->alp2 * q / c2->r;
        du[2] = c0->alp1 * c2->ale - c0->alp2 * q * qy;
        du[3] = -c0->alp1 * qy - c0->alp2 * c2->xi2 * q * c2->y32;
        du[4] = -c0->alp2 * xi * q / c2->r3;
        du[5] = c0->alp1 * xy + c0->alp2 * xi * c2->q2 * c2->y32;
        du[6] = c0->alp1 * xy * c0->sd + c0->alp2 * xi * c2->fy + c2->d / 2.0 * c2->x11;
        du[7] = c0->alp2 * c2->ey;
        du[8] = c0->alp1 * (c0->cd / c2->r + qy * c0->sd) - c0->alp2 * q * c2->fy;
        du[9] = c0->alp1 * xy * c0->cd + c0->alp2 * xi * c2->fz + c2->y / 2.0 * c2->x11;
        du[10] = c0->alp2 * c2->ez;
        du[11] = -c0->alp1 * (c0->sd / c2->r - qy * c0->cd) - c0->alp2 * q * c2->fz;
        for (int i = 0; i < 12; i++) u[i] += disl1 / PI2 * du[i];
    }
    if (disl2 != 0.0) {              /* dip-slip */
        du[0] = c0->alp2 * q / c2->r;
        du[1] = c2->tt / 2.0 + c0->alp2 * et * qx;
        du[2] = c0->alp1 * c2->alx - c0->alp2 * q * qx;
        du[3] = -c0->alp2 * xi * q / c2->r3;
        du[4] = -qy / 2.0 - c0->alp2 * et * q / c2->r3;
        du[5] = c0->alp1 / c2->r + c0->alp2 * c2->q2 / c2->r3;
        du[6] = c0->alp2 * c2->ey;
        du[7] = c0->alp1 * c2->d * c2->x11 + xy / 2.0 * c0->sd + c0->alp2 * et * c2->gy;
        du[8] = c0->alp1 * c2->y * c2->x11 - c0->alp2 * q * c2->gy;
        du[9] = c0->alp2 * c2->ez;
        du[10] = c0->alp1 * c2->y * c2->x11 + xy / 2.0 * c0->cd + c0->alp2 * et * c2->gz;
        du[11] = -c0->alp1 * c2->d * c2->x11 - c0->alp2 * q * c2->gz;
        for (int i = 0; i < 12; i++) u[i] += disl2 / PI2 * du[i];
    }
    if (disl3 != 0.0) {              /* tensile */
        du[0] = -c0->alp1 * c2->ale - c0->alp2 * q * qy;
        du[1] = -c0->alp1 * c2->alx - c0->alp2 * q * qx;
        du[2] = c2->tt / 2.0 - c0->alp2 * (et * qx + xi * qy);
        du[3] = -c0->alp1 * xy + c0->alp2 * xi * c2->q2 * c2->y32;
        du[4] = -c0->alp1 / c2->r + c0->alp2 * c2->q2 / c2->r3;
        du[5] = -c0->alp1 * qy - c0->alp2 * q * c2->q2 * c2->y32;
        du[6] = -c0->alp1 * (c0->cd / c2->r + qy * c0->sd) - c0->alp2 * q * c2->fy;
        du[7] = -c0->alp1 * c2->y * c2->x11 - c0->alp2 * q * c2->gy;
        du[8] = c0->alp1 * (c2->d * c2->x11 + xy * c0->sd) + c0->alp2 * q * c2->hy;
        du[9] = c0->alp1 * (c0->sd / c2->r - qy * c0->cd) - c0->alp2 * q * c2->fz;
        du[10] = c0->alp1 * c2->d * c2->x11 - c0->alp2 * q * c2->gz;
        du[11] = c0->alp1 * (c2->y * c2->x11 + xy * c0->cd) + c0->alp2 * q * c2->hz;
        for (int i = 0; i < 12; i++) u[i] += disl3 / PI2 * du[i];
    }
}

/* UB: part B -- the image-source correction term. */
static void ub(double xi, double et, double q,
               double disl1, double disl2, double disl3,
               const dc_c0 *c0, const dc_c2 *c2, double *u)
{
    double du[12];
    double ai1, ai2, ai3, ai4, aj1, aj2, aj3, aj4, aj5, aj6;
    double ak1, ak2, ak3, ak4;

    double rd = c2->r + c2->d;
    double d11 = 1.0 / (c2->r * rd);
    aj2 = xi * c2->y / rd * d11;
    aj5 = -(c2->d + c2->y * c2->y / rd) * d11;

    /* The cd == 0 branch is the vertical-dip limit, taken analytically
     * rather than by letting 1/cdcd blow up. */
    if (c0->cd != 0.0) {
        if (xi == 0.0) {
            ai4 = 0.0;
        } else {
            double x = sqrt(c2->xi2 + c2->q2);
            ai4 = 1.0 / c0->cdcd
                * (xi / rd * c0->sdcd
                   + 2.0 * atan((et * (x + q * c0->cd) + x * (c2->r + x) * c0->sd)
                                / (xi * (c2->r + x) * c0->cd)));
        }
        ai3 = (c2->y * c0->cd / rd - c2->ale + c0->sd * log(rd)) / c0->cdcd;
        ak1 = xi * (d11 - c2->y11 * c0->sd) / c0->cd;
        ak3 = (q * c2->y11 - c2->y * d11) / c0->cd;
        aj3 = (ak1 - aj2 * c0->sd) / c0->cd;
        aj6 = (ak3 - aj5 * c0->sd) / c0->cd;
    } else {
        double rd2 = rd * rd;
        ai3 = (et / rd + c2->y * q / rd2 - c2->ale) / 2.0;
        ai4 = xi * c2->y / rd2 / 2.0;
        ak1 = xi * q / rd * d11;
        ak3 = c0->sd / rd * (c2->xi2 * d11 - 1.0);
        aj3 = -xi / rd2 * (c2->q2 * d11 - 1.0 / 2.0);
        aj6 = -c2->y / rd2 * (c2->xi2 * d11 - 1.0 / 2.0);
    }

    double xy = xi * c2->y11;
    ai1 = -xi / rd * c0->cd - ai4 * c0->sd;
    ai2 = log(rd) + ai3 * c0->sd;
    ak2 = 1.0 / c2->r + ak3 * c0->sd;
    ak4 = xy * c0->cd - ak1 * c0->sd;
    aj1 = aj5 * c0->cd - aj6 * c0->sd;
    aj4 = -xy - aj2 * c0->cd + aj3 * c0->sd;

    for (int i = 0; i < 12; i++) u[i] = 0.0;
    double qx = q * c2->x11;
    double qy = q * c2->y11;

    if (disl1 != 0.0) {
        du[0] = -xi * qy - c2->tt - c0->alp3 * ai1 * c0->sd;
        du[1] = -q / c2->r + c0->alp3 * c2->y / rd * c0->sd;
        du[2] = q * qy - c0->alp3 * ai2 * c0->sd;
        du[3] = c2->xi2 * q * c2->y32 - c0->alp3 * aj1 * c0->sd;
        du[4] = xi * q / c2->r3 - c0->alp3 * aj2 * c0->sd;
        du[5] = -xi * c2->q2 * c2->y32 - c0->alp3 * aj3 * c0->sd;
        du[6] = -xi * c2->fy - c2->d * c2->x11 + c0->alp3 * (xy + aj4) * c0->sd;
        du[7] = -c2->ey + c0->alp3 * (1.0 / c2->r + aj5) * c0->sd;
        du[8] = q * c2->fy - c0->alp3 * (qy - aj6) * c0->sd;
        du[9] = -xi * c2->fz - c2->y * c2->x11 + c0->alp3 * ak1 * c0->sd;
        du[10] = -c2->ez + c0->alp3 * c2->y * d11 * c0->sd;
        du[11] = q * c2->fz + c0->alp3 * ak2 * c0->sd;
        for (int i = 0; i < 12; i++) u[i] += disl1 / PI2 * du[i];
    }
    if (disl2 != 0.0) {
        du[0] = -q / c2->r + c0->alp3 * ai3 * c0->sdcd;
        du[1] = -et * qx - c2->tt - c0->alp3 * xi / rd * c0->sdcd;
        du[2] = q * qx + c0->alp3 * ai4 * c0->sdcd;
        du[3] = xi * q / c2->r3 + c0->alp3 * aj4 * c0->sdcd;
        du[4] = et * q / c2->r3 + qy + c0->alp3 * aj5 * c0->sdcd;
        du[5] = -c2->q2 / c2->r3 + c0->alp3 * aj6 * c0->sdcd;
        du[6] = -c2->ey + c0->alp3 * aj1 * c0->sdcd;
        du[7] = -et * c2->gy - xy * c0->sd + c0->alp3 * aj2 * c0->sdcd;
        du[8] = q * c2->gy + c0->alp3 * aj3 * c0->sdcd;
        du[9] = -c2->ez - c0->alp3 * ak3 * c0->sdcd;
        du[10] = -et * c2->gz - xy * c0->cd - c0->alp3 * xi * d11 * c0->sdcd;
        du[11] = q * c2->gz - c0->alp3 * ak4 * c0->sdcd;
        for (int i = 0; i < 12; i++) u[i] += disl2 / PI2 * du[i];
    }
    if (disl3 != 0.0) {
        du[0] = q * qy - c0->alp3 * ai3 * c0->sdsd;
        du[1] = q * qx + c0->alp3 * xi / rd * c0->sdsd;
        du[2] = et * qx + xi * qy - c2->tt - c0->alp3 * ai4 * c0->sdsd;
        du[3] = -xi * c2->q2 * c2->y32 - c0->alp3 * aj4 * c0->sdsd;
        du[4] = -c2->q2 / c2->r3 - c0->alp3 * aj5 * c0->sdsd;
        du[5] = q * c2->q2 * c2->y32 - c0->alp3 * aj6 * c0->sdsd;
        du[6] = q * c2->fy - c0->alp3 * aj1 * c0->sdsd;
        du[7] = q * c2->gy - c0->alp3 * aj2 * c0->sdsd;
        du[8] = -q * c2->hy - c0->alp3 * aj3 * c0->sdsd;
        du[9] = q * c2->fz + c0->alp3 * ak3 * c0->sdsd;
        du[10] = q * c2->gz + c0->alp3 * xi * d11 * c0->sdsd;
        du[11] = -q * c2->hz + c0->alp3 * ak4 * c0->sdsd;
        for (int i = 0; i < 12; i++) u[i] += disl3 / PI2 * du[i];
    }
}

/* UC: part C -- the depth-dependent image term. */
static void uc(double xi, double et, double q, double z,
               double disl1, double disl2, double disl3,
               const dc_c0 *c0, const dc_c2 *c2, double *u)
{
    double du[12];
    double c = c2->d + z;
    double x53 = (8.0 * c2->r2 + 9.0 * c2->r * xi + 3.0 * c2->xi2)
                 * c2->x11 * c2->x11 * c2->x11 / c2->r2;
    double y53 = (8.0 * c2->r2 + 9.0 * c2->r * et + 3.0 * c2->et2)
                 * c2->y11 * c2->y11 * c2->y11 / c2->r2;
    double h = q * c0->cd - z;
    double z32 = c0->sd / c2->r3 - h * c2->y32;
    double z53 = 3.0 * c0->sd / c2->r5 - h * y53;
    double y0 = c2->y11 - c2->xi2 * c2->y32;
    double z0 = z32 - c2->xi2 * z53;
    double ppy = c0->cd / c2->r3 + q * c2->y32 * c0->sd;
    double ppz = c0->sd / c2->r3 - q * c2->y32 * c0->cd;
    double qq = z * c2->y32 + z32 + z0;
    double qqy = 3.0 * c * c2->d / c2->r5 - qq * c0->sd;
    double qqz = 3.0 * c * c2->y / c2->r5 - qq * c0->cd + q * c2->y32;
    double xy = xi * c2->y11;
    double qy = q * c2->y11;
    double qr = 3.0 * q / c2->r5;
    double cqx = c * q * x53;
    double cdr = (c + c2->d) / c2->r3;
    double yy0 = c2->y / c2->r3 - y0 * c0->cd;
    (void)cqx;  /* present in the Fortran's DATA list, unused in these branches */

    for (int i = 0; i < 12; i++) u[i] = 0.0;

    if (disl1 != 0.0) {
        du[0] = c0->alp4 * xy * c0->cd - c0->alp5 * xi * q * z32;
        du[1] = c0->alp4 * (c0->cd / c2->r + 2.0 * qy * c0->sd) - c0->alp5 * c * q / c2->r3;
        du[2] = c0->alp4 * qy * c0->cd
                - c0->alp5 * (c * et / c2->r3 - z * c2->y11 + c2->xi2 * z32);
        du[3] = c0->alp4 * y0 * c0->cd - c0->alp5 * q * z0;
        du[4] = -c0->alp4 * xi * (c0->cd / c2->r3 + 2.0 * q * c2->y32 * c0->sd)
                + c0->alp5 * c * xi * qr;
        du[5] = -c0->alp4 * xi * q * c2->y32 * c0->cd
                + c0->alp5 * xi * (3.0 * c * et / c2->r5 - qq);
        du[6] = -c0->alp4 * xi * ppy * c0->cd - c0->alp5 * xi * qqy;
        du[7] = c0->alp4 * 2.0 * (c2->d / c2->r3 - y0 * c0->sd) * c0->sd
                - c2->y / c2->r3 * c0->cd
                - c0->alp5 * (cdr * c0->sd - et / c2->r3 - c * c2->y * qr);
        du[8] = -c0->alp4 * q / c2->r3 + yy0 * c0->sd
                + c0->alp5 * (cdr * c0->cd + c * c2->d * qr - (y0 * c0->cd + q * z0) * c0->sd);
        du[9] = c0->alp4 * xi * ppz * c0->cd - c0->alp5 * xi * qqz;
        du[10] = c0->alp4 * 2.0 * (c2->y / c2->r3 - y0 * c0->cd) * c0->sd
                 + c2->d / c2->r3 * c0->cd - c0->alp5 * (cdr * c0->cd + c * c2->d * qr);
        du[11] = yy0 * c0->cd
                 - c0->alp5 * (cdr * c0->sd - c * c2->y * qr - y0 * c0->sdsd + q * z0 * c0->cd);
        for (int i = 0; i < 12; i++) u[i] += disl1 / PI2 * du[i];
    }
    if (disl2 != 0.0) {
        du[0] = c0->alp4 * c0->cd / c2->r - qy * c0->sd - c0->alp5 * c * q / c2->r3;
        du[1] = c0->alp4 * c2->y * c2->x11 - c0->alp5 * c * et * q * c2->x32;
        du[2] = -c2->d * c2->x11 - xy * c0->sd - c0->alp5 * c * (c2->x11 - c2->q2 * c2->x32);
        du[3] = -c0->alp4 * xi / c2->r3 * c0->cd + c0->alp5 * c * xi * qr
                + xi * q * c2->y32 * c0->sd;
        du[4] = -c0->alp4 * c2->y / c2->r3 + c0->alp5 * c * et * qr;
        du[5] = c2->d / c2->r3 - y0 * c0->sd
                + c0->alp5 * c / c2->r3 * (1.0 - 3.0 * c2->q2 / c2->r2);
        du[6] = -c0->alp4 * et / c2->r3 + y0 * c0->sdsd
                - c0->alp5 * (cdr * c0->sd - c * c2->y * qr);
        du[7] = c0->alp4 * (c2->x11 - c2->y * c2->y * c2->x32)
                - c0->alp5 * c * ((c2->d + 2.0 * q * c0->cd) * c2->x32 - c2->y * et * q * x53);
        du[8] = xi * ppy * c0->sd + c2->y * c2->d * c2->x32
                + c0->alp5 * c * ((c2->y + 2.0 * q * c0->sd) * c2->x32 - c2->y * c2->q2 * x53);
        du[9] = -q / c2->r3 + y0 * c0->sdcd - c0->alp5 * (cdr * c0->cd + c * c2->d * qr);
        du[10] = c0->alp4 * c2->y * c2->d * c2->x32
                 - c0->alp5 * c * ((c2->y - 2.0 * q * c0->sd) * c2->x32 + c2->d * et * q * x53);
        du[11] = -xi * ppz * c0->sd + c2->x11 - c2->d * c2->d * c2->x32
                 - c0->alp5 * c * ((c2->d - 2.0 * q * c0->cd) * c2->x32 - c2->d * c2->q2 * x53);
        for (int i = 0; i < 12; i++) u[i] += disl2 / PI2 * du[i];
    }
    if (disl3 != 0.0) {
        du[0] = -c0->alp4 * (c0->sd / c2->r + qy * c0->cd)
                - c0->alp5 * (z * c2->y11 - c2->q2 * z32);
        du[1] = c0->alp4 * 2.0 * xy * c0->sd + c2->d * c2->x11
                - c0->alp5 * c * (c2->x11 - c2->q2 * c2->x32);
        du[2] = c0->alp4 * (c2->y * c2->x11 + xy * c0->cd)
                + c0->alp5 * q * (c * et * c2->x32 + xi * z32);
        du[3] = c0->alp4 * xi / c2->r3 * c0->sd + xi * q * c2->y32 * c0->cd
                + c0->alp5 * xi * (3.0 * c * et / c2->r5 - 2.0 * z32 - z0);
        du[4] = c0->alp4 * 2.0 * y0 * c0->sd - c2->d / c2->r3
                + c0->alp5 * c / c2->r3 * (1.0 - 3.0 * c2->q2 / c2->r2);
        du[5] = -c0->alp4 * yy0 - c0->alp5 * (c * et * qr - q * z0);
        du[6] = c0->alp4 * (q / c2->r3 + y0 * c0->sdcd)
                + c0->alp5 * (z / c2->r3 * c0->cd + c * c2->d * qr - q * z0 * c0->sd);
        du[7] = -c0->alp4 * 2.0 * xi * ppy * c0->sd - c2->y * c2->d * c2->x32
                + c0->alp5 * c * ((c2->y + 2.0 * q * c0->sd) * c2->x32 - c2->y * c2->q2 * x53);
        du[8] = -c0->alp4 * (xi * ppy * c0->cd - c2->x11 + c2->y * c2->y * c2->x32)
                + c0->alp5 * (c * ((c2->d + 2.0 * q * c0->cd) * c2->x32 - c2->y * et * q * x53)
                              + xi * qqy);
        du[9] = -et / c2->r3 + y0 * c0->cdcd
                - c0->alp5 * (z / c2->r3 * c0->sd - c * c2->y * qr - y0 * c0->sdsd
                              + q * z0 * c0->cd);
        du[10] = c0->alp4 * 2.0 * xi * ppz * c0->sd - c2->x11 + c2->d * c2->d * c2->x32
                 - c0->alp5 * c * ((c2->d - 2.0 * q * c0->cd) * c2->x32 - c2->d * c2->q2 * x53);
        du[11] = c0->alp4 * (xi * ppz * c0->cd + c2->y * c2->d * c2->x32)
                 + c0->alp5 * (c * ((c2->y - 2.0 * q * c0->sd) * c2->x32 + c2->d * et * q * x53)
                               + xi * qqz);
        for (int i = 0; i < 12; i++) u[i] += disl3 / PI2 * du[i];
    }
}

/* DC3D -- displacement and strain at depth from a finite rectangular fault.
 *
 * space: 'H'/'h' for a half-space (the usual case), anything else for a
 *        whole space, which skips the image-source contribution.
 *
 * Returns 0 on success, 1 if the observation point is singular (r == 0,
 * outputs zeroed), 2 if z > 0 which is outside the model's domain.
 */
int dc3d(char space, double alpha, double x, double y, double z,
         double depth, double dip,
         double al1, double al2, double aw1, double aw2,
         double disl1, double disl2, double disl3,
         double *out)
{
    dc_c0 c0;
    dc_c2 c2;
    double u[12], du[12], dua[12], dub[12], duc[12];

    for (int i = 0; i < 12; i++) out[i] = 0.0;
    /* The Fortran writes a warning to unit 6 and continues.  Refusing is
     * better: a positive z is above the free surface, where the half-space
     * solution is not defined, and a printf per call inside a 100,000-sample
     * inversion is worse than useless. */
    if (z > 0.0) return 2;

    for (int i = 0; i < 12; i++) { u[i] = 0.0; dua[i] = 0.0; dub[i] = 0.0; duc[i] = 0.0; }

    dccon0(alpha, dip, &c0);

    /* ---- real-source contribution ---- */
    double d = depth + z;
    double p = y * c0.cd + d * c0.sd;
    double q = y * c0.sd - d * c0.cd;
    int jxi = ((x + al1) * (x - al2) <= 0.0) ? 1 : 0;
    int jet = ((p + aw1) * (p - aw2) <= 0.0) ? 1 : 0;

    for (int k = 0; k < 2; k++) {            /* Fortran K=1,2 */
        double et = (k == 0) ? p + aw1 : p - aw2;
        for (int j = 0; j < 2; j++) {        /* Fortran J=1,2 */
            double xi = (j == 0) ? x + al1 : x - al2;
            double qq = q, ee = et, xx = xi;
            if (!dccon2(&xx, &ee, &qq, c0.sd, c0.cd, jxi, jet, &c2)) return 1;
            ua(xx, ee, qq, disl1, disl2, disl3, &c0, &c2, dua);

            /* Fortran DO 220 I=1,10,3 -> i = 0,3,6,9 here.  The final block
             * (Fortran I=10, here i=9) is negated again; that special case is
             * easy to lose in translation and changes only the tilt terms. */
            for (int i = 0; i < 12; i += 3) {
                du[i] = -dua[i];
                du[i + 1] = -dua[i + 1] * c0.cd + dua[i + 2] * c0.sd;
                du[i + 2] = -dua[i + 1] * c0.sd - dua[i + 2] * c0.cd;
                if (i == 9) {
                    du[i] = -du[i];
                    du[i + 1] = -du[i + 1];
                    du[i + 2] = -du[i + 2];
                }
            }
            /* Fortran IF(J+K.NE.3): with 1-based J,K that is the two
             * off-diagonal corners.  0-based, J+K==3 becomes j+k==1. */
            for (int i = 0; i < 12; i++)
                u[i] += (j + k == 1) ? -du[i] : du[i];
        }
    }

    /* ---- image-source contribution (half-space only) ---- */
    if (space == 'H' || space == 'h') {
        double zz = z;
        d = depth - z;
        p = y * c0.cd + d * c0.sd;
        q = y * c0.sd - d * c0.cd;
        jet = ((p + aw1) * (p - aw2) <= 0.0) ? 1 : 0;

        for (int k = 0; k < 2; k++) {
            double et = (k == 0) ? p + aw1 : p - aw2;
            for (int j = 0; j < 2; j++) {
                double xi = (j == 0) ? x + al1 : x - al2;
                double qq = q, ee = et, xx = xi;
                dccon2(&xx, &ee, &qq, c0.sd, c0.cd, jxi, jet, &c2);
                ua(xx, ee, qq, disl1, disl2, disl3, &c0, &c2, dua);
                ub(xx, ee, qq, disl1, disl2, disl3, &c0, &c2, dub);
                uc(xx, ee, qq, zz, disl1, disl2, disl3, &c0, &c2, duc);

                for (int i = 0; i < 12; i += 3) {
                    du[i] = dua[i] + dub[i] + z * duc[i];
                    du[i + 1] = (dua[i + 1] + dub[i + 1] + z * duc[i + 1]) * c0.cd
                                - (dua[i + 2] + dub[i + 2] + z * duc[i + 2]) * c0.sd;
                    du[i + 2] = (dua[i + 1] + dub[i + 1] - z * duc[i + 1]) * c0.sd
                                + (dua[i + 2] + dub[i + 2] - z * duc[i + 2]) * c0.cd;
                    if (i == 9) {
                        du[9] += duc[0];
                        du[10] += duc[1] * c0.cd - duc[2] * c0.sd;
                        du[11] += -duc[1] * c0.sd - duc[2] * c0.cd;
                    }
                }
                for (int i = 0; i < 12; i++)
                    u[i] += (j + k == 1) ? -du[i] : du[i];
            }
        }
    }

    memcpy(out, u, sizeof(u));
    return 0;
}
