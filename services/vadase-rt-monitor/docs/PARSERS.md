# NMEA Parsers

The system includes a custom, high-performance NMEA 0183 parser optimized for Leica VADASE extensions. The source code is in `src/parsers/nmea_parser.py`.

## Supported Sentences

### 1. `$GNLVM` / `$GPLVM` (Velocity)
Contains instantaneous velocity components and variances.
- **Precision**: 4 decimal places ($0.0001 m/s$).
- **Fields returned**: `timestamp`, `vE`, `vN`, `vU` (m/s), `varE`, `varN`, `varU`, `covEN`, `covEU`, `covUN` (m²/s²), `cq` (3D quality, m/s), `n_sats`.

### 2. `$GNLDM` / `$GPLDM` (Displacement)
Contains integrated displacement from the start of the session.
- **Fields returned**: `timestamp`, `start_time` (start of integration), `dE`, `dN`, `dU` (m), `varE`…`covUN` (m²), `cq` (m), `n_sats`, `reset_indicator`, `epoch_completeness`, `overall_completeness`.

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

## Malformed sentences

A sentence with a valid checksum but fields that do not convert (too few
fields, a non-numeric value) makes `parse_lvm` / `parse_ldm` print the error
and return `None`; `IngestionCore` skips it. Only checksum failures raise.

Only the four sentence types above are parsed. Anything else on the stream,
including other NMEA sentences, is ignored by `IngestionCore.process_sentence`.

## Testing the Parser
The parser is tested in `tests/test_nmea_parser.py`, with fixtures in
`tests/fixtures/sample_lvm.nmea` and `sample_ldm.nmea`.
