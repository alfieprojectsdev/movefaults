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
if (@ARGV < 2 or @ARGV > 3 or lc($ARGV[0]) eq "-h") {
  die "\n  Start LUZON BPE process for a particular session\n".
      "\n  Usage: luzon_pcs.pl [-h] yyyy ssss [pcf]\n".
      "\n  yyyy : 4-digit (or 2-digit) year".
      "\n  ssss : 4-character session".
      "\n  pcf  : PCF name (default LUZON_DLY)".
      "\n  -h   : Display this help text\n\n" }

my $pcf = $ARGV[2] || "LUZON_DLY";

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
$$bpe{BPE_CAMPAIGN} = '${P}/LUZON';   # SINGLE quotes: Perl must not interpolate
$$bpe{YEAR}         = $ARGV[0];
$$bpe{SESSION}      = $ARGV[1];
$$bpe{SYSOUT}       = $pcf;
$$bpe{STATUS}       = "$pcf.RUN";
$$bpe{TASKID}       = "RS";

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
  die ("Error in LUZON BPE: $$bpe{PCF_FILE}.PCF (Session: $ARGV[1])\n");
}

# BPE process finished
# --------------------
print "LUZON BPE process finished on ".timstr(localtime(time))."\n\n";

__END__

