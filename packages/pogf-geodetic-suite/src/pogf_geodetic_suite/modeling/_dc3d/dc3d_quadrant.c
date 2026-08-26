/* dc3d_quadrant.c -- A.M. Bradley's cancellation-error fix for Okada's DC3D.
 *
 * ============================ LICENCE ============================
 * THIS FILE IS ECLIPSE PUBLIC LICENSE 1.0.  The rest of this repository is
 * MIT.  EPL is weak copyleft: an EPL file may live inside a larger work under
 * a different licence, but this file itself remains EPL and must be
 * identified as such.  That is why it is a separate file with its own header
 * rather than folded into dc3d_core.c.
 *
 *   Source:  Stanford CDFM, dc3dm v0.3, external/dc3omp.f
 *            subroutines MQ1 and MQ2
 *   Author:  A.M. Bradley (ambrad@cs.stanford.edu), Stanford University,
 *            November 2012
 *   Licence: Eclipse Public License 1.0
 *            https://www.opensource.org/licenses/eclipse-1.0
 *   See:     docs/external-sources/README.md
 *
 * Okada's DC3D itself (dc3d_core.c) is not EPL and is not affected by this.
 * Deleting this file leaves a working, unencumbered DC3D; see
 * `use_quadrant_fix` in dc3d.py.
 * =================================================================
 *
 * WHAT IT FIXES, IN BRADLEY'S OWN TERMS
 *   DC3D must compute x11 = 1/(R + xi) with R = sqrt(xi^2 + eta^2 + q^2).
 *   Along the ray (xi < 0, eta = 0, q = 0) that expression is singular, and
 *   Okada substitutes around the exact singularity.  But the numerical error
 *   must be measured RELATIVELY: cancellation in R + xi is severe whenever
 *
 *       sqrt(eta^2 + q^2) / R
 *
 *   is small -- not only when the numerator is zero.  So the error fills four
 *   cones extending from the corners of the rectangular dislocation into the
 *   negative half-spaces, and Okada's exact-singularity substitutions do not
 *   reach into them.
 *
 *   The repair is not a reformulation.  Symmetry means the solution need only
 *   ever be evaluated in the xi, eta > 0 quadrant; evaluate there and flip
 *   signs to recover the others.  Eighty lines, no change to the mathematics.
 *
 * WHY IT IS OPTIONAL HERE
 *   Whether our geometries land in those cones is an empirical question, and
 *   `test_dc3d.py` answers it rather than assuming.  If they do not, the
 *   unencumbered core is sufficient and this file can be dropped.  If they
 *   do, this is the version to use and its licence is the price.
 */

#include <math.h>

#define QDEG2RAD 1.7453292519943295e-2

/* Forward declaration of the unencumbered core. */
int dc3d(char space, double alpha, double x, double y, double z,
         double depth, double dip,
         double al1, double al2, double aw1, double aw2,
         double disl1, double disl2, double disl3,
         double *out);

/* dc3d_q -- DC3D evaluated in the xi, eta > 0 quadrant.
 *
 * Same signature and same return codes as dc3d().  The reflections are
 * Bradley's MQ1 (fold the observation point into the first quadrant, swapping
 * the fault half-lengths and flipping the corresponding slip component) and
 * MQ2 (reflect the twelve outputs back).
 */
int dc3d_q(char space, double alpha, double x, double y, double z,
           double depth, double dip,
           double al1, double al2, double aw1, double aw2,
           double disl1, double disl2, double disl3,
           double *out)
{
    /* ---- MQ1: flip signs so (x, y, z) is in the xi, eta > 0 quadrant ---- */
    double sd = sin(dip * QDEG2RAD);
    double cd = cos(dip * QDEG2RAD);
    double d = depth + z;
    double eta = y * cd + d * sd;

    int flip_xi = (x < 0.0);
    int flip_eta = (eta < 0.0);

    if (flip_xi) {
        x = -x;
        disl1 = -disl1;
        double tmp = al1; al1 = al2; al2 = tmp;
    }
    if (flip_eta) {
        y = -y;
        dip = -dip;
        disl2 = -disl2;
        double tmp = aw1; aw1 = aw2; aw2 = tmp;
    }

    int rc = dc3d(space, alpha, x, y, z, depth, dip,
                  al1, al2, aw1, aw2, disl1, disl2, disl3, out);

    /* ---- MQ2: reflect the solution back into the caller's quadrant ----
     * The index sets differ between the two reflections and both include
     * out[4] and out[6]; a component flipped by both reflections is flipped
     * twice, which is correct and easy to mistake for a duplicate. */
    if (flip_xi) {
        out[0] = -out[0];
        out[6] = -out[6];
        out[9] = -out[9];
        out[4] = -out[4];
        out[5] = -out[5];
    }
    if (flip_eta) {
        out[1] = -out[1];
        out[4] = -out[4];
        out[10] = -out[10];
        out[6] = -out[6];
        out[8] = -out[8];
    }
    return rc;
}
