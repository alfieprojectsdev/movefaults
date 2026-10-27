#!/usr/bin/env perl

# ============================================================================
#
# Name    :  sessions_pcs.pl
#
# Purpose :  Run N consecutive sessions of one PCF in parallel, each in its
#            own campaign (BSW reprocessing mode). Called by
#            bernese_workflow.backends.LinuxBPEBackend.run_sessions.
#
# Derived :  from phref_year.pl / luzon_year.pl (gps3, 2026-08), which differ
#            from each other only in the PCF default, the campaign and the
#            REPR campaign prefix. Here those are arguments. Two settings
#            differ from those drivers, on purpose:
#              REPR_MODE_ON_SUCCESS "keep" (they use "remove"): the server
#                removes a campaign as soon as its session ends, before the
#                caller can bank the day. The caller deletes it after banking.
#              NEXTSESS "0", set explicitly. It is startBPE.pm's own default,
#                so this is not a change: it makes visible that the server
#                starts no new session after the first error and lets the
#                running ones finish (MENU/bpe.cpp, startSessions).
#
# ============================================================================
use strict;

use lib $ENV{BPE};
use startBPE;
use bpe_util;

if (@ARGV != 7 or lc($ARGV[0]) eq "-h") {
  die "\n  Run consecutive sessions in parallel, one campaign per session\n".
      "\n  Usage: sessions_pcs.pl yyyy ssss pcf nsess maxsess campaign reprprefix\n".
      "\n  yyyy       : 4-digit year".
      "\n  ssss       : first session (4 characters)".
      "\n  pcf        : PCF name".
      "\n  nsess      : number of consecutive sessions".
      "\n  maxsess    : at most this many in parallel".
      "\n  campaign   : base campaign under \${P} (e.g. PHREF)".
      "\n  reprprefix : per-session campaign prefix (e.g. PHR -> PHR251520)\n\n" }

my ($year, $sess, $pcf, $nsess, $maxsess, $camp, $prefix) = @ARGV;
die "nsess must be a positive integer\n"   unless $nsess   =~ /^[1-9][0-9]*$/;
die "maxsess must be a positive integer\n" unless $maxsess =~ /^[1-9][0-9]*$/;
die "campaign must be a plain name\n"      unless $camp    =~ /^[A-Za-z0-9_]+$/;
die "reprprefix must be a plain name\n"    unless $prefix  =~ /^[A-Za-z0-9_]+$/;

my $bpe = new startBPE();

$$bpe{PCF_FILE}     = $pcf;
$$bpe{CPU_FILE}     = "USER";
# ${P}-qualified, and the ${P} must reach Bernese LITERALLY: startBPE resolves
# it with RUNBPE::_expandEnv, and a bare name would be resolved relative to the
# current directory. The ${P} part is therefore single-quoted (Perl would
# otherwise interpolate it as a variable, which under `use strict` aborts),
# and only the campaign name is concatenated on.
$$bpe{BPE_CAMPAIGN} = '${P}/' . $camp;
$$bpe{YEAR}         = $year;
$$bpe{SESSION}      = $sess;
$$bpe{SYSOUT}       = $pcf;
$$bpe{STATUS}       = "$pcf.RUN";
$$bpe{TASKID}       = "RP";

# Parallel multi-session: SUPERBPE=1 with RADIO_P=1 is "simple parallel multi
# session run"; NUM_SESS consecutive sessions, at most MAXSESS at once.
$$bpe{SUPERBPE}     = "1";
$$bpe{RADIO_P}      = "1";
$$bpe{NUM_SESS}     = $nsess;
$$bpe{MAXSESS}      = $maxsess;
$$bpe{NEXTSESS}     = "0";

# Reprocessing mode: one campaign per session, ${P}/<prefix><yy><ssss>. Shared
# campaigns failed 4 of 5 sessions at CCRNXO on 2026-08-12 (each consumed the
# others' staged RINEX).
$$bpe{REPR_MODE}            = "1";
$$bpe{REPR_MODE_PATH}       = "\${P}";
$$bpe{REPR_MODE_CAMPAIGN}   = $prefix;
$$bpe{REPR_MODE_ON_SUCCESS} = "keep";
$$bpe{REPR_MODE_ON_ERROR}   = "keep";

$bpe->resetCPU();

print "\n$camp BPE process started on ".timstr(localtime(time))."\n";
$bpe->run();

if ($$bpe{ERROR_STATUS} ) {
  die ("Error in $camp BPE: $$bpe{PCF_FILE}.PCF (Sessions: $sess +$nsess)\n");
}
print "$camp BPE process finished on ".timstr(localtime(time))."\n\n";

__END__
