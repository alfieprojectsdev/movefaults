> **HISTORICAL DOCUMENT (pre-implementation proposal).** This layout was a
> design sketch and does not match the current tree — e.g. there is no
> `src/database/` (persistence lives in `src/adapters/outputs/timescaledb.py`),
> and the hexagonal `src/ports` + `src/adapters` split happened instead.
> Use `ls -R src/` or the README for the real structure.

vadase-rt-monitor/
├── .gitignore
├── .env.example
├── README.md
├── LICENSE
- ├── requirements.txt          # Remove this (pip -> uv)
+ ├── pyproject.toml            # Add: Modern Python project config
+ ├── uv.lock                   # Add: UV's lockfile (auto-generated)
├── docker-compose.yml
├── Dockerfile
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── NMEA_SPEC.md           # Paste Leica LDM/LVM specs here
│   └── VALIDATION_GUIDE.md
│
├── src/
│   ├── __init__.py
│   ├── config.py               # Configuration management
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── nmea_parser.py      # LVM/LDM parsing functions
│   │   └── validators.py       # Checksum & quality checks
│   │
│   ├── stream/
│   │   ├── __init__.py
│   │   ├── handler.py          # VADASEStreamHandler class
│   │   └── connection.py       # TCP connection management
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py           # Database schema definitions
│   │   ├── writer.py           # DatabaseWriter class
│   │   └── queries.py          # Common SQL queries
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── event_detector.py   # Threshold-based detection logic
│   │   └── alerts.py           # Alert mechanisms (email, Telegram)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logging.py          # Custom logging setup
│       └── metrics.py          # Computation helpers (magnitude, etc.)
│
├── scripts/
│   ├── init_database.sql       # TimescaleDB schema setup
│   ├── continuous_aggregates.sql
│   ├── run_ingestor.py         # Main entry point
│   └── validate_parser.py      # Test against known events
│
├── tests/
│   ├── __init__.py
│   ├── test_parsers.py
│   ├── test_stream_handler.py
│   ├── test_event_detection.py
│   └── fixtures/
│       ├── sample_lvm.nmea     # Real NMEA samples for testing
│       └── sample_ldm.nmea
│
├── grafana/
│   ├── dashboards/
│   │   ├── real_time_monitoring.json
│   │   ├── event_analysis.json
│   │   └── data_quality.json
│   └── provisioning/
│       ├── datasources.yml
│       └── dashboards.yml
│
├── config/
│   ├── stations.yml            # Station metadata (ID, host, port, coords)
│   ├── thresholds.yml          # Detection thresholds per fault segment
│   └── logging.yml             # Logging configuration
│
└── notebooks/                  # Jupyter notebooks for analysis
    ├── event_validation.ipynb
    └── poster_reproduction.ipynb

