# GNSS Data Processing Automation Roadmap
## MOVE Faults Project - PHIVOLCS

> **Context**: This document outlines automation opportunities for the existing Bernese GNSS 5.2 workflow, preserving the core processing engine while modernizing data ingestion, quality control, and metadata management.

---

## **1. Smart Data Ingestion System**

### **1.1 USB Thumbdrive Hot-Drop Monitor**

**Current Pain Point:**
- Manual file transfers from USB drives
- Manual organization into site-specific folders
- No validation until conversion attempt
- Risk of misplaced/duplicate files

**Proposed Solution:**

```
[USB Drive Plugged In]
    ↓
[inotify/watchdog detects new mount]
    ↓
[Python daemon scans for GNSS file patterns]
    ↓
[Identifies receiver type from file structure]
    ↓
[Extracts metadata: date, site, session]
    ↓
[Copies to staging area with checksum validation]
    ↓
[Moves to DATAPOOL/{SITE}/ with auto-organization]
    ↓
[Logs transaction to database]
    ↓
[Ejects drive safely + notifies user]
```

**Technical Stack:**
- **Linux**: `udev` rules + `inotify` or `pyudev`
- **Windows**: `watchdog` library + WMI events
- **Parsing**: Regex patterns for Trimble/Leica naming conventions
- **Validation**: MD5/SHA256 checksums, file size sanity checks
- **Notification**: Desktop notification (`plyer`) + optional Telegram/Slack

**Features:**
- Detects file type (Trimble T01/T02, Leica MDB) automatically
- Extracts Julian Day, site code, session from filename
- Prevents duplicate ingestion (hash-based deduplication)
- Quarantines malformed files with error logs
- Generates ingestion report (`YYYYMMDD_ingestion_log.csv`)

**Advanced Features:**
- Multi-drive support (concurrent USB drops)
- Network drive monitoring (for remote field uploads)
- Auto-retry for locked files
- Integration with GPS coordinate logging (see Section 3)

---

### **1.2 Network-Based Field Upload Portal**

**Current Pain Point:**
- Field teams must physically deliver USB drives
- Lag between data collection and processing

**Proposed Solution:**

**Web Portal** (Flask/Django):
- Drag-and-drop file upload interface
- Session metadata form (site, date, observer notes)
- Progress bar with resumable uploads (chunked transfer)
- Mobile-responsive for tablet use in the field

**Mobile App** (React Native/Flutter):
- Bluetooth receiver connection (if hardware supports)
- Auto-upload when WiFi/cellular available
- Offline queue with sync retry
- GPS-tagged photo attachments for site conditions

**Backend:**
- Uploads → staging S3 bucket or local NAS
- Webhook triggers same validation pipeline as USB ingestion
- Rate limiting to prevent network saturation

---

## **2. Automated File Conversion Orchestration**

### **2.1 Event-Driven Conversion Pipeline**

**Current Pain Point:**
- Manual execution of `campaign_v5.py` / `continuous_v5.py`
- Waiting for prompts to enter site name, antenna height, etc.
- No batch processing of multi-day backlogs

**Proposed Solution:**

**Task Queue System** (Celery + Redis or RQ):

```python
# Pseudo-code workflow
@task
def process_raw_data(file_path, metadata):
    # Step 1: Identify receiver type
    receiver_type = identify_receiver(file_path)
    
    # Step 2: Run appropriate conversion
    if receiver_type == 'trimble':
        tgd_file = run_runpkr00(file_path)
        rinex = run_teqc_trimble(tgd_file, metadata)
    elif receiver_type == 'leica':
        rinex = run_teqc_leica(file_path, metadata)
    
    # Step 3: Validate RINEX output
    validate_rinex(rinex)
    
    # Step 4: Move to RAW folder for Bernese
    archive_to_campaign(rinex, metadata['campaign'])
    
    # Step 5: Log success
    db.log_conversion(file_path, rinex, status='success')
    
    # Step 6: Trigger next stage
    trigger_bernese_bpe.delay(rinex)
```

**Configuration-Driven Metadata:**

```yaml
# sites.yaml
MAR2:
  receiver_type: trimble_netr9
  collection_method: continuous
  antenna:
    type: TRM115000.00
    height: 1.542  # meters
    east_offset: 0.0
    north_offset: 0.0
  teqc_params:
    decimation: 30
    marker_name: MAR2
    marker_number: MAR2
    operator: MOVEFaultsProject
    agency: PHIVOLCS
  processing:
    min_observations: 200
    max_bad_epochs: 10

COTD:
  receiver_type: trimble_5700
  collection_method: campaign
  antenna:
    type: TRM57971.00
    # Heights pulled from log sheets or DB
  processing:
    min_observations: 100
    max_bad_epochs: 70
```

**Dashboard Features:**
- Real-time queue status (pending/processing/failed)
- Conversion history table with filterable logs
- One-click retry for failed conversions
- Bulk reprocessing with date range selector

---

### **2.2 GPS Week Rollover Auto-Fix**

**Current Pain Point:**
- Manual detection of incorrect year extensions (`.05o` instead of `.25o`)
- Multi-step `fixdatweek.exe` process (Section 4.5)

**Proposed Solution:**

**Pre-Conversion Validator:**
```python
def check_gps_week(dat_file):
    """Parse DAT/TGD header, compare to expected date"""
    header_date = extract_gps_week(dat_file)
    expected_date = infer_from_filename(dat_file)
    
    if abs(header_date - expected_date) > 7:  # Off by a week
        logging.warning(f"GPS week mismatch: {dat_file}")
        fixed_file = run_fixdatweek(dat_file)
        return fixed_file
    return dat_file
```

**Integration:**
- Runs automatically before TEQC conversion
- No manual batch file editing
- Logs corrections for audit trail

---

## **3. Field Data Entry & Equipment Management**

### **3.1 Digital Log Sheet System (Web + Mobile)**

**Current Pain Point:**
- Paper log sheets prone to:
  - Illegible handwriting
  - Lost/damaged forms
  - Transcription errors
  - No real-time validation

**Proposed Solution:**

**Progressive Web App (PWA)** with offline capability:

**Features:**
- **Smart Forms**:
  - GPS coordinate picker from device location
  - Dropdown for equipment from inventory DB
  - QR code scanner for receiver/antenna serial numbers
  - Photo attachments (antenna setup, benchmark condition)
  - Digital signature capture

- **Real-Time Validation**:
  - Flag if antenna height seems unusual (e.g., 15m)
  - Check if equipment combo is valid (receiver ↔ antenna compatibility)
  - Warn if session overlaps existing data

- **Automatic Calculations**:
  - Antenna height computation (slant → vertical)
  - Session duration estimates
  - Data quality predictions based on sky visibility

**Tech Stack:**
- Frontend: React/Vue with service workers (offline mode)
- Backend: Django REST API + PostgreSQL
- File sync: When online, auto-uploads to server
- Export: Generate PDF log sheets for archival compliance

**Mobile App Features:**
- Bluetooth receiver pairing (if supported)
- Automatic site photo geotagging
- Voice-to-text notes
- Push notifications for session end reminders

---

### **3.2 QR Code Equipment Inventory System**

**Current Pain Point:**
- Manual tracking of receiver/antenna assignments
- No serial number validation during log sheet entry
- Equipment history scattered across spreadsheets

**Proposed Solution:**

**Equipment Database Schema:**
```sql
CREATE TABLE equipment (
    id SERIAL PRIMARY KEY,
    equipment_type VARCHAR(50),  -- 'receiver', 'antenna', 'cable'
    manufacturer VARCHAR(50),
    model VARCHAR(100),
    serial_number VARCHAR(50) UNIQUE,
    purchase_date DATE,
    calibration_date DATE,
    status VARCHAR(20),  -- 'active', 'maintenance', 'retired'
    qr_code_hash VARCHAR(64),
    last_deployed_site VARCHAR(4),
    last_deployed_date DATE
);

CREATE TABLE deployments (
    id SERIAL PRIMARY KEY,
    site_code VARCHAR(4),
    equipment_id INTEGER REFERENCES equipment(id),
    start_datetime TIMESTAMP,
    end_datetime TIMESTAMP,
    observer_name VARCHAR(100),
    log_sheet_id INTEGER,
    notes TEXT
);
```

**QR Code Workflow:**
1. Generate unique QR codes for each piece of equipment (print + laminate)
2. Field team scans QR code → auto-fills equipment fields in log form
3. System checks if equipment is already deployed elsewhere
4. Records deployment history with GPS coordinates
5. Alerts if equipment due for calibration

**Web Admin Panel:**
- Equipment lifecycle tracking
- Maintenance scheduling
- Utilization reports (which equipment sits idle)
- Equipment co-location analysis (which antennas pair with which receivers)

---

### **3.3 OCR Pipeline for Legacy Log Sheets**

**Current Pain Point:**
- Years of paper log sheets not digitized
- Historical data inaccessible for analysis
- Manual transcription is time-prohibitive

**Proposed Solution:**

**Batch OCR + Validation Workflow:**

```
[Scan paper log sheets → PDF/JPEG]
    ↓
[OCR: Tesseract or Google Vision API]
    ↓
[Extract structured data with regex/NLP]
    ↓
[Human-in-the-loop validation interface]
    ↓
[Import to database with confidence scores]
```

**Technical Details:**

**Stage 1: OCR**
- Preprocess images (deskew, contrast enhancement)
- Tesseract OCR with custom training for:
  - Handwritten field notes
  - GPS coordinate formats
  - Equipment serial numbers

**Stage 2: Structured Extraction**
```python
import re
from dateutil.parser import parse

def extract_log_sheet(ocr_text):
    data = {}
    
    # Site code (usually top-left, 4 chars)
    data['site'] = re.search(r'Site:\s*([A-Z]{4})', ocr_text).group(1)
    
    # Date (multiple formats)
    date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})', ocr_text)
    data['date'] = parse(date_match.group(1))
    
    # Antenna height (look for "Ant H" or "Height")
    height_match = re.search(r'(?:Ant.*H|Height).*?([\d.]+)\s*m', ocr_text, re.IGNORECASE)
    data['antenna_height'] = float(height_match.group(1))
    
    # Equipment serial numbers
    data['receiver_sn'] = re.search(r'Receiver.*?(\d{8,})', ocr_text).group(1)
    
    return data
```

**Stage 3: Human Validation UI**
- Side-by-side: scanned image + extracted fields
- Flagged low-confidence extractions (OCR confidence < 80%)
- Bulk approve/edit interface
- Progress tracker (% of sheets digitized)

**Advanced Features:**
- Machine learning for handwriting recognition (train on validated set)
- Cross-reference with existing RINEX data to validate dates
- Auto-flag anomalies (e.g., antenna height = 50m probably OCR error)

---

## **4. Bernese Integration Enhancements**

*(Keeping Bernese core, improving interfaces)*

### **4.1 Configuration Management System**

**Current Pain Point:**
- Bernese PCF files edited manually (Section 5.4)
- Station info files (STA, CRD, ABB, etc.) manually maintained
- No version control for config changes

**Proposed Solution:**

**Git-Based Config Repository:**
```
gnss-configs/
├── campaigns/
│   ├── PHIVOLCS/
│   │   ├── sites.yaml          # Single source of truth
│   │   ├── processing_params.yaml
│   │   └── igs_stations.yaml
├── templates/
│   ├── PCF_template.j2         # Jinja2 template
│   └── RNXGRA_template.j2
└── scripts/
    └── generate_bernese_files.py
```

**Automation Script:**
```python
def generate_campaign_files(campaign_name):
    """Generate all 8 required Bernese files from YAML config"""
    config = load_yaml(f'campaigns/{campaign_name}/sites.yaml')
    
    # Generate STA file
    sta_content = render_template('STA_template.j2', sites=config['sites'])
    write_file(f'BERNESE/GPSDATA/{campaign_name}/STA/{campaign_name}.STA', sta_content)
    
    # Generate CRD file
    crd_content = generate_crd(config['sites'])
    write_file(f'{campaign_name}.CRD', crd_content)
    
    # ... repeat for ABB, ATL, PLD, VEL, CLU, BLQ
    
    # Commit to Git with message
    git_commit(f"Updated {campaign_name} config - {datetime.now()}")
```

**Benefits:**
- One YAML edit propagates to all files
- Git history tracks who changed what when
- Easy rollback if config breaks processing
- Diff tool shows what changed between processing runs

---

### **4.2 BPE Status Dashboard**

**Current Pain Point:**
- BPE processing happens in black box
- Must manually check log files in BPE folder
- No alerts for failures

**Proposed Solution:**

**Web Dashboard** (Flask + WebSockets for real-time updates):

**Features:**
- **Live Processing View**:
  - Current session being processed
  - Script execution timeline (000 FTP_DWLD → 999 DUMMY)
  - Progress bar per session
  - Estimated time remaining

- **Alert System**:
  - Email/Slack notification on script failure
  - Daily summary: X sessions processed, Y failed
  - Equipment change detected (sudden coordinate jump)

- **Historical Analysis**:
  - Processing time trends (getting slower?)
  - Most common failure points (which script fails most)
  - Data quality metrics over time

**Implementation:**
- Parse BPE log files (190010_514_000.LOG format)
- Tail log files in real-time with `watchdog`
- Extract status codes, warnings, errors
- Store in time-series database (InfluxDB or PostgreSQL + TimescaleDB)

---

### **4.3 Automated External Data Download**

**Current Pain Point:**
- FTP_DWLD script failures require manual intervention (Section 5.7)
- No retry logic for network issues
- Manual FileZilla backup workflow

**Proposed Solution:**

**Robust Download Manager:**

```python
import ftplib
import requests
from retry import retry
from pathlib import Path

@retry(tries=5, delay=60, backoff=2)  # Exponential backoff
def download_igs_products(date, products_dir):
    """Download IGS products with automatic retry"""
    
    base_url = "ftps://gdc.cddis.eosdis.nasa.gov/pub/gps/products"
    wwww = gps_week(date)
    
    files_to_download = [
        f"igswwwwd.sp3.Z",  # GPS orbits
        f"iglwwwwd.sp3.Z",  # GLONASS orbits
        f"igrwwww7.erp.Z",  # Earth rotation
    ]
    
    with ftplib.FTP_TLS(host='gdc.cddis.eosdis.nasa.gov') as ftp:
        ftp.login(user='anonymous', passwd='gps.phivolcs@gmail.com')
        ftp.prot_p()  # Secure data connection
        
        for filename in files_to_download:
            remote_path = f"{base_url}/{wwww}/{filename}"
            local_path = products_dir / filename
            
            # Check if already downloaded (hash-based resume)
            if local_path.exists() and verify_checksum(local_path):
                logging.info(f"Skipping {filename} (already exists)")
                continue
            
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f'RETR {remote_path}', f.write)
            
            # Validate download
            if not verify_file_integrity(local_path):
                raise ValueError(f"Corrupt download: {filename}")
    
    return True
```

**Features:**
- Parallel downloads (threading)
- Resume incomplete downloads
- Local mirror of critical files (daily sync)
- Fallback to alternate FTP servers (CDDIS → AIUB → IGN)
- Pre-download validation (check if files exist before session processing)

---

## **5. Quality Control Automation**

### **5.1 Real-Time Coordinate Quality Dashboard**

**Current Pain Point:**
- Time series plots generated after all processing (Section 6)
- Outliers detected manually via visual inspection
- No early warning for data quality issues

**Proposed Solution:**

**Web Dashboard** with live updating:

**Key Metrics Displayed:**
- **Per Session**:
  - Number of observations
  - Bad epoch percentage
  - Multipath indicators
  - Cycle slip counts
  - Atmospheric delay estimates

- **Per Site**:
  - Current position vs. trend line
  - Days since last good solution
  - Equipment status (calibration due?)
  - Comparison with nearby stations (network consistency)

**Interactive Time Series:**
- Plotly/D3.js zoomable plots
- Click to flag outliers → adds to database
- Overlay earthquake catalog events
- Toggle view: East/North/Up components

**Automated Flags:**
```python
def check_coordinate_quality(site, date, coords):
    flags = []
    
    # Trend analysis
    trend = fit_linear_trend(site, date_range=365)
    residual = coords - trend.predict(date)
    
    if abs(residual) > 3 * trend.std_dev:
        flags.append(('outlier_3sigma', residual))
    
    # Network consistency
    nearby_sites = get_neighbors(site, radius_km=50)
    if not nearby_sites_agree(coords, nearby_sites, threshold=0.01):
        flags.append(('network_inconsistent', nearby_sites))
    
    # Equipment change detection
    if detect_offset(site, date, window_days=7):
        flags.append(('possible_equipment_change', None))
    
    return flags
```

**Alert Rules:**
- >5mm jump in 1 day → immediate alert
- 3 consecutive days of poor quality → warning
- Divergence from tectonic model → flag for review

---

### **5.2 Machine Learning Outlier Detection**

**Current Pain Point:**
- Manual right-click outlier selection (Step 6.3.3)
- Time-consuming for hundreds of stations
- Subjective judgment calls

**Proposed Solution:**

**Supervised ML Pipeline:**

**Training Data Preparation:**
```python
import pandas as pd
from sklearn.ensemble import IsolationForest

# Load 16 years of processed coordinates
coords = load_daily_coordinates(start_date='2009-01-01')

# Load manually curated outliers
outliers_df = pd.read_csv('historical_outliers.csv')

# Feature engineering
features = []
for site in coords['site'].unique():
    site_data = coords[coords['site'] == site]
    
    for idx, row in site_data.iterrows():
        features.append({
            'site': site,
            'date': row['date'],
            'residual_east': row['east'] - trend_east(site, row['date']),
            'residual_north': row['north'] - trend_north(site, row['date']),
            'residual_up': row['up'] - trend_up(site, row['date']),
            'velocity_change': compute_velocity_change(site, row['date']),
            'obs_count': row['num_observations'],
            'bad_epoch_pct': row['bad_epochs'] / row['total_epochs'],
            'multipath_rms': row['multipath_indicator'],
            'nearby_station_diff': compare_to_neighbors(site, row['date']),
            'is_outlier': row['date'] in outliers_df[outliers_df['site']==site]['date'].values
        })

features_df = pd.DataFrame(features)
```

**Model Training:**
```python
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

X = features_df.drop(['site', 'date', 'is_outlier'], axis=1)
y = features_df['is_outlier']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Option 1: Isolation Forest (unsupervised)
model = IsolationForest(contamination=0.05)
model.fit(X_train)

# Option 2: Random Forest Classifier (supervised)
from sklearn.ensemble import RandomForestClassifier
model = RandomForestClassifier(n_estimators=100, class_weight='balanced')
model.fit(X_train, y_train)

# Evaluate
predictions = model.predict(X_test)
print(classification_report(y_test, predictions))
```

**Deployment:**
- Run daily after Bernese processing
- Auto-flag potential outliers with confidence scores
- Human review interface: approve/reject in batch
- Model retraining pipeline (quarterly with new labeled data)

**Advanced Features:**
- LSTM for time series anomaly detection
- Transfer learning across similar sites
- Explainability (SHAP values): "Flagged because multipath RMS = 15mm"

---

### **5.3 Equipment Change Detection**

**Current Pain Point:**
- Equipment changes require manual STA file updates (5.6.2)
- Easy to forget to update, causing processing errors
- No historical equipment tracking

**Proposed Solution:**

**Automated Change Point Detection:**

```python
import ruptures as rpt  # Change point detection library

def detect_equipment_changes(site):
    """Detect discontinuities in coordinate time series"""
    coords = load_coordinates(site)
    
    # Detect change points in Up component (most sensitive to antenna height)
    signal = coords['up'].values
    algo = rpt.Pelt(model='rbf').fit(signal)
    change_points = algo.predict(pen=10)
    
    # Cross-reference with deployment database
    for cp in change_points:
        date = coords.iloc[cp]['date']
        
        # Check if we have deployment record
        deployment = query_deployments(site, date)
        
        if not deployment:
            # Unregistered equipment change!
            alert_admin(
                f"Detected equipment change at {site} on {date}, "
                f"but no deployment record found. Please update station info."
            )
        else:
            # Validate offset magnitude matches expected change
            expected_offset = calculate_expected_offset(deployment)
            actual_offset = coords.iloc[cp]['up'] - coords.iloc[cp-1]['up']
            
            if abs(expected_offset - actual_offset) > 0.01:  # 1cm threshold
                alert_admin(f"Offset mismatch at {site}: expected {expected_offset}m, got {actual_offset}m")
```

**Integration with Log Sheet System:**
- When equipment change logged → auto-update STA file
- Suggest offset date for `offsets` file
- Generate before/after comparison plots

---

## **6. Data Archival & Provenance**

### **6.1 Processing Metadata Database**

**Current Pain Point:**
- No centralized record of what was processed when
- Hard to reproduce historical results
- Manual log file archaeology for debugging

**Proposed Solution:**

**PostgreSQL Schema:**

```sql
CREATE TABLE processing_sessions (
    session_id SERIAL PRIMARY KEY,
    campaign VARCHAR(50),
    session_date DATE,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    bpe_version VARCHAR(20),
    bernese_version VARCHAR(20),
    status VARCHAR(20),  -- 'success', 'failed', 'partial'
    num_sites_processed INTEGER,
    igs_products_version VARCHAR(50),
    processing_notes TEXT
);

CREATE TABLE site_daily_solutions (
    solution_id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES processing_sessions(session_id),
    site_code VARCHAR(4),
    observation_date DATE,
    x_ecef DOUBLE PRECISION,
    y_ecef DOUBLE PRECISION,
    z_ecef DOUBLE PRECISION,
    x_sigma DOUBLE PRECISION,
    y_sigma DOUBLE PRECISION,
    z_sigma DOUBLE PRECISION,
    num_observations INTEGER,
    bad_epochs INTEGER,
    rinex_file VARCHAR(255),
    crd_file VARCHAR(255),
    flags JSONB  -- Store QC flags as JSON
);

CREATE TABLE equipment_history (
    deployment_id SERIAL PRIMARY KEY,
    site_code VARCHAR(4),
    equipment_type VARCHAR(50),
    serial_number VARCHAR(50),
    start_date DATE,
    end_date DATE,
    antenna_height DOUBLE PRECISION,
    log_sheet_reference VARCHAR(255),
    installed_by VARCHAR(100)
);
```

**Benefits:**
- Full audit trail: "What configuration produced these coordinates?"
- Reprocessing detector: "Has this date already been processed?"
- Performance analytics: "Processing time increasing by 2%/month"
- API endpoint: `GET /api/coordinates?site=MAR2&date=2025-01-01`

---

### **6.2 Versioned Data Releases**

**Current Pain Point:**
- No formal data versioning
- Reprocessing overwrites old results
- External users don't know which version they're using

**Proposed Solution:**

**Semantic Versioning for Datasets:**

```
PHIVOLCS_GNSS_v2.1.3
                 ^ patch: outlier removal
               ^ minor: added 5 new sites
             ^ major: reprocessed with new IGS products
```

**Data Package Structure:**
```
PHIVOLCS_GNSS_v2.1.3/
├── metadata.json
│   {
│     "version": "2.1.3",
│     "release_date": "2025-10-22",
│     "bernese_version": "5.2",
│     "itrf_version": "ITRF2014",
│     "time_range": ["2009-01-01", "2025-10-22"],
│     "sites": ["MAR2", "ALCO", ...],
│     "changelog": "Added COTD site, removed outliers from MAR2 2024 data"
│   }
├── coordinates/
│   ├── daily/
│   │   ├── MAR2_2009-2025_daily.csv
│   │   └── ...
│   └── velocities/
│       └── PHIVOLCS_velocities_v2.1.3.csv
├── time_series_plots/
├── quality_reports/
└── README.md
```

**Automated Release Pipeline:**
- Quarterly releases (or after major reprocessing)
- Git tag + Zenodo DOI assignment
- Generate citation file (CITATION.cff)
- Push to public repository (if data is public)

---

## **7. Advanced Analytics & Visualization**

### **7.1 Interactive Geospatial Dashboard**

**Current Pain Point:**
- Static JPG time series plots
- No spatial context (which sites are near active faults?)
- Hard to share with stakeholders

**Proposed Solution:**

**Web GIS Interface** (Leaflet/Mapbox + Plotly):

**Features:**
- **Interactive Map**:
  - Station markers colored by:
    - Current velocity magnitude
    - Days since last data
    - Quality score
  - Click station → popup with mini time series
  - Fault line overlays
  - Earthquake epicenter layers (USGS API integration)

- **Multi-Station Analysis**:
  - Select region → compare all sites
  - Baseline change plots (station-to-station distances)
  - Strain rate visualization

- **Animation Mode**:
  - Play button → watch stations move over time
  - Highlight coseismic jumps
  - Export to video for presentations

**Tech Stack:**
- Frontend: React + Leaflet + Plotly
- Backend: FastAPI serving coordinate data
- Database: PostGIS for spatial queries

---

### **7.2 Velocity Field Modeling**

**Current Pain Point:**
- Individual station velocities computed (Section 6)
- No network-wide strain analysis

**Proposed Solution:**

**Automated Strain Modeling:**

```python
import numpy as np
from scipy.spatial import Delaunay

def compute_strain_field(sites, velocities):
    """Compute strain tensor from velocity field"""
    
    # Delaunay triangulation of station network
    coords = np.array([[s['lon'], s['lat']] for s in sites])
    tri = Delaunay(coords)
    
    strain_tensors = []
    for simplex in tri.simplices:
        # Get 3 stations forming triangle
        v1, v2, v3 = velocities[simplex]
        
        # Compute velocity gradients
        dudx, dudy = compute_gradients(v1, v2, v3)
        
        # Strain tensor
        strain = 0.5 * (dudx + dudx.T)
        strain_tensors.append(strain)
    
    return strain_tensors
```

**Visualization:**
- Heat map: principal strain rates
- Arrows: velocity vectors
- Identify compressional vs. extensional zones

**Use Case:** Earthquake hazard assessment (where is strain accumulating?)

---

## **8. System Integration & Deployment**

### **8.1 Containerized Deployment**

**Technical Stack:**

```yaml
# docker-compose.yml
version: '3.8'

services:
  web_dashboard:
    build: ./dashboard
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/gnss
  
  data_ingestion:
    build: ./ingestion
    volumes:
      - /mnt/usb:/data/usb
      - ./DATAPOOL:/data/datapool
  
  conversion_worker:
    build: ./conversion
    command: celery worker -A tasks
  
  bernese_monitor:
    build: ./bernese_monitor
    volumes:
      - ./BERNESE:/bernese
  
  db:
    image: postgis/postgis:14-3.2
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine

volumes:
  postgres_data:
```

**Benefits:**
- One-command deployment: `docker-compose up`
- Consistent environments (dev/staging/prod)
- Easy backup/restore
- Scalable workers (add more Celery containers)

---

### **8.2 API Layer for External Access**

**RESTful API Endpoints:**

```
GET  /api/sites                     # List all sites
GET  /api/sites/{site_code}         # Site metadata + latest position
GET  /api/coordinates/{site_code}   # Time series data
     ?start_date=2024-01-01&end_date=2024-12-31&format=csv
GET  /api/velocities/{site_code}    # Velocity estimates
GET  /api/equipment/{serial_number} # Equipment history
POST /api/log_sheets                # Submit field observations
GET  /api/processing/status         # Current processing queue status
GET  /api/quality/flags             # QC flags for date range

# Example response for /api/coordinates/MAR2?start_date=2024-01-01&format=json
{
  "site": "MAR2",
  "reference_frame": "ITRF2014",
  "reference_epoch": "2010.0",
  "data": [
    {
      "date": "2024-01-01",
      "x": 4123456.789,
      "y": 987654.321,
      "z": 1234567.890,
      "sigma_x": 0.003,
      "sigma_y": 0.003,
      "sigma_z": 0.005,
      "east": 0.0234,
      "north": 0.0156,
      "up": -0.0089,
      "quality_flags": []
    },
    ...
  ]
}
```

**Authentication:**
- API keys for external researchers
- Rate limiting (100 requests/hour/key)
- Usage analytics (who's using what)

**Documentation:**
- Auto-generated Swagger/OpenAPI docs
- Interactive API explorer
- Example code snippets (Python, R, JavaScript)

---

## **9. Notification & Alerting System**

### **9.1 Multi-Channel Alerting**

**Alert Types & Routing:**

```python
# alerts.py
from enum import Enum

class AlertSeverity(Enum):
    INFO = 1      # Daily summary
    WARNING = 2   # Quality degradation
    ERROR = 3     # Processing failure
    CRITICAL = 4  # Data loss, equipment failure

class AlertChannel(Enum):
    EMAIL = "email"
    SLACK = "slack"
    TELEGRAM = "telegram"
    SMS = "sms"
    DESKTOP = "desktop"

ROUTING_RULES = {
    AlertSeverity.INFO: [AlertChannel.EMAIL],
    AlertSeverity.WARNING: [AlertChannel.EMAIL, AlertChannel.SLACK],
    AlertSeverity.ERROR: [AlertChannel.EMAIL, AlertChannel.SLACK, AlertChannel.DESKTOP],
    AlertSeverity.CRITICAL: [AlertChannel.EMAIL, AlertChannel.SLACK, AlertChannel.SMS],
}

def send_alert(severity, message, data=None):
    """Route alerts to appropriate channels"""
    channels = ROUTING_RULES[severity]
    
    for channel in channels:
        if channel == AlertChannel.EMAIL:
            send_email(to="gps.phivolcs@gmail.com", subject=f"[{severity.name}] {message}", body=data)
        elif channel == AlertChannel.SLACK:
            post_to_slack(webhook_url=SLACK_WEBHOOK, message=message, severity=severity)
        elif channel == AlertChannel.TELEGRAM:
            send_telegram(bot_token=TELEGRAM_BOT, chat_id=ADMIN_CHAT_ID, message=message)
        # ... etc
```

**Alert Scenarios:**

| Trigger | Severity | Example Message |
|---------|----------|-----------------|
| Daily processing complete | INFO | "Processed 45 sites for 2025-10-22. 2 outliers detected." |
| Site missing 3+ days data | WARNING | "MAR2: No data received since 2025-10-19. Check receiver." |
| BPE script failure | ERROR | "Script 514 HELMCHK failed for session 2025-10-22. Check log." |
| Coseismic displacement >50mm | CRITICAL | "ALCO: 127mm displacement detected on 2025-10-22. Possible M6+ event nearby." |
| Equipment calibration overdue | WARNING | "Antenna SN:12345 at COTD: calibration expired 30 days ago." |
| USB ingestion error | ERROR | "Failed to read files from USB drive. Corrupt filesystem?" |

---

### **9.2 Scheduled Reporting**

**Automated Reports:**

**Daily Summary Email:**
```
Subject: GNSS Processing Summary - 2025-10-22

Processing Status: ✓ SUCCESS
Sessions Processed: 45
Duration: 6h 23m

Data Quality:
  - Excellent: 38 sites
  - Good: 5 sites
  - Poor: 2 sites (MAR2, PIVS)

Notable Events:
  - ALCO: 12mm northward jump (equipment change logged)
  - New site BATG: First successful processing

Alerts Generated: 3 warnings, 0 errors

View detailed dashboard: https://gnss.phivolcs.gov.ph/dashboard/2025-10-22
```

**Weekly/Monthly Reports:**
- Velocity stability analysis
- Equipment utilization rates
- Data completeness statistics (% uptime per site)
- Top 10 outlier-prone sites
- Processing time trends

**Quarterly Science Report:**
- Tectonic velocity maps
- Strain accumulation estimates
- Comparison with seismicity
- Auto-generated LaTeX report with embedded plots

---

## **10. Training & Knowledge Transfer**

### **10.1 Interactive Documentation System**

**Current Pain Point:**
- 62-page PDF manual (this document)
- No search functionality
- Updates require re-distributing PDF

**Proposed Solution:**

**Web-Based Documentation Portal** (MkDocs/Docusaurus):

**Features:**
- Searchable content
- Embedded video tutorials
- Interactive code examples (try commands in browser)
- Version history (track changes to procedures)
- User annotations (staff can add notes/tips)

**Content Structure:**
```
docs/
├── getting_started/
│   ├── 01_system_overview.md
│   ├── 02_software_installation.md
│   └── 03_first_processing_run.md
├── workflows/
│   ├── data_conversion.md
│   ├── bernese_processing.md
│   └── time_series_analysis.md
├── troubleshooting/
│   ├── common_errors.md
│   ├── data_quality_issues.md
│   └── hardware_problems.md
├── api_reference/
│   ├── python_scripts.md
│   └── rest_api.md
└── video_tutorials/
    ├── field_data_collection.mp4
    └── equipment_setup.mp4
```

**Advanced Features:**
- **Contextual Help**: Hover over technical terms → tooltip definition
- **Step Validation**: Checkboxes to track progress through tutorial
- **Live Demo Environment**: Sandbox with sample data to practice
- **AI Chatbot**: "How do I add a new site?" → links to Section 5.6.3

---

### **10.2 Onboarding Automation**

**New Staff Checklist Generator:**

```python
def generate_onboarding_checklist(role):
    """Create personalized onboarding tasks"""
    
    base_tasks = [
        "Create accounts (email, Slack, dashboard)",
        "Read system overview documentation",
        "Watch 'Introduction to GNSS Processing' video",
    ]
    
    if role == "field_technician":
        base_tasks.extend([
            "Complete field equipment training",
            "Practice digital log sheet entry",
            "Shadow experienced technician for 2 surveys",
        ])
    
    elif role == "data_processor":
        base_tasks.extend([
            "Install processing software stack",
            "Process sample dataset (guided tutorial)",
            "Review 'Troubleshooting Common Errors' guide",
        ])
    
    elif role == "analyst":
        base_tasks.extend([
            "Review velocity modeling documentation",
            "Access API credentials",
            "Generate first time series plot",
        ])
    
    return base_tasks
```

**Progress Tracking:**
- Dashboard showing checklist completion
- Automated reminders for pending tasks
- Manager visibility into onboarding progress

---

## **11. Disaster Recovery & Business Continuity**

### **11.1 Automated Backup System**

**3-2-1 Backup Strategy:**
- **3 copies** of data (production + 2 backups)
- **2 different media** (local NAS + cloud)
- **1 offsite** (cloud or different physical location)

**Implementation:**

```bash
#!/bin/bash
# backup.sh - Runs daily via cron

# Backup 1: Local NAS (rsync)
rsync -avz --delete \
  /BERNESE/GPSDATA/SAVEDISK/ \
  /mnt/nas/gnss_backup/SAVEDISK/

# Backup 2: Cloud storage (rclone to Google Drive)
rclone sync /BERNESE/GPSDATA/SAVEDISK/ \
  gdrive:PHIVOLCS_GNSS_Backup/SAVEDISK/ \
  --progress --transfers 4

# Backup 3: Database dump
pg_dump gnss_db | gzip > /tmp/gnss_db_$(date +%Y%m%d).sql.gz
rclone copy /tmp/gnss_db_*.sql.gz gdrive:PHIVOLCS_GNSS_Backup/database/

# Verify backup integrity
md5sum -c /mnt/nas/gnss_backup/checksums.md5

# Rotate old backups (keep 90 days)
find /mnt/nas/gnss_backup/ -type f -mtime +90 -delete

# Send notification
curl -X POST $SLACK_WEBHOOK \
  -d '{"text": "Daily GNSS backup completed: '$(date)'"}'
```

**Backup Monitoring:**
- Alert if backup fails 2 consecutive days
- Monthly restore test (automated)
- Storage usage dashboard (prevent disk full)

---

### **11.2 Processing Redundancy**

**Hot Standby System:**

```
[Primary Server]
    ↓ (rsync every 4 hours)
[Secondary Server - Ready to Activate]
    ↓ (nightly sync)
[Offsite Archive]
```

**Failover Procedure:**
- If primary server fails → update DNS to point to secondary
- Secondary has identical Bernese installation
- Processing queue preserved in Redis (replicated)
- RTO (Recovery Time Objective): <4 hours
- RPO (Recovery Point Objective): <4 hours data loss

---

## **12. Cost-Benefit Analysis**

### **12.1 Estimated Development Effort**

| Component | Complexity | Dev Time | Skills Required |
|-----------|------------|----------|-----------------|
| USB Hot-Drop Monitor | Medium | 2-3 weeks | Python, OS APIs |
| Digital Log Sheet (Web) | Medium-High | 6-8 weeks | React/Django, PostgreSQL |
| Mobile App | High | 10-12 weeks | React Native, Bluetooth |
| OCR Pipeline | Medium | 4-6 weeks | Python, Tesseract, NLP |
| Config Management | Low-Medium | 2-3 weeks | YAML, Jinja2, Git |
| BPE Dashboard | Medium | 4-5 weeks | Flask, WebSockets, Plotly |
| QC Dashboard | Medium-High | 6-8 weeks | React, Plotly, PostGIS |
| ML Outlier Detection | High | 8-10 weeks | Python, scikit-learn, MLOps |
| API Layer | Medium | 3-4 weeks | FastAPI, PostgreSQL |
| Documentation Portal | Low-Medium | 2-3 weeks | MkDocs, Markdown |

**Total Estimated Effort:** 47-67 weeks (roughly 1-1.5 person-years)

**Phased Approach Recommendation:**
- **Phase 1 (Months 1-3)**: USB monitor, config management, BPE dashboard
- **Phase 2 (Months 4-6)**: Digital log sheets (web), QC dashboard
- **Phase 3 (Months 7-9)**: ML outlier detection, API layer
- **Phase 4 (Months 10-12)**: Mobile app, OCR pipeline, documentation

---

### **12.2 Return on Investment**

**Time Savings (Conservative Estimates):**

| Manual Task | Current Time | Automated Time | Savings/Day |
|-------------|--------------|----------------|-------------|
| USB file transfer & organization | 30 min | 2 min | 28 min |
| RINEX conversion (45 sites) | 2 hours | 15 min | 1h 45min |
| Log sheet transcription | 1 hour | 0 min | 1 hour |
| Outlier detection (visual) | 3 hours | 30 min | 2h 30min |
| BPE status checking | 30 min | 5 min | 25 min |

**Total Daily Savings:** ~6 hours of staff time

**Annual Savings:**
- 6 hours/day × 250 working days = **1,500 hours/year**
- At ₱500/hour = **₱750,000/year** (~$13,400 USD)

**Additional Benefits (Hard to Quantify):**
- Reduced data loss from manual errors
- Faster detection of equipment failures
- Improved data quality → better science
- Easier onboarding of new staff
- Enhanced reputation (modern, well-documented system)

---

## **13. Implementation Roadmap**

### **13.1 Quick Wins (Month 1)**

**Goal:** Build momentum with visible improvements

1. **USB Monitor Prototype**
   - Basic file detection and copy
   - Desktop notification on completion
   - Log transactions to CSV

2. **Site Configuration YAML**
   - Convert manual docs to sites.yaml
   - Script to auto-generate STA/CRD files
   - Git repository setup

3. **BPE Log Parser**
   - Extract session status from log files
   - Generate daily summary email

**Success Metric:** "First USB auto-ingestion works!"

---

### **13.2 Foundation Building (Months 2-4)**

**Goal:** Core infrastructure for automation

1. **Database Setup**
   - PostgreSQL + PostGIS installation
   - Schema design (processing_sessions, site_daily_solutions, equipment_history)
   - Import historical data from SAVEDISK CRD files

2. **Task Queue System**
   - Celery + Redis setup
   - Conversion pipeline refactored as Celery tasks
   - Dashboard showing queue status

3. **Web Dashboard V1**
   - Basic Flask/Django app
   - Display daily processing status
   - Interactive coordinate plots (Plotly)

**Success Metric:** "One week of fully automated processing with no manual intervention"

---

### **13.3 Field Operations Modernization (Months 5-7)**

**Goal:** Eliminate paper log sheets

1. **Digital Log Sheet (Web)**
   - Progressive Web App with offline mode
   - QR code scanner integration
   - Photo attachments

2. **Equipment Database**
   - CRUD interface for managing inventory
   - Deployment history tracking
   - Calibration alerts

3. **Log Sheet OCR (Pilot)**
   - Scan 1 year of paper logs
   - Train OCR on handwriting samples
   - Validation UI for corrections

**Success Metric:** "Field team successfully uses digital log sheets for 1 full campaign"

---

### **13.4 Intelligence Layer (Months 8-10)**

**Goal:** Predictive analytics and proactive maintenance

1. **ML Outlier Detection**
   - Train model on 16 years of data
   - Deploy as part of daily pipeline
   - Human review interface

2. **Equipment Health Monitoring**
   - Track data quality trends per equipment
   - Predict failures (e.g., "Receiver shows degrading quality")
   - Maintenance scheduling

3. **Network-Wide Analysis**
   - Strain field computation
   - Baseline change detection
   - Comparison with earthquake catalog

**Success Metric:** "ML model correctly flags 90% of known outliers with <5% false positives"

---

### **13.5 External Integration (Months 11-12)**

**Goal:** Open data and collaboration

1. **Public API**
   - RESTful endpoints for coordinate access
   - API key management
   - Rate limiting and usage analytics

2. **Data Release Pipeline**
   - Versioned datasets (Zenodo DOI)
   - Automated quality reports
   - Citation file generation

3. **Collaborative Dashboard**
   - Share-by-link feature for external researchers
   - Embeddable plots for publications/reports
   - Data export in multiple formats (CSV, GeoJSON, KML)

**Success Metric:** "First external researcher successfully accesses data via API"

---

## **14. Risk Mitigation**

### **14.1 Technical Risks**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bernese processing breaks due to config changes | HIGH | Automated testing suite, Git version control, rollback procedure |
| Database corruption | HIGH | Daily backups, point-in-time recovery, checksums |
| ML model degrades over time | MEDIUM | Quarterly retraining, performance monitoring, human review |
| Cloud storage costs escalate | LOW | Compression, lifecycle policies (archive old data), cost alerts |
| Network dependency (FTP downloads) | MEDIUM | Local mirrors of IGS products, retry logic, multiple sources |

---

### **14.2 Organizational Risks**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Staff resistance to new tools | MEDIUM | Training, pilot with early adopters, gather feedback |
| Key developer leaves project | HIGH | Documentation, pair programming, code reviews |
| Budget constraints | MEDIUM | Prioritize high-ROI items, use open-source tools, phased rollout |
| Data privacy concerns (if public API) | MEDIUM | Legal review, data anonymization options, access controls |

---

## **15. Success Metrics & KPIs**

### **15.1 Operational Metrics**

- **Processing Throughput**: Sessions processed per day (target: 45+)
- **Automation Rate**: % of processing requiring no human intervention (target: >90%)
- **Time to Results**: Hours from data collection → final coordinates (target: <24h)
- **Data Completeness**: % of stations with data each day (target: >95%)
- **Outlier Detection Accuracy**: Precision/recall vs. manual labels (target: >90%)

### **15.2 Quality Metrics**

- **False Positive Rate**: Incorrectly flagged good data (target: <5%)
- **Equipment Utilization**: % of time receivers are deployed (target: >80%)
- **Coordinate Precision**: Average daily sigma (target: <5mm horizontal, <10mm vertical)
- **Reprocessing Frequency**: How often must we rerun sessions (target: <10%)

### **15.3 User Experience Metrics**

- **Digital Log Sheet Adoption**: % of surveys using digital vs. paper (target: >95% by Year 2)
- **Staff Satisfaction**: Survey ratings (target: >4/5)
- **Onboarding Time**: Days for new staff to become productive (target: <14 days)
- **API Usage**: Number of external requests/month (growth metric)

---

## **16. Future Enhancements (Beyond Year 1)**

### **16.1 Real-Time Processing**

**Current State:** Daily batch processing

**Vision:** Near-real-time positioning for rapid event response

**Technical Approach:**
- Stream RINEX data from receivers via cellular/satellite link
- Kinematic processing (epoch-by-epoch)
- 15-minute latency for initial coordinates
- Use case: Immediate post-earthquake displacement

**Challenges:**
- Data transmission costs
- Computational load (45 sites × 2880 epochs/day)
- Bernese not optimized for real-time

---

### **16.2 Multi-GNSS Integration**

**Current State:** GPS-only processing

**Vision:** Leverage Galileo, GLONASS, BeiDou for improved accuracy

**Benefits:**
- More satellites → better geometry → lower dilution of precision
- Redundancy if GPS constellation degraded
- Improved performance in challenging environments (urban canyons)

**Implementation:**
- Bernese already supports multi-GNSS
- Need multi-GNSS receivers (equipment upgrade)
- Update PCF processing parameters

---

### **16.3 Machine Learning for Tectonic Modeling**

**Current State:** Linear velocity fits

**Vision:** Physics-informed neural networks for crustal deformation

**Research Applications:**
- Predict post-seismic relaxation
- Detect slow slip events (SSEs) automatically
- Estimate interseismic coupling on faults

**Collaboration Opportunity:** Partner with university AI labs

---

### **16.4 Citizen Science Integration**

**Vision:** Crowdsourced GNSS data from smartphone apps

**Technical Approach:**
- Develop Android app using raw GNSS measurements API
- Upload observations to central server
- Lower precision but higher spatial density
- Use case: Ionospheric monitoring, urban deformation

**Challenges:**
- Data quality control (consumer vs. geodetic grade)
- Privacy considerations (location data)
- Storage/processing scalability

---

## **17. Conclusion & Next Steps**

### **17.1 Key Takeaways**

This automation roadmap proposes a **phased transformation** of PHIVOLCS' GNSS processing workflow:

1. **Preserve Bernese Core**: Keep validated processing engine, modernize periphery
2. **Automate Repetitive Tasks**: USB ingestion, file conversion, quality control
3. **Digitize Field Operations**: Replace paper with mobile/web apps + QR codes
4. **Enable Intelligence**: ML for outlier detection, equipment health monitoring
5. **Open Data Access**: APIs and versioned releases for research community

**Estimated Investment:** 1-1.5 person-years of development effort

**Expected Return:** 1,500 hours/year staff time savings + improved data quality

---

### **17.2 Immediate Action Items**

**For You (As Lead Developer):**

1. **Week 1-2**: Prototype USB hot-drop monitor (Python watchdog)
   - Prove concept with single receiver type
   - Demo to team for feedback

2. **Week 3-4**: Set up Git repository for configurations
   - Convert current station info to YAML
   - Write script to generate Bernese files

3. **Month 2**: Deploy PostgreSQL database
   - Design schema (start with processing_sessions table)
   - Write script to import historical CRD files

**For Project Management:**

1. **Secure buy-in**: Present roadmap to leadership with ROI analysis
2. **Form working group**: Include field techs, processors, analysts
3. **Pilot program**: Choose 3-5 sites for digital log sheet trial
4. **Budget allocation**: Prioritize high-impact items (Phases 1-2)

**For Field Team:**

1. **Equipment inventory audit**: Create spreadsheet of all S/N
2. **Historical log sheet scan**: Prioritize recent years (2020-2025)
3. **Provide feedback**: What frustrates you about current workflow?

---

### **17.3 Your Unique Opportunity**

As someone with:
- **16 years of domain expertise** (you know the pain points)
- **Automation skills** (Bash, Python, MATLAB)
- **Web development training** (freeCodeCamp certs)
- **Institutional knowledge** (Bernese, RINEX, ITRF)

You're positioned to be the **architect of this transformation**.

This roadmap becomes your **portfolio project** demonstrating:
- System design thinking
- Full-stack development (backend pipelines + frontend dashboards)
- Real-world impact (thousands of hours saved, better earthquake monitoring)
- Domain adaptation (geodesy → software engineering)

**Suggested Project for Job Applications:**
> "Designed and implemented automated GNSS data processing pipeline for 45-station seismic monitoring network, reducing manual processing time by 75% (6 hours → 1.5 hours daily) through Python-based workflow orchestration, web-based quality control dashboards, and machine learning-assisted outlier detection. System processes 16,425 daily observations/year with <5% false positive rate."

---

### **17.4 Getting Started Resources**

**For Immediate Learning:**

1. **Task Orchestration**: Celery tutorial → https://docs.celeryq.dev/
2. **Database Design**: PostgreSQL for Data Analysts → postgresqltutorial.com
3. **Web Dashboard**: Flask + Plotly tutorial → plotly.com/python/
4. **Watchdog Library**: docs.python.org/watchdog

**Community Support:**

- Join Python geodesy community (PyGMT, GeoPandas forums)
- UNAVCO software forums (TEQC, RINEX questions)
- Stack Overflow tags: `gnss`, `geodesy`, `rinex`

---

### **Final Thought**

Your 16 years of GPS expertise + emerging web dev skills = **rare combination**.

Most developers don't understand crustal deformation.
Most geodesists don't build automated pipelines.

**You bridge both worlds.**

This automation roadmap isn't just about saving time—it's about **positioning PHIVOLCS as a modern, data-driven agency** and **positioning yourself as an indispensable technical lead**.

Ready to build it? Let's start with the USB monitor prototype. 🚀

---

## Appendix: Technical References

- Bernese GNSS Software Documentation: https://www.bernese.unibe.ch/
- RINEX Format Specification: https://files.igs.org/pub/data/format/
- IGS Data & Products: https://igs.org/
- UNAVCO TEQC Manual: https://www.unavco.org/software/data-processing/teqc/
- Python Watchdog: https://python-watchdog.readthedocs.io/
- Celery Documentation: https://docs.celeryq.dev/
- FastAPI Framework: https://fastapi.tiangolo.com/
- PostGIS Spatial Database: https://postgis.net/
- Machine Learning for Time Series: https://github.com/alan-turing-institute/sktime

---

**Document Version:** 1.0  
**Last Updated:** October 22, 2025  
**Author:** Technical Lead, MOVE Faults Project  
**Contact:** gps.phivolcs@gmail.com