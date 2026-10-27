#!/usr/bin/env perl

# ============================================================================
#
# Name    :  rnx2snx_pcs.pl
#
# Purpose :  Start LUZON BPE process for a particular session
#
# Author  :  R. Dach
# Created :  07-Jun-2022
#
# Changes :  07-Jun-2022 RD: Created for version 5.4
#
# ============================================================================
use strict;

use lib $ENV{BPE};
use startBPE;
use bpe_util;

# Check arguments
# ---------------
if (@ARGV < 2 or @ARGV > 5 or lc($ARGV[0]) eq "-h") {
  die "\n  Start LUZON BPE process for a particular session\n".
      "\n  Usage: luzon_pcs.pl [-h] yyyy ssss [pcf]\n".
      "\n  yyyy : 4-digit (or 2-digit) year".
      "\n  ssss : 4-character session".
      "\n  pcf  : PCF name (default PHREF_DLY)".
      "\n  -h   : Display this help text\n\n" }

my $pcf = $ARGV[2] || "PHREF_DLY";

# Create startBPE object
# ----------------------
my $bpe = new startBPE();

# Redefine mandatory variables
# ----------------------------
$$bpe{PCF_FILE}     = $pcf;
$$bpe{CPU_FILE}     = "USER";
# ${P}-qualified, NOT a bare name. startBPE tests the campaign with
# `-d RUNBPE::_expandEnv('', BPE_CAMPAIGN)`, so a bare "LUZON" is resolved
# RELATIVE TO THE CURRENT DIRECTORY and only works when launched from $P.
# The stock rnx2snx_pcs.pl uses a bare "EXAMPLE" and is therefore silently
# CWD-dependent; running it from anywhere else fails with
# "The campaign directory ... does not exist" while the directory plainly does.
#
# SINGLE-quoted on purpose. In double quotes Perl interpolates ${P} as a Perl
# variable, which does not exist under `use strict` and aborts at compile time.
# Bernese's _expandEnv wants the LITERAL string ${P} and resolves it itself.
$$bpe{BPE_CAMPAIGN} = '${P}/PHREF';   # SINGLE quotes: Perl must not interpolate
$$bpe{YEAR}         = $ARGV[0];
$$bpe{SESSION}      = $ARGV[1];
$$bpe{SYSOUT}       = $pcf;
$$bpe{STATUS}       = "$pcf.RUN";
$$bpe{TASKID}       = "RP";
# --- PARALLEL MULTI-SESSION (SUPERBPE verification, 2026-08-12) ---
# SUPERBPE=1 is the documented "Run sessions in parallel" checkbox (DOCU52
# 22.9). RADIO_P=1 selects "Simple parallel multi session run", which the
# manual recommends over the legacy Super-BPE sub-mode. MAXSESS caps how many
# sessions overlap at once; NUM_SESS is how many are processed in total.
#
# PRECONDITION the manual states, and which this run exists to verify: with
# every session in ONE campaign, "all scripts and filenames (including all
# temporary files) must be fully sessions-independent". If our derived PCF
# violates that, results will differ from the sequential baseline.
$$bpe{SUPERBPE}     = "1";
$$bpe{RADIO_P}      = "1";
$$bpe{NUM_SESS}     = $ARGV[3] || "5";
$$bpe{MAXSESS}      = $ARGV[4] || "5";

# --- REPROCESSING MODE: one campaign per session -------------------------
# The 2026-08-12 test with all sessions sharing $P/LUZON failed 4 of 5 at
# CCRNXO with "No input files": the sessions consumed each other's staged
# RINEX. DOCU52 22.9 states the precondition -- with one shared campaign,
# "all scripts and filenames (including all temporary files) must be fully
# sessions-independent" -- and ours are not.
#
# REPR_MODE is the documented remedy: BSW builds a private campaign per
# session from ${U}/PAN/NEWCAMP.INP, named <CAMPAIGN ID> + yySSSS.
#
# ON_SUCCESS is 'keep' rather than the 'remove' default so a failed
# verification can still be autopsied. Switch to 'remove' for production or
# the campaign area will grow without bound.
$$bpe{REPR_MODE}            = "1";
$$bpe{REPR_MODE_PATH}       = "\${P}";
$$bpe{REPR_MODE_CAMPAIGN}   = "PHR";
$$bpe{REPR_MODE_ON_SUCCESS} = "remove";
$$bpe{REPR_MODE_ON_ERROR}   = "keep";



# Reset CPU file
# --------------
$bpe->resetCPU();

# Start BPE process
# -----------------
print "\nLUZON BPE process started on ".timstr(localtime(time))."\n";

# The BPE runs
# ------------
$bpe->run();

# Check for error
# ---------------
if ($$bpe{ERROR_STATUS} ) {
  die ("Error in PHREF BPE: $$bpe{PCF_FILE}.PCF (Session: $ARGV[1])\n");
}

# BPE process finished
# --------------------
print "LUZON BPE process finished on ".timstr(localtime(time))."\n\n";

__END__

