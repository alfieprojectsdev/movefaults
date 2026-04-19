# NMEA Parsers

The system includes a custom, high-performance NMEA 0183 parser optimized for Leica VADASE extensions. The source code is in `src/parsers/nmea_parser.py`.

## Supported Sentences

### 1. `$GNLVM` / `$GPLVM` (Velocity)
Contains instantaneous velocity components and variances.
- **Precision**: 4 decimal places ($0.0001 m/s$).
- **Key Fields**: `vE`, `vN`, `vU`, `cq` (3D quality), `n_sats`.

### 2. `$GNLDM` / `$GPLDM` (Displacement)
Contains integrated displacement from the start of the session.
- **Key Fields**: `dE`, `dN`, `dU`, `epoch_completeness`, `overall_completeness`.

## Technical Implementation

### Checksum Validation
Every sentence is validated before parsing using the standard NMEA 0183 XOR checksum.
```python
def validate_nmea_checksum(sentence: str) -> bool:
    body, checksum_str = sentence.rsplit("*", 1)
    # ... XOR calculation ...
    return calculated == expected
```
If a checksum fails, the `NMEAChecksumError` is raised and caught by the `IngestionCore`, which logs the error and skips the corrupted line.

### Time & Date Handling
NMEA timestamps are typically UTC. The parser handles the standard `hhmmss.ss` format and combines it with a date field (`mmddyy`) to create a timezone-aware Python `datetime` object.

```python
# Example conversion
# Time: 113805.50 (11:38:05.500)
# Date: 030215 (Feb 3, 2015)
# Result: 2015-02-03 11:38:05.500+00:00
```

## Regular Expression Parsers
For older or generic VADASE streams, the system also supports:
- `$PTNL,VEL`: Proprietary Trimble-style velocity sentence.
- `$PTNL,POS`: Proprietary Trimble-style position/displacement sentence.

These are parsed using optimized regular expressions (`re.match`) for robustness against varying whitespace or field order.

## Testing the Parser
The parser is rigorously tested in `tests/test_parsers.py` using historical data strings from PHIVOLCS CORS stations.
