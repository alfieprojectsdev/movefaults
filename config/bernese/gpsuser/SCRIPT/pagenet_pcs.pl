#!/usr/bin/env perl

# ============================================================================
#
# Name    :  rnx2snx_pcs.pl
#
# Purpose :  Start PAGENET BPE process for a particular session
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
  die "\n  Start PAGENET BPE process for a particular session\n".
      "\n  Usage: pagenet_pcs.pl [-h] yyyy ssss [pcf]\n".
      "\n  yyyy : 4-digit (or 2-digit) year".
      "\n  ssss : 4-character session".
      "\n  pcf  : PCF name (default PAGENET; use PAGENET_DLY for daily 001-514)".
      "\n  -h   : Display this help text\n\n" }

my $pcf = $ARGV[2] || "PAGENET";

# Create startBPE object
# ----------------------
my $bpe = new startBPE();

# Redefine mandatory variables
# ----------------------------
$$bpe{PCF_FILE}     = $pcf;
$$bpe{CPU_FILE}     = "USER";
$$bpe{BPE_CAMPAIGN} = "PAGENET";
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
print "\nPAGENET BPE process started on ".timstr(localtime(time))."\n";

# The BPE runs
# ------------
$bpe->run();

# Check for error
# ---------------
if ($$bpe{ERROR_STATUS} ) {
  die ("Error in PAGENET BPE: $$bpe{PCF_FILE}.PCF (Session: $ARGV[1])\n");
}

# BPE process finished
# --------------------
print "PAGENET BPE process finished on ".timstr(localtime(time))."\n\n";

__END__

