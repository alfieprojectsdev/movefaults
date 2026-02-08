import logging
import os
from typing import Tuple, Optional
from pogf_geodetic_suite.qc.rinex_qc import RinexQC

logger = logging.getLogger(__name__)

def validate_rinex_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate RINEX file.
    Returns (is_valid, error_message)
    """
    if not os.path.exists(file_path):
        return False, "File not found"

    try:
        # Simple header check first
        with open(file_path, 'r', errors='ignore') as f:
            first_line = f.readline()
            if "RINEX VERSION / TYPE" not in first_line:
                 return False, "Invalid RINEX header: Missing VERSION/TYPE line"

        # Try full QC
        qc = RinexQC()
        try:
             qc.run_qc(file_path)
             return True, None
        except FileNotFoundError:
             # gfzrnx not installed
             logger.warning("gfzrnx binary not found, skipping deep QC")
             return True, "Skipped deep QC (gfzrnx missing)"
        except RuntimeError as e:
             logger.error(f"QC check failed: {e}")
             return False, str(e)

    except Exception as e:
        logger.error(f"Validation exception: {e}")
        return False, str(e)
