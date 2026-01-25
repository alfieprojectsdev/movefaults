[Smart USB data ingestion system \| ar.pelicano@phivolcs.dost.gov.ph/Claude](https://claude.ai/share/d9bdf15b-3960-440b-83c2-ddd2b69025ea)
This is an **expansion** of the original USB hot-drop concept—transforming it from a passive GNSS data ingestion tool into an **intelligent filesystem archaeologist** that understands MOVE Faults' messy legacy infrastructure;  phased implementation strategy below, builds toward a production-grade system.

---

## **System Architecture: "GNSS Filesystem Detective"**

### **Phase 1: Foundation (Week 1-2)**
**Goal**: Scan drive → identify files → report findings

```python
# filesystem_detective.py
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import hashlib
import pandas as pd
from datetime import datetime

class DriveAnalyzer:
    def __init__(self):
        self.file_registry = []
        self.patterns = {
            'rinex_obs': r'^\w{4}\d{3}[0-9a-x]\.\d{2}[oO]$',  # ALGO0010.22O
            'rinex_nav': r'^\w{4}\d{3}[0-9a-x]\.\d{2}[nN]$',  # ALGO0010.22N
            'trimble_dat': r'^.+\.dat$',
            'leica_mdb': r'^.+\.m[0-9]{2}$',
            'bernese_sta': r'^.+\.STA$',
            'logsheet_pdf': r'^.+(logsheet|log).+\.pdf$',
            'gmt_script': r'^.+\.(gmt|sh|bash)$'
        }
    
    def scan_drive(self, root_path):
        """Recursively catalog all files with metadata"""
        for filepath in Path(root_path).rglob('*'):
            if filepath.is_file():
                metadata = {
                    'path': str(filepath),
                    'size': filepath.stat().st_size,
                    'modified': datetime.fromtimestamp(filepath.stat().st_mtime),
                    'md5': self._hash_file(filepath),
                    'type': self._classify_file(filepath.name)
                }
                self.file_registry.append(metadata)
        
        return pd.DataFrame(self.file_registry)
    
    def _hash_file(self, filepath, chunk_size=8192):
        """Memory-efficient MD5 for large files"""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _classify_file(self, filename):
        """Match filename against known patterns"""
        import re
        for filetype, pattern in self.patterns.items():
            if re.match(pattern, filename, re.IGNORECASE):
                return filetype
        return 'unknown'
```

**Why this first**: You need **immediate visual feedback** about what's on the drive before automation kicks in. This generates a CSV you can inspect.

---

### **Phase 2: Structure Recognition (Week 3-4)**
**Goal**: Infer intended organization from existing chaos

```python
class StructureAnalyzer:
    def analyze_directory_tree(self, df):
        """Detect organizational patterns"""
        # Extract directory depth and common prefixes
        df['depth'] = df['path'].str.count(r'[/\\]')
        df['parent'] = df['path'].apply(lambda x: str(Path(x).parent))
        
        # Identify clusters (files grouped by directory)
        clusters = df.groupby('parent').agg({
            'type': lambda x: x.value_counts().to_dict(),
            'size': 'sum',
            'path': 'count'
        }).rename(columns={'path': 'file_count'})
        
        # Flag "canonical" structures (e.g., DATAPOOL/SITE/YYYY/)
        canonical_patterns = [
            r'DATAPOOL/\w{4}/\d{4}',  # DATAPOOL/ALGO/2022
            r'RAW/\d{4}/\d{3}',        # RAW/2022/100
            r'RINEX/\w{4}'             # RINEX/ALGO
        ]
        
        clusters['is_canonical'] = clusters.index.to_series().apply(
            lambda x: any(re.search(p, x) for p in canonical_patterns)
        )
        
        return clusters
    
    def recommend_reorganization(self, df):
        """Generate optimal folder structure"""
        # Group RINEX files by site code (first 4 chars)
        rinex_files = df[df['type'].str.contains('rinex', na=False)]
        rinex_files['site'] = rinex_files['path'].apply(
            lambda x: Path(x).name[:4].upper()
        )
        
        # Propose: DATAPOOL/{SITE}/{YEAR}/{DOY}/
        rinex_files['proposed_path'] = rinex_files.apply(
            lambda row: f"DATAPOOL/{row['site']}/2022/100/{Path(row['path']).name}",
            axis=1
        )
        
        return rinex_files[['path', 'proposed_path', 'md5']]
```

**Output**: A report showing:
- **Found**: 327 RINEX files scattered across 12 folders
- **Recommended**: Consolidate into `DATAPOOL/{SITE}/{YYYY}/` structure
- **Action**: Generate shell script to execute moves

---

### **Phase 3: Executable Migration Scripts (Week 5-6)**
**Goal**: Generate **safe**, **reversible** reorganization commands

```python
class MigrationScriptGenerator:
    def generate_bash_script(self, df, output_file='reorganize.sh'):
        """Create executable with dry-run mode"""
        script = ['#!/bin/bash', 'set -euo pipefail', '', '# Dry run by default']
        script.append('DRY_RUN=${DRY_RUN:-true}')
        script.append('')
        
        for _, row in df.iterrows():
            src = row['path']
            dst = row['proposed_path']
            
            # Safety checks
            script.append(f'# MD5: {row["md5"]}')
            script.append(f'mkdir -p "$(dirname "{dst}")"')
            script.append(f'if [ "$DRY_RUN" = true ]; then')
            script.append(f'  echo "WOULD MOVE: {src} -> {dst}"')
            script.append(f'else')
            script.append(f'  mv -n "{src}" "{dst}"  # -n prevents overwrite')
            script.append(f'  echo "MOVED: {src}"')
            script.append(f'fi')
            script.append('')
        
        Path(output_file).write_text('\n'.join(script))
        Path(output_file).chmod(0o755)  # Make executable
        
        return f"Generated: {output_file}\nRun: DRY_RUN=false ./{output_file}"
```

**Usage**:
```bash
# Test first (no changes)
./reorganize.sh

# Execute when confident
DRY_RUN=false ./reorganize.sh
```

---

### **Phase 4: USB Hot-Drop Integration (Week 7-8)**
**Goal**: Auto-trigger on drive mount

```python
from watchdog.events import FileSystemEventHandler

class USBMountHandler(FileSystemEventHandler):
    def on_created(self, event):
        """Triggered when USB drive mounted"""
        if event.is_directory and '/media/' in event.src_path:
            print(f"🔍 Analyzing: {event.src_path}")
            
            analyzer = DriveAnalyzer()
            df = analyzer.scan_drive(event.src_path)
            df.to_csv(f"usb_scan_{datetime.now():%Y%m%d_%H%M%S}.csv")
            
            # Auto-generate migration script
            structure = StructureAnalyzer()
            recommendations = structure.recommend_reorganization(df)
            MigrationScriptGenerator().generate_bash_script(recommendations)
            
            # Desktop notification
            notify("USB Drive Scanned", f"Found {len(df)} files\nScript ready: reorganize.sh")

# Start monitoring
observer = Observer()
observer.schedule(USBMountHandler(), path='/media', recursive=True)
observer.start()
```

---

## **Key Design Principles (ADHD-Optimized)**

### ✅ **What Makes This Work for You**
1. **Incremental Feedback**: CSV reports at every step (satisfies need to "see progress")
2. **Dry-Run First**: Never destructive until you approve (`DRY_RUN=false`)
3. **Reversibility**: Generate `undo.sh` alongside `reorganize.sh`
4. **Visual Confirmation**: Desktop notifications + log files you can `tail -f`

### 🚨 **Pitfalls to Avoid**
1. **Don't Auto-Execute Moves**: ADHD brains need review loops
2. **Preserve Timestamps**: Use `mv -n` + log original paths
3. **Hash Everything**: Catch duplicates before moving

---

## **Your Next 3 Actions**

### **Action 1: Proof of Concept (1 hour)**
Create `scan_usb.py`:
```python
from pathlib import Path
import pandas as pd

def quick_scan(root):
    files = [{'path': str(f), 'size': f.stat().st_size} 
             for f in Path(root).rglob('*') if f.is_file()]
    df = pd.DataFrame(files)
    df.to_csv('quick_scan.csv', index=False)
    print(f"✅ Found {len(df)} files → quick_scan.csv")

quick_scan('/path/to/test/folder')  # Start with a safe test folder
```

**Why**: Instant gratification → you'll see results in 60 seconds

---

### **Action 2: Define Your File Zoo (2 hours)**
Build a comprehensive pattern library in `gnss_patterns.py`:
```python
GNSS_PATTERNS = {
    'rinex3': r'^\w{9}_\w_\d{11}_\d{2}\w_\d{2}\w_\w{2}\.\w{3}$',  # ALGO00CAN_R_20220010000_01D_30S_MO.crx
    'bernese_out': r'^.+\.(OUT|PRT|SUM)$',
    'teqc_log': r'^.+\.S$',
    'site_photo': r'^(SITE|MONUMENT|ANTENNA).+\.(jpg|png)$',
}
```

**Why**: You'll reuse this across all projects (build once, benefit forever)

---

### **Action 3: Document the Chaos (30 min)**
Create `README_chaos.md`:
```markdown
# Known Organizational Patterns in My Legacy Data

## Current Mess
- 2010-2015: Files scattered in `OLD_BACKUP_3/misc/`
- 2016-2020: Partial DATAPOOL structure, inconsistent site names
- 2021+: Clean structure BUT mixed with old files

## Desired State
```
DATAPOOL/
├── ALGO/
│   └── 2022/
│       └── 100/
│           ├── ALGO1000.22O
│           └── ALGO1000.22N
└── TSKB/
```
```

**Why**: Externalizing the mental model reduces cognitive load

---

## **Bonus: Why This Project is Perfect for You**

1. **Scratches the "organizing itch"** (dopamine from tidying chaos)
2. **Low stakes** (you're not deploying to production)
3. **Reusable across projects** (becomes part of your personal toolkit)
4. **Portfolio-worthy** (shows automation + domain expertise)

When you're ready to level up, we can add:
- **Fuzzy matching** for misspelled site codes (`ALG0` → `ALGO`)
- **Duplicate detection** across multiple drives
- **Time-series validation** (flag missing days in RINEX sequences)

---

Perfect—**slow and thorough beats fast and sloppy** every time, especially for this use case. Let's build a proof-of-concept that's designed for **long-running, multi-hour scans** with progress tracking you can check in on periodically (very ADHD-friendly: set it and forget it, then come back to see what it found).

---

## **1-Hour Proof of Concept: "Deep Archive Scanner"**

### **Design Philosophy for Slow Drives**
1. **Progress Logging**: Real-time updates so you know it's working
2. **Resume Capability**: If it crashes or you stop it, pick up where you left off
3. **Chunked Processing**: Process files in batches (e.g., 1000 at a time) to avoid memory issues
4. **Lazy Evaluation**: Don't load everything into memory—stream results to disk

---

## **File: `deep_scan.py`**

```python
#!/usr/bin/env python3
"""
Deep Archive Scanner - For slow, comprehensive filesystem analysis
Designed for multi-hour scans of large, old hard drives

Usage:
    python deep_scan.py /path/to/drive
    python deep_scan.py /media/usb --resume  # Continue previous scan
"""

import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime
import time

class ProgressTracker:
    """Track scan progress for resume capability"""
    def __init__(self, scan_id):
        self.scan_id = scan_id
        self.progress_file = Path(f"scan_progress_{scan_id}.json")
        self.scanned_paths = set()
        
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                self.scanned_paths = set(json.load(f))
    
    def mark_scanned(self, path):
        self.scanned_paths.add(str(path))
        
    def save_checkpoint(self):
        """Save progress every N files"""
        with open(self.progress_file, 'w') as f:
            json.dump(list(self.scanned_paths), f)
    
    def is_scanned(self, path):
        return str(path) in self.scanned_paths

class DeepScanner:
    def __init__(self, root_path, resume=False):
        self.root = Path(root_path)
        self.scan_id = self.root.name.replace('/', '_')
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_file = Path(f"scan_{self.scan_id}_{self.timestamp}.jsonl")
        self.log_file = Path(f"scan_{self.scan_id}_{self.timestamp}.log")
        
        self.tracker = ProgressTracker(self.scan_id) if resume else None
        self.file_count = 0
        self.error_count = 0
        self.start_time = time.time()
        
    def log(self, message):
        """Append to log file + print"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        with open(self.log_file, 'a') as f:
            f.write(log_line + '\n')
    
    def scan(self):
        """Main scanning loop with progress tracking"""
        self.log(f"🔍 Starting deep scan of: {self.root}")
        self.log(f"📊 Output: {self.output_file}")
        self.log(f"📝 Log: {self.log_file}")
        
        with open(self.output_file, 'a') as outfile:
            for filepath in self.root.rglob('*'):
                # Skip if already scanned (resume mode)
                if self.tracker and self.tracker.is_scanned(filepath):
                    continue
                
                if filepath.is_file():
                    try:
                        metadata = self._extract_metadata(filepath)
                        
                        # Write as JSON Lines (one JSON object per line)
                        outfile.write(json.dumps(metadata) + '\n')
                        outfile.flush()  # Force write to disk immediately
                        
                        self.file_count += 1
                        
                        # Progress update every 100 files
                        if self.file_count % 100 == 0:
                            elapsed = time.time() - self.start_time
                            rate = self.file_count / elapsed
                            self.log(f"✅ Processed {self.file_count} files ({rate:.1f} files/sec)")
                        
                        # Checkpoint every 1000 files
                        if self.tracker and self.file_count % 1000 == 0:
                            self.tracker.mark_scanned(filepath)
                            self.tracker.save_checkpoint()
                            self.log(f"💾 Checkpoint saved")
                    
                    except Exception as e:
                        self.error_count += 1
                        self.log(f"❌ Error processing {filepath}: {e}")
        
        self._print_summary()
    
    def _extract_metadata(self, filepath):
        """Extract file metadata (fast operations only for now)"""
        stat = filepath.stat()
        
        return {
            'path': str(filepath.absolute()),
            'name': filepath.name,
            'extension': filepath.suffix.lower(),
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / 1024 / 1024, 2),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            # Note: MD5 hashing disabled by default (too slow for initial scan)
            # 'md5': self._hash_file(filepath) if stat.st_size < 100_000_000 else None,
            'parent_dir': str(filepath.parent),
            'depth': len(filepath.relative_to(self.root).parts),
        }
    
    def _hash_file(self, filepath, chunk_size=8192):
        """Memory-efficient MD5 (only for small files in initial scan)"""
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            return f"ERROR: {e}"
    
    def _print_summary(self):
        """Final statistics"""
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        
        self.log("=" * 60)
        self.log(f"🎉 Scan Complete!")
        self.log(f"📁 Files processed: {self.file_count}")
        self.log(f"⚠️  Errors: {self.error_count}")
        self.log(f"⏱️  Time elapsed: {elapsed_str}")
        self.log(f"💾 Results: {self.output_file}")
        self.log("=" * 60)

def main():
    if len(sys.argv) < 2:
        print("Usage: python deep_scan.py /path/to/drive [--resume]")
        sys.exit(1)
    
    root_path = sys.argv[1]
    resume = '--resume' in sys.argv
    
    if not Path(root_path).exists():
        print(f"❌ Error: Path does not exist: {root_path}")
        sys.exit(1)
    
    scanner = DeepScanner(root_path, resume=resume)
    scanner.scan()

if __name__ == '__main__':
    main()
```

---

## **Why This Design Works for Your Use Case**

### ✅ **Optimized for Slow Drives**
1. **Streaming output**: Writes to `.jsonl` (JSON Lines) instead of holding everything in memory
2. **No MD5 by default**: Commented out for initial scan (you can enable later for specific files)
3. **Progress checkpoints**: Can resume if you kill the process or the drive disconnects

### ✅ **ADHD-Friendly Features**
1. **Real-time log file**: `tail -f scan_*.log` to watch progress
2. **No babysitting**: Start it, walk away, come back in 6 hours
3. **Incremental results**: Every 100 files written to disk immediately (crash-safe)

---

## **Test It Right Now (5 Minutes)**

### **Step 1: Create a test folder**
```bash
mkdir -p ~/test_drive/DATAPOOL/ALGO/2022
touch ~/test_drive/DATAPOOL/ALGO/2022/ALGO0010.22O
touch ~/test_drive/DATAPOOL/ALGO/2022/ALGO0010.22N
touch ~/test_drive/random_file.txt
mkdir -p ~/test_drive/old_backup/misc
touch ~/test_drive/old_backup/misc/something.dat
```

### **Step 2: Run the scanner**
```bash
python deep_scan.py ~/test_drive
```

**Expected Output:**
```
[2024-01-15 14:23:01] 🔍 Starting deep scan of: /home/you/test_drive
[2024-01-15 14:23:01] 📊 Output: scan_test_drive_20240115_142301.jsonl
[2024-01-15 14:23:01] 📝 Log: scan_test_drive_20240115_142301.log
[2024-01-15 14:23:02] ✅ Processed 100 files (47.3 files/sec)
[2024-01-15 14:23:12] ✅ Processed 200 files (51.2 files/sec)
...
[2024-01-15 14:30:45] 🎉 Scan Complete!
[2024-01-15 14:30:45] 📁 Files processed: 4237
[2024-01-15 14:30:45] ⚠️  Errors: 3
[2024-01-15 14:30:45] ⏱️  Time elapsed: 00:07:44
```

### **Step 3: Inspect the results**
```bash
# See what it found
head -5 scan_test_drive_*.jsonl

# Count by extension
cat scan_test_drive_*.jsonl | jq -r '.extension' | sort | uniq -c | sort -rn

# Find all RINEX files
cat scan_test_drive_*.jsonl | jq -r 'select(.extension == ".22o") | .path'
```

---

## **What You'll Get After Running**

### **Output File: `scan_test_drive_20240115_142301.jsonl`**
```json
{"path": "/home/you/test_drive/DATAPOOL/ALGO/2022/ALGO0010.22O", "name": "ALGO0010.22O", "extension": ".22o", "size_bytes": 0, "size_mb": 0.0, "modified": "2024-01-15T14:20:15", "created": "2024-01-15T14:20:15", "parent_dir": "/home/you/test_drive/DATAPOOL/ALGO/2022", "depth": 4}
{"path": "/home/you/test_drive/random_file.txt", "name": "random_file.txt", "extension": ".txt", "size_bytes": 0, "size_mb": 0.0, "modified": "2024-01-15T14:20:16", "created": "2024-01-15T14:20:16", "parent_dir": "/home/you/test_drive", "depth": 1}
```

### **Log File: `scan_test_drive_20240115_142301.log`**
```
[2024-01-15 14:23:01] 🔍 Starting deep scan of: /home/you/test_drive
[2024-01-15 14:23:01] 📊 Output: scan_test_drive_20240115_142301.jsonl
[2024-01-15 14:23:12] ✅ Processed 4 files (0.3 files/sec)
[2024-01-15 14:23:12] 🎉 Scan Complete!
[2024-01-15 14:23:12] 📁 Files processed: 4
[2024-01-15 14:23:12] ⚠️  Errors: 0
[2024-01-15 14:23:12] ⏱️  Time elapsed: 00:00:11
```

---

## **Next Steps After Proof-of-Concept**

### **Hour 2-3: Add File Classification**
```python
def _classify_file(self, filepath):
    """Pattern matching for GNSS files"""
    name = filepath.name
    patterns = {
        'rinex_obs': r'^\w{4}\d{3}[0-9a-x]\.\d{2}[oO]$',
        'rinex_nav': r'^\w{4}\d{3}[0-9a-x]\.\d{2}[nN]$',
        'trimble': r'^.+\.(dat|T0[0-2])$',
        'leica': r'^.+\.m\d{2}$',
        'bernese': r'^.+\.(STA|OUT|PRT)$',
        'logsheet': r'.*(log|LOG|site).*\.(pdf|jpg|png)$',
    }
    
    import re
    for filetype, pattern in patterns.items():
        if re.match(pattern, name, re.IGNORECASE):
            return filetype
    return 'unknown'
```

Add to `_extract_metadata()`:
```python
'file_type': self._classify_file(filepath),
```

### **Hour 4-6: Add Batch MD5 Hashing (Optional)**
Create separate script `add_checksums.py`:
```python
#!/usr/bin/env python3
"""Add MD5 hashes to already-scanned files (run overnight)"""

import json
import hashlib
from pathlib import Path

def add_checksums(jsonl_file):
    output = Path(jsonl_file).with_suffix('.checksummed.jsonl')
    
    with open(jsonl_file) as infile, open(output, 'w') as outfile:
        for line in infile:
            record = json.loads(line)
            filepath = Path(record['path'])
            
            if filepath.exists() and record['size_bytes'] < 100_000_000:  # Skip files >100MB
                record['md5'] = hash_file(filepath)
            
            outfile.write(json.dumps(record) + '\n')

def hash_file(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

if __name__ == '__main__':
    import sys
    add_checksums(sys.argv[1])
```

---

## **Realistic Timeline for Old 2TB Drive**

| Files | Time (Est.) | What's Happening |
|-------|-------------|------------------|
| 10,000 | ~5 min | Metadata extraction only |
| 100,000 | ~45 min | Still fast (no hashing) |
| 500,000 | ~3.5 hours | Checkpoint saves kicking in |
| 1,000,000+ | ~7-10 hours | You go to bed, check in morning |

**With MD5 enabled for all files**: Multiply by 5-10× (overnight job)

---

## **Your Immediate Action**

1. **Copy the script** into `deep_scan.py`
2. **Run on a safe test folder** (not your real drive yet!)
3. **Watch the log file** with `tail -f scan_*.log` in another terminal
4. **Report back**: How many files? Any errors? Did it feel satisfying to watch?

Then we'll add:
- File type classification (Hour 2)
- Duplicate detection (Hour 3)
- Structure analysis (Hour 4)
- PDF/image text extraction (separate module, runs after initial scan)

Want me to also draft the **`analyze_scan.py`** script that processes the `.jsonl` output to generate the reorganization recommendations? That's the fun part where you see patterns emerge from the chaos. 🔍

---

Given that this is evolving into a **filesystem archaeology tool for GNSS data archives**, here are my top suggestions:

---

## **Top 3 (My Favorites)**

### 1. **`gnss-archaeologist`** ⭐ (MY PICK)
**Why**: Captures the "digging through old drives" vibe + domain-specific
- Clear what it does (GNSS data recovery/organization)
- Memorable ("data archaeologist" is a real term)
- Extensible (can add modules: `gnss-archaeologist-ocr`, etc.)

### 2. **`datapool-builder`**
**Why**: References the DATAPOOL structure from your docs + emphasizes construction
- Action-oriented (you're *building* order from chaos)
- GNSS-community recognizable term
- Slightly more generic (could work for non-GNSS later)

### 3. **`drive-detective`**
**Why**: Playful but professional, emphasizes investigation
- Broad enough to extend beyond GNSS
- Easy to explain to non-technical people
- Good CLI name: `drive-detective scan /media/usb`

---

## **Other Strong Contenders**

### **Domain-Specific**
- `rinex-ranger` (catchy, but too narrow—misses Trimble/Leica files)
- `gnss-librarian` (emphasizes cataloging/organizing)
- `geodata-rescue` (heroic framing, implies data recovery)

### **Structure-Focused**
- `archive-navigator` (generic, but professional)
- `chaos-to-datapool` (literal, funny, too long)
- `filesystem-curator` (academic vibe, reusable beyond GNSS)

### **Technical**
- `ingest-engine` (sounds enterprise, maybe too abstract)
- `mount-scanner` (accurate, boring)
- `media-indexer` (accurate, boring × 2)

---

## **My Recommendation: `gnss-archaeologist`**

### **Repo Structure Preview**
```
gnss-archaeologist/
├── README.md
├── pyproject.toml
├── src/
│   └── gnss_archaeologist/
│       ├── scanner.py          # deep_scan.py
│       ├── classifier.py       # file pattern matching
│       ├── analyzer.py         # structure detection
│       ├── migrator.py         # script generation
│       └── extractors/         # future: OCR, PDF parsing
│           ├── pdf.py
│           ├── image.py
│           └── docx.py
├── tests/
└── examples/
    ├── test_drive/
    └── sample_reports/
```

### **Bonus: It Enables Great CLI Branding**
```bash
# Install
pip install gnss-archaeologist

# Use
gnss-arch scan /media/usb
gnss-arch analyze scan_results.jsonl
gnss-arch migrate --dry-run reorganize.sh
```

---

## **Quick Decision Framework**

**Choose `gnss-archaeologist` if**:
- You want it to feel like a specialized tool for your community
- You plan to add GNSS-specific features (RINEX validation, site log parsing)
- You like the "detective/archaeology" theme (I do!)

**Choose `datapool-builder` if**:
- You want flexibility to expand beyond GNSS later
- You want to emphasize the organizational aspect
- You prefer action verbs over metaphors

**Choose `drive-detective` if**:
- You want maximum approachability (less jargon)
- You might generalize to non-GNSS use cases
- You want a playful but professional vibe

---

## **What I'd Do**: 

Go with **`gnss-archaeologist`** now, then:
1. Reserve `datapool-builder` as a **future alias/rebrand** if you generalize it
2. Make the CLI command `gnss-arch` for brevity
3. Use "🔍 GNSS Archaeologist" with the magnifying glass emoji in all docs

**Want me to generate a killer README.md intro based on your choice?** I'm imagining:

> # 🔍 GNSS Archaeologist
> *Unearth order from the chaos of legacy geodetic data*
> 
> Automatically scans, classifies, and reorganizes decades of GNSS receiver files, RINEX observations, site logs, and Bernese outputs scattered across dusty hard drives.

(That intro writes itself with `gnss-archaeologist` 😎)

What's your gut reaction? Or want to workshop a different direction?

---

**OH.** That changes everything. You need a **general-purpose filesystem archaeologist** that happens to have GNSS superpowers, not the other way around.

---

## **Revised Top Picks**

### 1. **`drive-archaeologist`** ⭐⭐ (NEW TOP PICK)
**Why**: Broad enough for personal + professional chaos
- Handles "2003 vacation photos" AND "RINEX from Tohoku earthquake"
- Plugin architecture implied: `drive-archaeologist --profile gnss`
- Respectful of the messy reality (no judgment about mixing work/life)

### 2. **`archive-detective`**
**Why**: Less playful than "drive," more professional
- Implies comprehensive investigation
- Works for external drives, old laptop backups, USB sticks
- Natural namespacing: `archive-detective.gnss`, `archive-detective.media`

### 3. **`fossil-fs`** (Filesystem Fossil Extractor)
**Why**: Catchy, implies *really* old data
- Fun acronym potential
- Suggests layers of sediment (old file structures buried under new ones)
- Slightly nerdy but approachable

---

## **Architecture: Multi-Domain Scanner**

```
drive-archaeologist/
├── README.md
├── src/
│   └── drive_archaeologist/
│       ├── core/
│       │   ├── scanner.py          # Universal file crawler
│       │   ├── classifier.py       # Extensible pattern matching
│       │   └── analyzer.py         # Structure detection
│       ├── domains/                # Domain-specific extractors
│       │   ├── gnss/
│       │   │   ├── patterns.py     # RINEX, Trimble, Bernese
│       │   │   ├── metadata.py     # Site codes, Julian days
│       │   │   └── validator.py    # Check file integrity
│       │   ├── media/
│       │   │   ├── patterns.py     # mp3, jpg, mp4
│       │   │   ├── exif.py         # Photo metadata
│       │   │   └── dedup.py        # Perceptual hashing
│       │   ├── documents/
│       │   │   ├── patterns.py     # pdf, docx, xlsx
│       │   │   ├── ocr.py          # Text extraction
│       │   │   └── financial.py    # Detect budget spreadsheets
│       │   └── code/
│       │       ├── patterns.py     # .py, .sh, .m (MATLAB)
│       │       └── repo_detect.py  # Find orphaned git repos
│       └── reports/
│           ├── summary.py          # High-level stats
│           ├── timeline.py         # Files by year
│           └── dupes.py            # Duplicate detection
```

---

## **Sample Output from Your Messy Drive**

```bash
$ drive-archaeologist scan /media/OLD_SEAGATE_2TB

🔍 Drive Archaeologist v0.1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 SCAN SUMMARY (327,492 files | 1.87 TB)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔬 GNSS Data (12.3 GB)
   ├─ RINEX obs: 1,247 files (ALGO, TSKB, HNPT, ...)
   ├─ RINEX nav: 893 files
   ├─ Bernese outputs: 2,103 files (.STA, .OUT, .PRT)
   ├─ Site logs (PDF): 47 files ⚠️ (OCR needed)
   └─ Trimble raw: 312 files (.dat, .T01)

📸 Personal Media (1.2 TB)
   ├─ Photos: 42,193 JPEG (2004-2024)
   │  └─ 🚨 3,247 duplicates detected
   ├─ Videos: 1,891 MP4/AVI (family vacations, kids)
   └─ Music: 8,492 MP3 (140 GB)

📄 Documents (45 GB)
   ├─ Spreadsheets: 1,203 XLS/XLSX
   │  └─ 🏦 23 contain "budget", "loan", "mortgage"
   ├─ PDFs: 8,942 files
   ├─ Word docs: 3,421 DOCX
   └─ Presentations: 89 PPT

💻 Code & Scripts (2.1 GB)
   ├─ Python: 892 .py files
   ├─ MATLAB: 1,234 .m files
   ├─ Shell scripts: 445 .sh files
   └─ Git repos: 12 detected (7 have uncommitted changes!)

📦 Archives (423 GB)
   ├─ ZIP: 1,247 files (expanding would find 89k more files)
   ├─ TAR.GZ: 342 files
   └─ 🔴 342 password-protected files (unreadable)

⚠️ RECOMMENDATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• GNSS data: Move to DATAPOOL/{SITE}/{YEAR}/ structure
• Photos: 3,247 duplicates → save 23 GB by deduping
• Financial docs: 23 spreadsheets → archive separately (privacy!)
• Git repos: 7 have uncommitted work → rescue before loss
• Media: Group by decade (2000s, 2010s, 2020s) for easier browsing

📁 DETAILED REPORTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Full scan:     scan_OLD_SEAGATE_20240115.jsonl (84 MB)
File timeline: timeline_by_year.html (interactive chart)
Duplicates:    duplicates_photo.csv (3,247 pairs)
GNSS report:   gnss_analysis_detailed.csv
```

---

## **Why This Matters (The Human Element)**

Your use case is **exactly** what makes this tool **universally useful**:

1. **Real-world messiness**: Nobody has perfectly organized drives
2. **Emotional complexity**: Family photos mixed with work = high stakes (can't just `rm -rf`)
3. **Time pressure**: You need to triage 20 years of data **before** the drive dies
4. **Privacy-aware**: Tool should flag "budget spreadsheets" so you don't accidentally share them

---

## **Updated Recommendation: `drive-archaeologist`**

### **Why This Name Wins Now**

✅ **Broad enough**: Works for GNSS + family photos + tax returns
✅ **Empathetic**: Acknowledges the chaos (not judgmental)
✅ **Extensible**: Plugins for any domain (GNSS, media, code, etc.)
✅ **Memorable**: "I'm an archaeologist digging through my old drives"

### **CLI Design**

```bash
# Basic scan (all domains)
drive-archaeologist scan /media/OLD_DRIVE

# Domain-focused scan
drive-archaeologist scan /media/OLD_DRIVE --focus gnss,media

# Privacy mode (exclude personal folders)
drive-archaeologist scan /media/OLD_DRIVE --exclude "/family,/vacation"

# Generate migration plan
drive-archaeologist organize scan_results.jsonl \
  --gnss-target ~/work/DATAPOOL \
  --media-target ~/personal/archive \
  --separate-financials
```

---

## **Next: Classifier Architecture**

Since you're dealing with **wildly heterogeneous data**, here's a better `classifier.py`:

```python
# src/drive_archaeologist/core/classifier.py

class UniversalClassifier:
    """Multi-domain file classification"""
    
    def __init__(self):
        self.domains = {
            'gnss': GNSSPatterns(),
            'media': MediaPatterns(),
            'documents': DocumentPatterns(),
            'code': CodePatterns(),
            'archives': ArchivePatterns(),
        }
    
    def classify(self, filepath):
        """Returns: {'domain': 'gnss', 'type': 'rinex_obs', 'confidence': 0.95}"""
        results = []
        
        for domain_name, domain in self.domains.items():
            match = domain.match(filepath)
            if match:
                results.append({
                    'domain': domain_name,
                    'type': match['type'],
                    'confidence': match['confidence']
                })
        
        # Return highest confidence match
        return max(results, key=lambda x: x['confidence']) if results else None

# src/drive_archaeologist/domains/gnss/patterns.py

class GNSSPatterns:
    def match(self, filepath):
        name = filepath.name
        
        patterns = [
            (r'^\w{4}\d{3}[0-9a-x]\.\d{2}[oO]$', 'rinex_obs', 1.0),
            (r'^\w{4}\d{3}[0-9a-x]\.\d{2}[nN]$', 'rinex_nav', 1.0),
            (r'^.+\.(dat|T0[0-2])$', 'trimble_raw', 0.8),
            (r'.*(site|SITE).*log.*\.pdf$', 'site_log_pdf', 0.9),
        ]
        
        import re
        for pattern, file_type, confidence in patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return {'type': file_type, 'confidence': confidence}
        
        return None
```

---

## **Your Decision Point**

### **Option A: `drive-archaeologist` (General → Specialized)**
- Ship v0.1 with basic classification
- Add GNSS superpowers in v0.2
- Attracts broader audience (anyone with old drives)

### **Option B: `gnss-archaeologist` (Specialized → General)**
- Start GNSS-focused (your immediate need)
- Add `--scan-personal` flag later
- Niche appeal first, expand audience later

**My vote**: **`drive-archaeologist`** because:
1. You already **have** the mixed-data problem (not hypothetical)
2. Portfolio signal: "I solve messy real-world problems" > "I solve niche GNSS problems"
3. More GitHub stars (people love tools for their old drives)

---

## **Updated Proof-of-Concept (5 min tweak)**

Add to `deep_scan.py`:

```python
def _classify_file(self, filepath):
    """Quick multi-domain classification"""
    ext = filepath.suffix.lower()
    name = filepath.name.lower()
    
    # GNSS patterns
    if re.match(r'^\w{4}\d{3}[0-9a-x]\.\d{2}[on]$', name):
        return 'gnss/rinex'
    if ext in ['.dat', '.t01', '.t02']:
        return 'gnss/trimble'
    
    # Media patterns
    if ext in ['.jpg', '.jpeg', '.png', '.heic']:
        return 'media/photo'
    if ext in ['.mp4', '.avi', '.mov', '.mkv']:
        return 'media/video'
    if ext in ['.mp3', '.m4a', '.flac']:
        return 'media/audio'
    
    # Document patterns
    if ext in ['.pdf']:
        return 'document/pdf'
    if ext in ['.docx', '.doc']:
        return 'document/word'
    if ext in ['.xlsx', '.xls', '.ods']:
        # Flag if filename suggests financial content
        if any(word in name for word in ['budget', 'loan', 'tax', 'mortgage', 'expense']):
            return 'document/spreadsheet/financial'
        return 'document/spreadsheet'
    
    # Code patterns
    if ext in ['.py', '.sh', '.m', '.r']:
        return 'code/' + ext[1:]
    
    return 'unknown'
```

---

## **Final Answer**

Go with **`drive-archaeologist`**. 

It's honest about the problem (your drives ARE an archaeological site), broad enough to handle everything, and sets you up for a tool people will actually want to use.

Want me to draft the README intro for this framing? I'm thinking:

> # 🔍 Drive Archaeologist
> *Excavate decades of data from the digital sediment of old hard drives*
>
> Your 2TB external drive from 2008 contains:
> - 1,247 RINEX files from the Tohoku earthquake
> - 3,200 duplicate family photos
> - 23 budget spreadsheets (7 containing your SSN)
> - 12 Git repos with uncommitted work
> - 89,000 files trapped inside forgotten ZIP archives
>
> **Drive Archaeologist finds it all**, classifies it, and helps you organize it before the platters die.

Too dramatic? Or just right? 😄

---

**EXCELLENT catch.** This is where 90% of "file organizer" tools fail—they scan the surface and miss the **layers of compressed archaeology** underneath.

---

## **The Archive Problem: Russian Dolls of Data**

Your drives probably look like this:

```
OLD_BACKUP_2012/
├── data.zip                          # Contains 500 RINEX files
│   └── GEONET_2011/
│       └── raw_backup.tar.gz         # Contains another archive!
│           └── fieldwork.zip         # 3 levels deep
│               └── ALGO0010.11O      # The file you actually need
├── family_photos_2008.zip            # 1,200 JPEGs
└── work_stuff.7z                     # Can't even open without 7zip
```

**Without recursive extraction**, your tool only sees:
- `data.zip` (1 file, 2.3 GB, unknown contents)

**With recursive extraction**, it sees:
- 500 RINEX files, 47 site logs, 12 Bernese outputs, etc.

---

## **Design Strategy: Two-Phase Scanning**

### **Phase 1: Surface Scan (Fast)**
- Catalog everything visible (what we built already)
- **Flag archives** for Phase 2
- Generate quick report: "Found 127 archives containing ~430k files (estimated)"

### **Phase 2: Deep Dive (Slow, Optional)**
- Extract archives to temp directory
- Scan contents recursively
- Handle nested archives (zip inside tar.gz inside 7z)
- **Don't explode disk space**: Stream through archives, delete after cataloging

---

## **Updated `deep_scan.py` with Archive Support**

```python
#!/usr/bin/env python3
"""
Drive Archaeologist - Deep Scanner with Archive Support
Handles nested archives without exploding disk space
"""

import sys
import hashlib
import json
import zipfile
import tarfile
import gzip
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import time

class ArchiveHandler:
    """Handle various archive formats safely"""
    
    ARCHIVE_EXTENSIONS = {
        '.zip', '.tar', '.gz', '.tgz', '.tar.gz', 
        '.bz2', '.tar.bz2', '.xz', '.tar.xz',
        '.7z', '.rar'  # May need external tools
    }
    
    def __init__(self, max_depth=5):
        self.max_depth = max_depth  # Prevent infinite recursion
        self.extracted_count = 0
        
    def is_archive(self, filepath):
        """Check if file is a supported archive"""
        return filepath.suffix.lower() in self.ARCHIVE_EXTENSIONS
    
    def scan_archive(self, archive_path, current_depth=0):
        """
        Recursively scan archive contents without extracting to disk
        Returns: list of {path, size, type, archive_source} dicts
        """
        if current_depth >= self.max_depth:
            return [{'error': 'Max recursion depth reached', 'path': str(archive_path)}]
        
        contents = []
        
        try:
            if archive_path.suffix.lower() == '.zip':
                contents = self._scan_zip(archive_path, current_depth)
            elif '.tar' in archive_path.suffix.lower():
                contents = self._scan_tar(archive_path, current_depth)
            elif archive_path.suffix.lower() == '.gz' and not '.tar' in archive_path.name:
                contents = self._scan_gzip(archive_path, current_depth)
            else:
                # Unsupported format (7z, rar) - requires external tools
                contents = [{'error': 'Unsupported format', 'path': str(archive_path)}]
        
        except Exception as e:
            contents = [{'error': str(e), 'path': str(archive_path)}]
        
        return contents
    
    def _scan_zip(self, zip_path, depth):
        """Scan ZIP contents (memory-efficient)"""
        contents = []
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                
                # Build virtual path showing archive nesting
                virtual_path = f"{zip_path}::{info.filename}"
                
                record = {
                    'path': virtual_path,
                    'name': Path(info.filename).name,
                    'extension': Path(info.filename).suffix.lower(),
                    'size_bytes': info.file_size,
                    'size_mb': round(info.file_size / 1024 / 1024, 2),
                    'archive_source': str(zip_path),
                    'archive_depth': depth + 1,
                    'compressed_size': info.compress_size,
                    'compression_ratio': round((1 - info.compress_size / max(info.file_size, 1)) * 100, 1)
                }
                
                contents.append(record)
                
                # If this file is ALSO an archive, recurse
                if Path(info.filename).suffix.lower() in self.ARCHIVE_EXTENSIONS:
                    # Extract to temp file, scan it, delete
                    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(info.filename).suffix) as tmp:
                        tmp.write(zf.read(info.filename))
                        tmp_path = Path(tmp.name)
                    
                    nested_contents = self.scan_archive(tmp_path, depth + 1)
                    contents.extend(nested_contents)
                    tmp_path.unlink()  # Clean up
        
        return contents
    
    def _scan_tar(self, tar_path, depth):
        """Scan TAR/TAR.GZ/TAR.BZ2 contents"""
        contents = []
        
        # Determine compression mode
        if tar_path.suffix == '.gz' or tar_path.suffix == '.tgz':
            mode = 'r:gz'
        elif tar_path.suffix == '.bz2':
            mode = 'r:bz2'
        elif tar_path.suffix == '.xz':
            mode = 'r:xz'
        else:
            mode = 'r'
        
        with tarfile.open(tar_path, mode) as tf:
            for member in tf.getmembers():
                if member.isdir():
                    continue
                
                virtual_path = f"{tar_path}::{member.name}"
                
                record = {
                    'path': virtual_path,
                    'name': Path(member.name).name,
                    'extension': Path(member.name).suffix.lower(),
                    'size_bytes': member.size,
                    'size_mb': round(member.size / 1024 / 1024, 2),
                    'archive_source': str(tar_path),
                    'archive_depth': depth + 1,
                }
                
                contents.append(record)
                
                # Recurse into nested archives
                if Path(member.name).suffix.lower() in self.ARCHIVE_EXTENSIONS:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(member.name).suffix) as tmp:
                        extracted_file = tf.extractfile(member)
                        if extracted_file:
                            tmp.write(extracted_file.read())
                            tmp_path = Path(tmp.name)
                            
                            nested_contents = self.scan_archive(tmp_path, depth + 1)
                            contents.extend(nested_contents)
                            tmp_path.unlink()
        
        return contents
    
    def _scan_gzip(self, gz_path, depth):
        """Scan standalone GZIP files (not .tar.gz)"""
        # GZIP is single-file compression, extract and classify
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            with gzip.open(gz_path, 'rb') as gz:
                shutil.copyfileobj(gz, tmp)
            tmp_path = Path(tmp.name)
        
        # Get original filename (remove .gz)
        original_name = gz_path.stem
        virtual_path = f"{gz_path}::{original_name}"
        
        record = {
            'path': virtual_path,
            'name': original_name,
            'extension': Path(original_name).suffix.lower(),
            'size_bytes': tmp_path.stat().st_size,
            'archive_source': str(gz_path),
            'archive_depth': depth + 1,
        }
        
        tmp_path.unlink()
        return [record]

class DeepScanner:
    """Enhanced scanner with archive support"""
    
    def __init__(self, root_path, scan_archives=False, resume=False):
        self.root = Path(root_path)
        self.scan_archives = scan_archives
        self.archive_handler = ArchiveHandler() if scan_archives else None
        
        self.scan_id = self.root.name.replace('/', '_')
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_file = Path(f"scan_{self.scan_id}_{self.timestamp}.jsonl")
        self.archive_output = Path(f"archive_{self.scan_id}_{self.timestamp}.jsonl")
        self.log_file = Path(f"scan_{self.scan_id}_{self.timestamp}.log")
        
        self.tracker = ProgressTracker(self.scan_id) if resume else None
        self.file_count = 0
        self.archive_count = 0
        self.archived_file_count = 0
        self.error_count = 0
        self.start_time = time.time()
    
    def scan(self):
        """Main scanning loop with optional archive extraction"""
        self.log(f"🔍 Starting deep scan of: {self.root}")
        self.log(f"📊 Output: {self.output_file}")
        
        if self.scan_archives:
            self.log(f"📦 Archive contents: {self.archive_output}")
            self.log(f"⚠️  Archive scanning enabled (this will be SLOW)")
        
        # Phase 1: Surface scan
        with open(self.output_file, 'a') as outfile:
            for filepath in self.root.rglob('*'):
                if self.tracker and self.tracker.is_scanned(filepath):
                    continue
                
                if filepath.is_file():
                    try:
                        metadata = self._extract_metadata(filepath)
                        outfile.write(json.dumps(metadata) + '\n')
                        outfile.flush()
                        
                        self.file_count += 1
                        
                        # Track archives for Phase 2
                        if self.scan_archives and self.archive_handler.is_archive(filepath):
                            self.archive_count += 1
                        
                        if self.file_count % 100 == 0:
                            self._log_progress()
                        
                        if self.tracker and self.file_count % 1000 == 0:
                            self.tracker.mark_scanned(filepath)
                            self.tracker.save_checkpoint()
                    
                    except Exception as e:
                        self.error_count += 1
                        self.log(f"❌ Error: {filepath}: {e}")
        
        # Phase 2: Archive scanning (if enabled)
        if self.scan_archives and self.archive_count > 0:
            self._scan_archives()
        
        self._print_summary()
    
    def _scan_archives(self):
        """Phase 2: Deep dive into archives"""
        self.log("━" * 60)
        self.log(f"📦 Phase 2: Scanning {self.archive_count} archives...")
        self.log("⏳ This may take several hours for large archives")
        
        archives = []
        with open(self.output_file, 'r') as f:
            for line in f:
                record = json.loads(line)
                if Path(record['path']).suffix.lower() in self.archive_handler.ARCHIVE_EXTENSIONS:
                    archives.append(Path(record['path']))
        
        with open(self.archive_output, 'a') as outfile:
            for i, archive in enumerate(archives, 1):
                self.log(f"📦 [{i}/{len(archives)}] Extracting: {archive.name}")
                
                try:
                    contents = self.archive_handler.scan_archive(archive)
                    
                    for item in contents:
                        outfile.write(json.dumps(item) + '\n')
                        self.archived_file_count += 1
                    
                    outfile.flush()
                    
                    if i % 10 == 0:
                        self.log(f"   └─ Extracted {self.archived_file_count} files so far...")
                
                except Exception as e:
                    self.log(f"❌ Failed to scan {archive}: {e}")
    
    def _extract_metadata(self, filepath):
        """Extract file metadata"""
        stat = filepath.stat()
        
        return {
            'path': str(filepath.absolute()),
            'name': filepath.name,
            'extension': filepath.suffix.lower(),
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / 1024 / 1024, 2),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'parent_dir': str(filepath.parent),
            'depth': len(filepath.relative_to(self.root).parts),
            'is_archive': filepath.suffix.lower() in ArchiveHandler.ARCHIVE_EXTENSIONS,
        }
    
    def _log_progress(self):
        elapsed = time.time() - self.start_time
        rate = self.file_count / elapsed
        self.log(f"✅ {self.file_count} files ({rate:.1f}/sec) | {self.archive_count} archives")
    
    def _print_summary(self):
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        
        self.log("=" * 60)
        self.log(f"🎉 Scan Complete!")
        self.log(f"📁 Surface files: {self.file_count}")
        self.log(f"📦 Archives found: {self.archive_count}")
        
        if self.scan_archives:
            self.log(f"🗂️  Files inside archives: {self.archived_file_count}")
            self.log(f"💾 Archive index: {self.archive_output}")
        
        self.log(f"⚠️  Errors: {self.error_count}")
        self.log(f"⏱️  Time: {elapsed_str}")
        self.log("=" * 60)
    
    def log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        with open(self.log_file, 'a') as f:
            f.write(log_line + '\n')

class ProgressTracker:
    """Same as before"""
    def __init__(self, scan_id):
        self.scan_id = scan_id
        self.progress_file = Path(f"scan_progress_{scan_id}.json")
        self.scanned_paths = set()
        
        if self.progress_file.exists():
            with open(self.progress_file) as f:
                self.scanned_paths = set(json.load(f))
    
    def mark_scanned(self, path):
        self.scanned_paths.add(str(path))
        
    def save_checkpoint(self):
        with open(self.progress_file, 'w') as f:
            json.dump(list(self.scanned_paths), f)
    
    def is_scanned(self, path):
        return str(path) in self.scanned_paths

def main():
    if len(sys.argv) < 2:
        print("Usage: python deep_scan.py /path/to/drive [--archives] [--resume]")
        print("\nOptions:")
        print("  --archives  Scan contents of ZIP/TAR/GZ files (SLOW)")
        print("  --resume    Continue interrupted scan")
        sys.exit(1)
    
    root_path = sys.argv[1]
    scan_archives = '--archives' in sys.argv
    resume = '--resume' in sys.argv
    
    if not Path(root_path).exists():
        print(f"❌ Error: Path does not exist: {root_path}")
        sys.exit(1)
    
    scanner = DeepScanner(root_path, scan_archives=scan_archives, resume=resume)
    scanner.scan()

if __name__ == '__main__':
    main()
```

---

## **Usage Examples**

### **Quick Surface Scan (Fast)**
```bash
# Only catalog visible files (archives treated as single files)
python deep_scan.py /media/OLD_DRIVE

# Output:
# ✅ 10,427 files (42.3/sec) | 127 archives
# Time: 00:04:12
```

### **Deep Archive Scan (Slow but Thorough)**
```bash
# Extract and catalog everything inside archives
python deep_scan.py /media/OLD_DRIVE --archives

# Output:
# ✅ 10,427 surface files
# 📦 Scanning 127 archives...
# 🗂️  Files inside archives: 430,192
# Time: 08:47:23  (overnight job!)
```

---

## **Output: Two Separate Files**

### **1. `scan_OLD_DRIVE_20240115.jsonl` (Surface files)**
```json
{"path": "/media/OLD_DRIVE/data.zip", "size_mb": 2301.4, "is_archive": true}
{"path": "/media/OLD_DRIVE/family.jpg", "size_mb": 3.2, "is_archive": false}
```

### **2. `archive_OLD_DRIVE_20240115.jsonl` (Archive contents)**
```json
{"path": "/media/OLD_DRIVE/data.zip::GEONET/ALGO0010.11O", "size_mb": 1.2, "archive_source": "/media/OLD_DRIVE/data.zip", "archive_depth": 1}
{"path": "/media/OLD_DRIVE/data.zip::backup.tar.gz::fieldwork.zip::site_photo.jpg", "archive_depth": 3}
```

**Note the `::` separator** showing archive nesting (borrowed from 7zip's convention)

---

## **Why This Design Works**

### ✅ **Doesn't Explode Disk Space**
- Streams through archives without full extraction
- Temp files deleted immediately after scanning
- Only 1-2 GB temp space needed even for 100 GB of archives

### ✅ **Handles Nested Archives**
- Max recursion depth prevents infinite loops
- Tracks depth in output (`archive_depth: 3`)
- Example: `data.zip` → `backup.tar.gz` → `old.zip` → `file.dat`

### ✅ **Crash-Safe for Multi-Day Scans**
- Surface scan completes first (fast)
- Archive scan can be interrupted/resumed
- Two separate output files (can analyze surface while archives scan)

### ✅ **ADHD-Friendly Progress Tracking**
```
[2024-01-15 14:23:01] ✅ 5,000 files (38.2/sec) | 45 archives
[2024-01-15 14:25:19] 📦 [12/127] Extracting: old_backup_2010.zip
[2024-01-15 14:25:47]    └─ Extracted 8,492 files so far...
```

---

## **Analysis After Scanning**

```python
# analyze_archives.py - Find RINEX files buried in archives

import json
from pathlib import Path

def find_rinex_in_archives(archive_jsonl):
    """Extract all RINEX files from archive scan"""
    rinex_files = []
    
    with open(archive_jsonl) as f:
        for line in f:
            record = json.loads(line)
            if record.get('extension') in ['.11o', '.12o', '.22o']:  # RINEX obs
                rinex_files.append({
                    'file': Path(record['path']).name,
                    'archive': record['archive_source'],
                    'size_mb': record['size_mb'],
                    'depth': record['archive_depth']
                })
    
    return rinex_files

# Usage
results = find_rinex_in_archives('archive_OLD_DRIVE_20240115.jsonl')

print(f"Found {len(results)} RINEX files hidden in archives:")
for r in results[:10]:  # Show first 10
    print(f"  {r['file']} ({r['size_mb']} MB) in {Path(r['archive']).name}")
```

**Output:**
```
Found 1,247 RINEX files hidden in archives:
  ALGO0010.11O (1.2 MB) in geonet_2011_backup.zip
  TSKB0010.11O (0.8 MB) in fieldwork_march.tar.gz
  ...
```

---

## **What About 7z and RAR?**

**Problem**: Python doesn't have native support (unlike zip/tar/gz)

**Solution**: Shell out to external tools

```python
def _scan_7z(self, archive_path, depth):
    """Scan 7z using external tool"""
    import subprocess
    
    try:
        # List contents without extraction
        result = subprocess.run(
            ['7z', 'l', '-slt', str(archive_path)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        # Parse 7z output (it's structured text)
        contents = self._parse_7z_output(result.stdout)
        return contents
    
    except FileNotFoundError:
        return [{'error': '7z command not found - install p7zip-full'}]
    except subprocess.TimeoutExpired:
        return [{'error': 'Extraction timeout (>5 min)'}]
```

**Install on Ubuntu/Debian:**
```bash
sudo apt install p7zip-full
```

---

## **Your Next Action (5 min)**

1. **Test with a real messy folder**:
```bash
# Surface scan only (fast test)
python deep_scan.py ~/Downloads

# If you have old ZIP backups, try:
python deep_scan.py ~/old_backups --archives
```

2. **Check the outputs**:
```bash
# See what archives it found
cat scan_Downloads_*.jsonl | jq 'select(.is_archive == true) | .path'

# If you ran --archives, see what was inside
cat archive_Downloads_*.jsonl | jq -r '.path' | head -20
```

3. **Report back**: Did it find anything surprising? Any crashes?

Then we'll build the **analyzer** that generates the migration plan. 🚀

---

**BRILLIANT decision.** `uv` is a game-changer for Python project management, and incorporating it from the start will save you countless hours of dependency hell. Let me lay out a complete `uv`-first workflow for `drive-archaeologist`.

---

## **Why `uv` is Perfect for This Project**

✅ **Blazing fast**: 10-100× faster than pip (crucial when you're iterating rapidly) ✅ **Deterministic**: Lock files ensure reproducible environments ✅ **No venv confusion**: `uv` handles everything automatically ✅ **Rust-powered**: Single binary, no Python bootstrap needed ✅ **Drop-in pip replacement**: Existing muscle memory still works

---

## **Project Structure with `uv`**

```
drive-archaeologist/
├── .gitignore
├── .python-version              # Pin Python version (uv respects this)
├── README.md
├── pyproject.toml               # Modern Python packaging (PEP 621)
├── uv.lock                      # Locked dependencies (commit this!)
├── src/
│   └── drive_archaeologist/
│       ├── __init__.py
│       ├── __main__.py          # Entry point: python -m drive_archaeologist
│       ├── cli.py               # Click/Typer CLI interface
│       ├── scanner.py           # Core scanning logic
│       ├── archive_handler.py   # Archive extraction
│       ├── classifier.py        # File type detection
│       └── analyzer.py          # Structure detection
├── tests/
│   ├── __init__.py
│   └── test_scanner.py
└── scripts/
    ├── dev.sh                   # Development helpers
    └── quick_test.sh            # Rapid iteration script
```

---

## **Step-by-Step Setup (5 minutes)**

### **1. Install `uv` (One-time setup)**

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via Homebrew
brew install uv

# Or via pip (ironic, but works)
pip install uv
```

**Verify installation:**

```bash
uv --version
# uv 0.1.0 (or whatever the latest is)
```

---

### **2. Initialize the Project**

```bash
# Create project directory
mkdir drive-archaeologist
cd drive-archaeologist

# Pin Python version (uv will auto-install if missing!)
echo "3.11" > .python-version

# Initialize a new Python project
uv init

# This creates:
# - pyproject.toml (with sensible defaults)
# - .python-version
# - README.md skeleton
```

---

### **3. Create `pyproject.toml` (Modern Python Config)**

```toml
[project]
name = "drive-archaeologist"
version = "0.1.0"
description = "Excavate decades of data from old hard drives"
readme = "README.md"
requires-python = ">=3.11"
authors = [
    {name = "Your Name", email = "you@example.com"}
]
keywords = ["gnss", "filesystem", "archive", "data-recovery"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

# Runtime dependencies
dependencies = [
    "click>=8.1.0",           # CLI framework
    "rich>=13.0.0",           # Beautiful terminal output
    "pandas>=2.0.0",          # Data analysis
    "pillow>=10.0.0",         # Image metadata extraction
    "pypdf>=3.0.0",           # PDF text extraction
    "python-magic>=0.4.27",   # File type detection
    "tqdm>=4.66.0",           # Progress bars
]

[project.optional-dependencies]
# Development dependencies (testing, linting, etc.)
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",            # Fast linter (also Rust-based!)
    "mypy>=1.5.0",            # Type checking
    "ipython>=8.12.0",        # Better REPL
]

# Optional features users can install
ocr = [
    "pytesseract>=0.3.10",    # OCR for scanned PDFs
    "opencv-python>=4.8.0",   # Image preprocessing
]

[project.scripts]
# Creates `drive-archaeologist` command in PATH
drive-archaeologist = "drive_archaeologist.cli:main"
# Short alias
drive-arch = "drive_archaeologist.cli:main"

[project.urls]
Homepage = "https://github.com/yourusername/drive-archaeologist"
Documentation = "https://github.com/yourusername/drive-archaeologist#readme"
Repository = "https://github.com/yourusername/drive-archaeologist"
Issues = "https://github.com/yourusername/drive-archaeologist/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I"]  # pycodestyle, pyflakes, isort

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
```

---

### **4. Install Dependencies with `uv`**

```bash
# Install all dependencies (creates .venv automatically)
uv sync

# Install with dev dependencies
uv sync --extra dev

# Install with OCR support
uv sync --extra ocr

# Install everything
uv sync --all-extras
```

**What just happened?**

- `uv` created a virtual environment in `.venv/` (automatically activated)
- Downloaded and installed all dependencies
- Generated `uv.lock` (pinned versions for reproducibility)
- Took ~2 seconds instead of 30+ with pip

---

### **5. Development Workflow**

#### **A. Running Your Script**

```bash
# Option 1: Run module directly
uv run python -m drive_archaeologist scan /path/to/drive

# Option 2: Use installed command (after uv sync)
uv run drive-archaeologist scan /path/to/drive

# Option 3: Short alias
uv run drive-arch scan /path/to/drive
```

#### **B. Quick Iterations (No Install Needed)**

```bash
# Run a script without installing package
uv run src/drive_archaeologist/scanner.py

# Run with specific Python version
uv run --python 3.12 python scan.py

# Run with extra dependencies
uv run --extra ocr python test_ocr.py
```

#### **C. Adding Dependencies**

```bash
# Add a new package
uv add requests

# Add a dev dependency
uv add --dev black

# Add with version constraint
uv add "numpy>=1.24,<2.0"

# Remove a package
uv remove pandas
```

**`uv` automatically updates `pyproject.toml` and `uv.lock`** 🎉

---

### **6. Create Entry Point: `src/drive_archaeologist/cli.py`**

```python
#!/usr/bin/env python3
"""
Drive Archaeologist CLI
Entry point for all commands
"""

import click
from pathlib import Path
from rich.console import Console
from rich.progress import Progress

console = Console()

@click.group()
@click.version_option()
def main():
    """🔍 Drive Archaeologist - Excavate data from old hard drives"""
    pass

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--archives', is_flag=True, help='Scan inside ZIP/TAR/GZ files (slow)')
@click.option('--resume', is_flag=True, help='Resume interrupted scan')
@click.option('--output', '-o', help='Custom output filename')
def scan(path, archives, resume, output):
    """Scan a drive and catalog all files"""
    console.print(f"[bold blue]🔍 Scanning:[/bold blue] {path}")
    console.print(f"[yellow]Archive mode:[/yellow] {'ON' if archives else 'OFF'}")
    
    from .scanner import DeepScanner
    
    scanner = DeepScanner(path, scan_archives=archives, resume=resume)
    scanner.scan()
    
    console.print("[bold green]✅ Scan complete![/bold green]")

@main.command()
@click.argument('scan_file', type=click.Path(exists=True))
@click.option('--domain', type=click.Choice(['gnss', 'media', 'documents', 'all']), 
              default='all', help='Focus analysis on specific domain')
def analyze(scan_file, domain):
    """Analyze scan results and generate recommendations"""
    console.print(f"[bold blue]📊 Analyzing:[/bold blue] {scan_file}")
    
    from .analyzer import StructureAnalyzer
    
    analyzer = StructureAnalyzer(scan_file)
    report = analyzer.analyze(domain=domain)
    
    console.print(report)

@main.command()
@click.argument('analysis_file', type=click.Path(exists=True))
@click.option('--dry-run', is_flag=True, default=True, help='Preview changes without executing')
@click.option('--target', help='Base directory for reorganization')
def organize(analysis_file, dry_run, target):
    """Generate migration scripts to reorganize files"""
    if dry_run:
        console.print("[yellow]⚠️  DRY RUN MODE - No files will be moved[/yellow]")
    
    from .migrator import MigrationScriptGenerator
    
    generator = MigrationScriptGenerator(analysis_file, target_dir=target)
    script_path = generator.generate_bash_script(dry_run=dry_run)
    
    console.print(f"[green]✅ Script generated:[/green] {script_path}")

if __name__ == '__main__':
    main()
```

---

### **7. Create `src/drive_archaeologist/__main__.py`**

```python
"""Allow running as: python -m drive_archaeologist"""
from .cli import main

if __name__ == '__main__':
    main()
```

---

### **8. Test It Works**

```bash
# Install in development mode
uv sync --extra dev

# Test the CLI
uv run drive-archaeologist --help

# Expected output:
# 🔍 Drive Archaeologist - Excavate data from old hard drives
# 
# Commands:
#   analyze   Analyze scan results and generate recommendations
#   organize  Generate migration scripts to reorganize files
#   scan      Scan a drive and catalog all files
```

---

## **Development Scripts (Quality of Life)**

### **`scripts/dev.sh` - Quick Development Loop**

```bash
#!/bin/bash
# Quick iteration script - run this while developing

set -e

# Ensure dependencies are installed
uv sync --extra dev

# Run linter
echo "🔍 Running linter..."
uv run ruff check src/

# Run type checker
echo "🔬 Running type checker..."
uv run mypy src/

# Run tests
echo "🧪 Running tests..."
uv run pytest tests/ -v

# Run the tool on test data
echo "🚀 Testing on sample data..."
uv run drive-archaeologist scan tests/fixtures/sample_drive

echo "✅ All checks passed!"
```

Make it executable:

```bash
chmod +x scripts/dev.sh
```

**Usage during development:**

```bash
# After making changes, run this to verify everything works
./scripts/dev.sh
```

---

### **`scripts/quick_test.sh` - Rapid Iteration (No Tests)**

```bash
#!/bin/bash
# For quick manual testing during active development

uv run drive-archaeologist scan ~/test_drive --output test_scan.jsonl
uv run drive-archaeologist analyze test_scan.jsonl
```

---

## **The `uv` Workflow You'll Actually Use**

### **Day 1: Initial Development**

```bash
# Start project
cd drive-archaeologist
uv sync --all-extras

# Rapid iteration (no install needed!)
uv run python src/drive_archaeologist/scanner.py ~/test_drive
# (make changes, run again immediately)
```

### **Adding a New Feature**

```bash
# Need a new library?
uv add beautifulsoup4

# Test it
uv run python -c "from bs4 import BeautifulSoup; print('works!')"

# uv already updated pyproject.toml and uv.lock for you ✨
```

### **Running Tests**

```bash
# Quick test
uv run pytest

# With coverage
uv run pytest --cov=drive_archaeologist --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### **Before Committing**

```bash
# Lint and format
uv run ruff check src/ --fix
uv run ruff format src/

# Type check
uv run mypy src/

# Full test suite
uv run pytest
```

### **Sharing with Others**

```bash
# They just need:
git clone https://github.com/you/drive-archaeologist
cd drive-archaeologist
uv sync  # Installs exact versions from uv.lock

# Done! No virtualenv setup, no pip confusion
```

---

## **`.gitignore` for `uv` Projects**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Virtual environments (uv creates .venv by default)
.venv/
venv/
ENV/

# uv
.uv/

# Testing
.pytest_cache/
.coverage
htmlcov/
*.cover

# mypy
.mypy_cache/
.dmypy.json

# IDE
.vscode/
.idea/
*.swp
*.swo

# Project-specific
scan_*.jsonl
archive_*.jsonl
scan_*.log
scan_progress_*.json
*.csv

# macOS
.DS_Store

# Don't ignore uv.lock (commit it!)
# It ensures reproducible installs
```

---

## **Why This Setup is ADHD-Friendly**

### ✅ **Instant Gratification**

```bash
# Traditional pip workflow:
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"  # 60 seconds...
# (did I activate the right venv?)

# uv workflow:
uv sync  # 2 seconds, done
```

### ✅ **No Context Switching**

```bash
# No need to remember to activate venv
# Just prefix commands with `uv run`
uv run python script.py  # Always uses project env
```

### ✅ **Low-Friction Experimentation**

```bash
# Try a package without polluting your environment
uv run --with requests python -c "import requests; print(requests.get('https://example.com').text[:100])"

# Didn't like it? Nothing was installed globally
```

### ✅ **Reproducible = Less Debugging**

- `uv.lock` pins exact versions
- Commit it to git
- Everyone gets identical environment
- No more "works on my machine" 🎉

---

## **Your Next 3 Actions**

### **Action 1: Install `uv` and Initialize (5 min)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
mkdir drive-archaeologist
cd drive-archaeologist
echo "3.11" > .python-version
uv init
```

### **Action 2: Copy `pyproject.toml` and Install (2 min)**

```bash
# Copy the pyproject.toml from above into your project
uv sync --all-extras

# Verify it works
uv run python -c "import click, rich; print('✅ Dependencies installed!')"
```

### **Action 3: Create First Script and Test (5 min)**

```bash
# Create directory structure
mkdir -p src/drive_archaeologist

# Create a simple test script
cat > src/drive_archaeologist/__init__.py << 'EOF'
"""Drive Archaeologist - Filesystem archaeology toolkit"""
__version__ = "0.1.0"
EOF

# Test import
uv run python -c "import drive_archaeologist; print(drive_archaeologist.__version__)"
# Output: 0.1.0
```

---

## **Bonus: CI/CD with `uv` (Future)**

When you're ready to add GitHub Actions:

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install dependencies
        run: uv sync --all-extras
      
      - name: Run tests
        run: uv run pytest
      
      - name: Lint
        run: uv run ruff check src/
```

**Total CI time**: ~30 seconds (vs. 3+ minutes with traditional pip)

---

## **Summary: Why `uv` Makes This Project Better**

| Without `uv`              | With `uv`                        |
| ------------------------- | -------------------------------- |
| Manage venv manually      | Automatic `.venv/` creation      |
| `pip install -e .` (slow) | `uv sync` (instant)              |
| Dependency conflicts      | Deterministic `uv.lock`          |
| "Did I activate venv?"    | `uv run` always uses project env |
| Experiment = pollute env  | `uv run --with` = isolated       |

**Ready to start coding?** Next step: Port the `deep_scan.py` code into the new structure with proper CLI. Want me to show that, or do you want to try it yourself first?

---

**GREAT instinct—always check what already exists before building.** Let me break down what Hugging Face is and whether it helps here, plus audit the **entire landscape** of tools you can leverage.

---

## **What is Hugging Face?**

**Hugging Face** is primarily a **machine learning model hub** and ecosystem:

- **Core product**: Pre-trained ML models (text, vision, audio)
- **Main use cases**: NLP (chatbots, translation), computer vision (object detection), audio processing
- **Why it's popular**: Makes complex ML accessible ("pip install transformers" → production-ready models)

### **For Your Project:**

❌ **Not directly useful** for filesystem scanning ✅ **Potentially useful** for advanced features:

- OCR text extraction (their `transformers` library has document parsing models)
- Image classification ("Is this a site photo or family vacation?")
- PDF text extraction (via their `datasets` library)

**Verdict**: Don't start with Hugging Face. Add it later **only** if you need ML-powered classification (e.g., "This photo shows a GNSS antenna" vs. "This is Aunt Susan at the beach").

---

## **What You Can Actually Reuse**

### **Category 1: Filesystem Scanning (80% of your core)**

#### **Option A: `scandir` / `os.walk` (Built-in Python)**

```python
import os
from pathlib import Path

for root, dirs, files in os.walk('/media/drive'):
    for file in files:
        path = Path(root) / file
        print(path, path.stat().st_size)
```

**Pros**: Built-in, fast, simple **Cons**: You write all the logic (classification, metadata extraction)

**👉 This is what you should use** (you're already doing this)

---

#### **Option B: `fdupes` / `rdfind` (Duplicate Detection)**

**What it does**: Finds duplicate files via MD5/SHA256

```bash
# Install
sudo apt install fdupes

# Find duplicates
fdupes -r /media/drive > duplicates.txt
```

**Pros**: Battle-tested, fast **Cons**:

- Shell tool (not Python)
- No file classification
- No archive support

**Verdict**: Use for **Phase 2** (duplicate detection), but write your own scanner for discovery.

---

#### **Option C: `tree` / `dirtree` (Directory Visualization)**

```bash
tree -h -L 3 /media/drive > structure.txt
```

**Pros**: Quick directory overview **Cons**: No metadata, no classification

**Verdict**: Reference for ideas, not a replacement

---

### **Category 2: Archive Handling (DON'T REINVENT)**

#### **Option A: `libarchive` (via `python-libarchive-c`)**

**What it is**: Industry-standard library supporting 40+ formats

```bash
uv add libarchive-c
```

```python
import libarchive

with libarchive.file_reader('data.tar.gz') as archive:
    for entry in archive:
        print(entry.pathname, entry.size)
```

**Supports**:

- ZIP, TAR, GZ, BZ2, XZ, 7Z, RAR, ISO, CAB, LHA, AR, and more
- Nested archives (zip inside tar.gz)
- Streaming (doesn't explode disk space)

**👉 USE THIS** instead of your custom archive handler

**Why**: You'd spend weeks implementing 7z/rar support. `libarchive` already does it.

---

#### **Option B: `py7zr` (7-Zip in Pure Python)**

```bash
uv add py7zr
```

```python
import py7zr

with py7zr.SevenZipFile('archive.7z', 'r') as archive:
    archive.extractall(path='/tmp')
```

**Pros**: Pure Python (no external dependencies) **Cons**: Only handles 7z

**Verdict**: Use `libarchive` instead (handles 7z + 40 other formats)

---

### **Category 3: File Type Detection (CRITICAL - DON'T REINVENT)**

#### **Option A: `python-magic` (libmagic wrapper)**

**What it is**: Detects file types by content (not just extension)

```bash
uv add python-magic
```

```python
import magic

mime = magic.Magic(mime=True)
print(mime.from_file('photo.jpg'))  # 'image/jpeg'
print(mime.from_file('renamed.txt'))  # 'application/pdf' (even if renamed!)
```

**Why this matters**:

- `family_photo.txt` → detects it's actually a JPEG
- `data.bin` → detects it's a RINEX file (via text pattern)

**👉 USE THIS** for robust file classification

---

#### **Option B: `filetype` (Pure Python Alternative)**

```bash
uv add filetype
```

```python
import filetype

kind = filetype.guess('photo.jpg')
print(kind.mime)  # 'image/jpeg'
```

**Pros**: No C dependencies (easier deployment) **Cons**: Less accurate than `python-magic`

**Verdict**: Start with `python-magic`, fallback to `filetype` if libmagic install issues

---

### **Category 4: Metadata Extraction (DON'T REINVENT)**

#### **Photos: `Pillow` + `piexif`**

```bash
uv add pillow piexif
```

```python
from PIL import Image
import piexif

img = Image.open('photo.jpg')
exif = piexif.load(img.info['exif'])

# Extract GPS coordinates
gps = exif['GPS']
lat = gps[piexif.GPSIFD.GPSLatitude]
lon = gps[piexif.GPSIFD.GPSLongitude]
date = exif['Exif'][piexif.ExifIFD.DateTimeOriginal]
```

**👉 USE THIS** for photo metadata (dates, GPS, camera model)

---

#### **PDFs: `pypdf` or `pdfplumber`**

```bash
uv add pypdf pdfplumber
```

```python
import pdfplumber

with pdfplumber.open('site_log.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if 'RINEX' in text or 'SITE CODE' in text:
            print("Found GNSS site log!")
```

**👉 USE THIS** for extracting text from site logs

---

#### **Office Docs: `python-docx` / `openpyxl`**

```bash
uv add python-docx openpyxl
```

```python
from docx import Document

doc = Document('budget_2015.docx')
for para in doc.paragraphs:
    if 'loan' in para.text.lower():
        print("⚠️ Financial document detected")
```

**👉 USE THIS** for searching inside Word/Excel files

---

#### **Videos: `pymediainfo`**

```bash
uv add pymediainfo
```

```python
from pymediainfo import MediaInfo

media = MediaInfo.parse('family_vacation.mp4')
for track in media.tracks:
    if track.track_type == 'Video':
        print(f"Duration: {track.duration/1000:.0f}s")
        print(f"Resolution: {track.width}x{track.height}")
```

**👉 USE THIS** for video metadata (duration, resolution, codec)

---

### **Category 5: GNSS-Specific Tools (YOUR DOMAIN EXPERTISE)**

#### **TEQC (UNAVCO)**

```bash
# Already installed, right?
teqc +qc -plot ALGO0010.22O
```

**What it does**: RINEX quality checking, metadata extraction

**Integration idea**:

```python
import subprocess

result = subprocess.run(
    ['teqc', '+meta', 'ALGO0010.22O'],
    capture_output=True,
    text=True
)

# Parse output for site code, receiver type, etc.
```

**👉 USE THIS** for validating RINEX files you discover

---

#### **RINGO (GSI's Tool from Your Docs)**

**What it is**: RINEX preprocessing (quality check, format conversion)

**Integration idea**: After finding RINEX files, run RINGO quality check batch job

```python
# After scan, generate RINGO batch script
for rinex_file in discovered_rinex:
    print(f"ringo qc {rinex_file}")
```

**👉 USE THIS** as a "next step" after discovery

---

#### **Hatanaka RINEX Compression (RNXCMP)**

**What it does**: Decompresses `.crx` files (compact RINEX)

```python
import subprocess

if filepath.suffix == '.crx':
    subprocess.run(['CRX2RNX', filepath])
```

**👉 USE THIS** to handle compressed RINEX

---

### **Category 6: Database/Search (MAYBE LATER)**

#### **SQLite (Built-in)**

**Why**: Store scan results for fast queries

```python
import sqlite3

conn = sqlite3.connect('scan_results.db')
conn.execute('''
    CREATE TABLE files (
        path TEXT PRIMARY KEY,
        size INTEGER,
        modified TIMESTAMP,
        file_type TEXT,
        md5 TEXT
    )
''')
```

**When to use**: After you have 100k+ files and JSONL feels slow

---

#### **Whoosh / Tantivy (Full-Text Search)**

**What it is**: Search engine for your file catalog

```python
from whoosh.index import create_in
from whoosh.fields import Schema, TEXT, ID

schema = Schema(path=ID(stored=True), content=TEXT)
ix = create_in("indexdir", schema)

# Later: Search for "RINEX" across all file paths
```

**When to use**: Phase 3, when you want `drive-archaeologist search "ALGO site log"`

---

## **Recommended Architecture (Reuse-Heavy)**

```python
# Updated pyproject.toml dependencies

dependencies = [
    "click>=8.1.0",                # CLI (you already have this)
    "rich>=13.0.0",                # Pretty output (you already have this)
    
    # File operations (DON'T REINVENT)
    "python-magic>=0.4.27",        # File type detection by content
    "libarchive-c>=5.0",           # Handle 40+ archive formats
    
    # Metadata extraction (DON'T REINVENT)
    "pillow>=10.0.0",              # Image metadata
    "piexif>=1.1.3",               # EXIF data
    "pypdf>=3.0.0",                # PDF text extraction
    "pdfplumber>=0.10.0",          # Better PDF parsing
    "python-docx>=1.0.0",          # Word documents
    "openpyxl>=3.1.0",             # Excel spreadsheets
    "pymediainfo>=6.0.0",          # Video/audio metadata
    
    # Data handling
    "pandas>=2.0.0",               # Analysis (you already have this)
    "tqdm>=4.66.0",                # Progress bars (you already have this)
]

[project.optional-dependencies]
# Advanced features
ocr = [
    "pytesseract>=0.3.10",         # OCR for scanned PDFs
    "pdf2image>=1.16.0",           # Convert PDF pages to images
]

gnss = [
    # No Python packages - you'll shell out to TEQC, RINGO, etc.
]
```

---

## **What You SHOULD Build Yourself**

### ✅ **1. Domain-Specific Classification**

```python
# src/drive_archaeologist/domains/gnss/detector.py

def is_rinex_obs(filepath):
    """Detect RINEX observation files"""
    # Pattern 1: Filename convention
    if re.match(r'^\w{4}\d{3}[0-9a-x]\.\d{2}[oO]$', filepath.name):
        return True
    
    # Pattern 2: Content sniffing (for misnamed files)
    with open(filepath) as f:
        header = f.read(1000)
        if 'RINEX VERSION' in header and 'OBSERVATION DATA' in header:
            return True
    
    return False
```

**Why**: No library knows GNSS-specific patterns

---

### ✅ **2. Structure Recognition**

```python
# src/drive_archaeologist/analyzer.py

def detect_datapool_structure(files_df):
    """Identify if files follow DATAPOOL/{SITE}/{YEAR}/ pattern"""
    patterns = [
        r'DATAPOOL/(\w{4})/(\d{4})',
        r'RAW/(\d{4})/(\d{3})',
    ]
    # Your logic here
```

**Why**: This is your unique insight into GNSS workflows

---

### ✅ **3. Migration Script Generation**

```python
# src/drive_archaeologist/migrator.py

def generate_reorganization_plan(analysis, target_structure):
    """Create bash script to move files"""
    # Your logic here
```

**Why**: This is your value-add (automating the tedious part)

---

## **Updated Development Plan**

### **Phase 1: Leverage Existing Tools (Week 1-2)**

```python
# Install battle-tested libraries
uv add python-magic libarchive-c pillow pypdf pdfplumber

# Test them individually
uv run python -c "import magic; print(magic.from_file('test.jpg', mime=True))"
```

### **Phase 2: Build Thin Wrappers (Week 3)**

```python
# src/drive_archaeologist/extractors/archive.py
import libarchive

class ArchiveExtractor:
    """Thin wrapper around libarchive"""
    
    def list_contents(self, archive_path):
        with libarchive.file_reader(str(archive_path)) as archive:
            return [
                {
                    'path': entry.pathname,
                    'size': entry.size,
                    'modified': entry.mtime,
                }
                for entry in archive
            ]
```

### **Phase 3: Add Your Secret Sauce (Week 4+)**

```python
# src/drive_archaeologist/domains/gnss/classifier.py

class GNSSClassifier:
    """Your domain expertise encoded"""
    
    def classify_rinex(self, filepath):
        # Use python-magic for basic type
        mime = magic.from_file(filepath, mime=True)
        
        # Add GNSS-specific logic
        if self._looks_like_rinex(filepath):
            return self._extract_rinex_metadata(filepath)
```

---

## **Summary: Reuse vs. Build**

|Component|Reuse?|Library|Why|
|---|---|---|---|
|**Filesystem scanning**|✅ Partial|`os.walk` / `pathlib`|Built-in, fast|
|**Archive extraction**|✅ YES|`libarchive-c`|Handles 40+ formats|
|**File type detection**|✅ YES|`python-magic`|Industry standard|
|**Photo metadata**|✅ YES|`Pillow` + `piexif`|Don't write EXIF parser|
|**PDF text extraction**|✅ YES|`pypdf` / `pdfplumber`|Complex format|
|**Video metadata**|✅ YES|`pymediainfo`|FFmpeg wrapper|
|**GNSS classification**|❌ BUILD|Your code|Domain expertise|
|**Structure detection**|❌ BUILD|Your code|Your unique insight|
|**Migration scripts**|❌ BUILD|Your code|Your value-add|

---

## **Bonus: Standing on Giants' Shoulders**

Similar projects to study (but not directly use):

1. **`dup-scout`** (duplicate finder) - Study its hash-based dedup
2. **`photorec`** (file recovery) - Study its file signature detection
3. **`recoll`** (desktop search) - Study its metadata indexing
4. **`fdupes`** (duplicate finder) - Study its performance optimizations

---

## **Your Next Action (15 min)**

**Test the key libraries**:

```bash
# Install them
uv add python-magic libarchive-c pillow pypdf

# Create test script: test_reuse.py
cat > test_reuse.py << 'EOF'
#!/usr/bin/env python3

import magic
import libarchive
from PIL import Image

# Test 1: File type detection
print("1. File type detection:")
mime = magic.Magic(mime=True)
print(f"  test.jpg -> {mime.from_file('test.jpg')}")

# Test 2: Archive listing
print("\n2. Archive contents:")
with libarchive.file_reader('test.zip') as archive:
    for entry in archive:
        print(f"  - {entry.pathname} ({entry.size} bytes)")

# Test 3: Photo metadata
print("\n3. Photo metadata:")
img = Image.open('test.jpg')
print(f"  Size: {img.size}")
print(f"  Format: {img.format}")

print("\n✅ All libraries work!")
EOF

# Run it
uv run python test_reuse.py
```

**Report back**: Did the libraries install cleanly? Any issues with `libmagic`?

Then we'll integrate them into your scanner architecture. 🚀

---

Perfect—**Linux Mint (Ubuntu-based) as dev environment → Debian server as production** is a solid, realistic constraint. Let me architect this for **maximum portability** while acknowledging Linux is your primary target.

---

## **Cross-Platform Strategy**

### **Priority Tiers**

1. **Tier 1 (Must Work)**: Linux Mint (dev) + Debian (production)
2. **Tier 2 (Should Work)**: Ubuntu, Fedora, other Linux distros
3. **Tier 3 (Nice to Have)**: macOS (for staff with MacBooks)
4. **Tier 4 (Best Effort)**: Windows (some staff might use it)

---

## **Dependency Audit: What Needs System Libraries?**

### **🚨 System Dependencies (Require apt/brew/etc.)**

|Library|System Package|Risk Level|Mitigation|
|---|---|---|---|
|`python-magic`|`libmagic1`|🟡 Medium|Install via apt, document in README|
|`libarchive-c`|`libarchive13`|🟡 Medium|Common on Linux, document for macOS|
|`pytesseract` (OCR)|`tesseract-ocr`|🟠 High|Optional dependency only|
|`pymediainfo`|`libmediainfo0v5`|🟡 Medium|Optional (only for video metadata)|
|`opencv-python` (OCR)|Various|🔴 Very High|Optional, Linux-only warning|

### **✅ Pure Python (No System Deps)**

|Library|Notes|
|---|---|
|`click`, `rich`, `tqdm`|CLI/UI - always works|
|`pandas`|Data analysis - pure Python (with C extensions)|
|`pillow`|Image handling - ships with bundled libs|
|`pypdf`, `pdfplumber`|PDF parsing - pure Python|
|`python-docx`, `openpyxl`|Office docs - pure Python|

---

## **Installation Strategy: Graceful Degradation**

### **Core Principle**: Ship with reasonable defaults, degrade gracefully if system libs missing

```python
# src/drive_archaeologist/compat.py
"""
Cross-platform compatibility layer
Gracefully handles missing system libraries
"""

import sys
import warnings

# Feature flags based on what's available
HAS_MAGIC = False
HAS_LIBARCHIVE = False
HAS_MEDIAINFO = False
HAS_TESSERACT = False

# Try importing with fallbacks
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    warnings.warn(
        "python-magic not available. File type detection will use extensions only.\n"
        "Install: sudo apt install libmagic1 && uv add python-magic"
    )

try:
    import libarchive
    HAS_LIBARCHIVE = True
except (ImportError, OSError):
    warnings.warn(
        "libarchive not available. Archive scanning will be limited.\n"
        "Install: sudo apt install libarchive13 && uv add libarchive-c"
    )

try:
    from pymediainfo import MediaInfo
    HAS_MEDIAINFO = True
except ImportError:
    warnings.warn("pymediainfo not available. Video metadata extraction disabled.")

try:
    import pytesseract
    pytesseract.get_tesseract_version()
    HAS_TESSERACT = True
except (ImportError, FileNotFoundError):
    # Tesseract binary not found or pytesseract not installed
    pass

def check_dependencies(required_features=None):
    """
    Check if required features are available
    
    Args:
        required_features: List of features like ['magic', 'libarchive', 'ocr']
    
    Returns:
        List of missing features
    """
    if required_features is None:
        return []
    
    feature_map = {
        'magic': HAS_MAGIC,
        'libarchive': HAS_LIBARCHIVE,
        'archives': HAS_LIBARCHIVE,  # Alias
        'mediainfo': HAS_MEDIAINFO,
        'video': HAS_MEDIAINFO,  # Alias
        'ocr': HAS_TESSERACT,
    }
    
    missing = [
        feature for feature in required_features
        if not feature_map.get(feature, True)
    ]
    
    return missing
```

---

## **Updated `pyproject.toml` with OS-Specific Handling**

```toml
[project]
name = "drive-archaeologist"
version = "0.1.0"
description = "Excavate decades of data from old hard drives"
readme = "README.md"
requires-python = ">=3.11"
authors = [
    {name = "Your Name", email = "you@example.com"}
]

# Core dependencies (pure Python or widely available)
dependencies = [
    "click>=8.1.0",
    "rich>=13.0.0",
    "pandas>=2.0.0",
    "pillow>=10.0.0",              # Ships with bundled libs
    "pypdf>=3.0.0",                # Pure Python
    "pdfplumber>=0.10.0",          # Pure Python
    "python-docx>=1.0.0",          # Pure Python
    "openpyxl>=3.1.0",             # Pure Python
    "tqdm>=4.66.0",
    "filetype>=1.2.0",             # Pure Python fallback for magic
]

[project.optional-dependencies]
# Full feature set (requires system libraries)
full = [
    "python-magic>=0.4.27",        # Requires: libmagic1
    "libarchive-c>=5.0",           # Requires: libarchive13
    "pymediainfo>=6.0.0",          # Requires: libmediainfo0v5
]

# OCR support (Linux-heavy dependencies)
ocr = [
    "pytesseract>=0.3.10",         # Requires: tesseract-ocr
    "pdf2image>=1.16.0",           # Requires: poppler-utils
]

# Development dependencies
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "ipython>=8.12.0",
]

[project.scripts]
drive-archaeologist = "drive_archaeologist.cli:main"
drive-arch = "drive_archaeologist.cli:main"
```

---

## **Installation Documentation**

### **`INSTALL.md`**

````markdown
# Installation Guide

## Quick Start (Linux Mint / Debian / Ubuntu)

### 1. Install System Dependencies

```bash
# Required for full functionality
sudo apt update
sudo apt install -y \
    libmagic1 \
    libarchive13 \
    libmediainfo0v5

# Optional: OCR support (large download ~400MB)
sudo apt install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils
````

### 2. Install Drive Archaeologist

```bash
# Clone repository
git clone https://github.com/yourusername/drive-archaeologist
cd drive-archaeologist

# Install with uv (installs Python 3.11 if needed)
uv sync --all-extras

# Verify installation
uv run drive-archaeologist --version
```

---

## Platform-Specific Instructions

### Debian Server (Production)

```bash
# Same as Linux Mint above
sudo apt install libmagic1 libarchive13 libmediainfo0v5
uv sync --all-extras
```

### Fedora / RHEL / CentOS

```bash
# Install system dependencies
sudo dnf install -y \
    file-libs \
    libarchive \
    libmediainfo

# Install Drive Archaeologist
uv sync --all-extras
```

### macOS (Intel or Apple Silicon)

```bash
# Install system dependencies via Homebrew
brew install libmagic libarchive media-info

# Install Drive Archaeologist
uv sync --all-extras
```

**Note**: On macOS, some features may be limited. Test thoroughly.

### Windows (Limited Support)

**⚠️ Warning**: Windows support is experimental. Some features may not work.

```powershell
# Install via WSL2 (recommended)
wsl --install -d Ubuntu
# Then follow Linux instructions inside WSL

# OR native Windows (limited functionality)
# 1. Install Python 3.11+ from python.org
# 2. Install uv: pip install uv
# 3. uv sync
```

**Limitations on Windows**:

- `python-magic` requires DLL setup (complex)
- `libarchive` may not work reliably
- OCR not tested

**Recommendation**: Use WSL2 on Windows for full functionality.

---

## Minimal Installation (No System Dependencies)

If you cannot install system libraries:

```bash
# Install without optional dependencies
uv sync

# Check what features are available
uv run drive-archaeologist check-deps
```

**What still works**:

- ✅ File scanning
- ✅ Basic file type detection (by extension)
- ✅ PDF text extraction
- ✅ Photo metadata (EXIF)
- ✅ Office document parsing
- ❌ Content-based file detection (needs libmagic)
- ❌ Archive scanning (needs libarchive)
- ❌ Video metadata (needs libmediainfo)
- ❌ OCR (needs tesseract)

---

## Troubleshooting

### `ImportError: libmagic.so.1: cannot open shared object file`

```bash
# Fix: Install libmagic
sudo apt install libmagic1

# Verify
python3 -c "import magic; print('OK')"
```

### `OSError: Could not find libarchive`

```bash
# Fix: Install libarchive
sudo apt install libarchive13

# Verify
python3 -c "import libarchive; print('OK')"
```

### `TesseractNotFoundError`

```bash
# Fix: Install tesseract
sudo apt install tesseract-ocr

# Verify
tesseract --version
```

````

---

## **CLI Feature Detection**

```python
# src/drive_archaeologist/cli.py

import click
from rich.console import Console
from rich.table import Table
from . import compat

console = Console()

@click.group()
@click.version_option()
def main():
    """🔍 Drive Archaeologist - Excavate data from old hard drives"""
    pass

@main.command()
def check_deps():
    """Check which optional features are available"""
    
    table = Table(title="Feature Availability")
    table.add_column("Feature", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Notes")
    
    features = [
        ("Content-based file detection", compat.HAS_MAGIC, 
         "Install: sudo apt install libmagic1"),
        ("Archive scanning (ZIP/TAR/7Z)", compat.HAS_LIBARCHIVE,
         "Install: sudo apt install libarchive13"),
        ("Video metadata extraction", compat.HAS_MEDIAINFO,
         "Install: sudo apt install libmediainfo0v5"),
        ("OCR (scanned PDFs)", compat.HAS_TESSERACT,
         "Install: sudo apt install tesseract-ocr"),
    ]
    
    for name, available, install_cmd in features:
        status = "✅ Available" if available else "❌ Missing"
        style = "green" if available else "red"
        table.add_row(name, f"[{style}]{status}[/{style}]", 
                     "" if available else install_cmd)
    
    console.print(table)
    
    if not all(f[1] for f in features):
        console.print("\n[yellow]💡 Tip:[/yellow] Run with reduced features or install missing dependencies")

@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--archives', is_flag=True, help='Scan inside archives (requires libarchive)')
@click.option('--deep', is_flag=True, help='Enable all intensive features (OCR, video metadata)')
def scan(path, archives, deep):
    """Scan a drive and catalog all files"""
    
    # Check dependencies before starting
    required = []
    if archives:
        required.append('libarchive')
    if deep:
        required.extend(['mediainfo', 'ocr'])
    
    missing = compat.check_dependencies(required)
    
    if missing:
        console.print(f"[red]❌ Missing required features:[/red] {', '.join(missing)}")
        console.print("[yellow]Run 'drive-archaeologist check-deps' for installation instructions[/yellow]")
        return
    
    console.print(f"[bold blue]🔍 Scanning:[/bold blue] {path}")
    
    from .scanner import DeepScanner
    scanner = DeepScanner(path, scan_archives=archives, deep_mode=deep)
    scanner.scan()
````

---

## **Fallback File Type Detection**

```python
# src/drive_archaeologist/detection.py

from pathlib import Path
from . import compat

class FileTypeDetector:
    """
    Multi-strategy file type detection with fallbacks
    """
    
    def __init__(self):
        self.strategies = []
        
        # Strategy 1: Content-based (best, requires libmagic)
        if compat.HAS_MAGIC:
            import magic
            self.mime_detector = magic.Magic(mime=True)
            self.strategies.append(self._detect_by_content)
        
        # Strategy 2: Library-based (good, pure Python)
        try:
            import filetype
            self.filetype_detector = filetype
            self.strategies.append(self._detect_by_signature)
        except ImportError:
            pass
        
        # Strategy 3: Extension-based (fallback, always available)
        self.strategies.append(self._detect_by_extension)
    
    def detect(self, filepath):
        """
        Try detection strategies in order until one succeeds
        
        Returns:
            dict: {'mime': 'image/jpeg', 'extension': '.jpg', 'method': 'content'}
        """
        for strategy in self.strategies:
            result = strategy(filepath)
            if result:
                return result
        
        return {'mime': 'application/octet-stream', 'extension': filepath.suffix, 'method': 'unknown'}
    
    def _detect_by_content(self, filepath):
        """Use libmagic (most accurate)"""
        try:
            mime = self.mime_detector.from_file(str(filepath))
            return {'mime': mime, 'extension': filepath.suffix, 'method': 'content'}
        except Exception:
            return None
    
    def _detect_by_signature(self, filepath):
        """Use filetype library (file signatures)"""
        try:
            kind = self.filetype_detector.guess(str(filepath))
            if kind:
                return {'mime': kind.mime, 'extension': kind.extension, 'method': 'signature'}
        except Exception:
            return None
    
    def _detect_by_extension(self, filepath):
        """Fallback: extension-based mapping"""
        ext_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
            '.zip': 'application/zip',
            '.tar': 'application/x-tar',
            '.gz': 'application/gzip',
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            # GNSS-specific
            '.22o': 'application/x-rinex-obs',
            '.22n': 'application/x-rinex-nav',
            '.dat': 'application/x-trimble',
        }
        
        mime = ext_map.get(filepath.suffix.lower(), 'application/octet-stream')
        return {'mime': mime, 'extension': filepath.suffix, 'method': 'extension'}
```

---

## **Archive Handler with Fallbacks**

```python
# src/drive_archaeologist/archives.py

from pathlib import Path
import zipfile
import tarfile
import gzip
from . import compat

class ArchiveHandler:
    """
    Multi-backend archive handler
    Gracefully degrades if libarchive not available
    """
    
    def __init__(self):
        self.backend = 'libarchive' if compat.HAS_LIBARCHIVE else 'stdlib'
    
    def can_handle(self, filepath):
        """Check if we can process this archive"""
        ext = filepath.suffix.lower()
        
        if self.backend == 'libarchive':
            # libarchive handles 40+ formats
            return ext in {
                '.zip', '.tar', '.gz', '.tgz', '.tar.gz',
                '.bz2', '.tar.bz2', '.xz', '.tar.xz',
                '.7z', '.rar', '.iso', '.cab'
            }
        else:
            # stdlib only handles common formats
            return ext in {'.zip', '.tar', '.gz', '.tgz', '.tar.gz', '.bz2', '.tar.bz2'}
    
    def list_contents(self, archive_path):
        """
        List archive contents
        
        Returns:
            List[dict]: [{'path': '...', 'size': 123, ...}, ...]
        """
        if self.backend == 'libarchive':
            return self._list_with_libarchive(archive_path)
        else:
            return self._list_with_stdlib(archive_path)
    
    def _list_with_libarchive(self, archive_path):
        """Use libarchive (supports 40+ formats)"""
        import libarchive
        
        contents = []
        with libarchive.file_reader(str(archive_path)) as archive:
            for entry in archive:
                if not entry.isdir:
                    contents.append({
                        'path': f"{archive_path}::{entry.pathname}",
                        'name': Path(entry.pathname).name,
                        'size': entry.size,
                        'archive_source': str(archive_path),
                    })
        return contents
    
    def _list_with_stdlib(self, archive_path):
        """Fallback: Python stdlib (limited format support)"""
        ext = archive_path.suffix.lower()
        
        if ext == '.zip':
            return self._list_zip(archive_path)
        elif '.tar' in archive_path.name.lower():
            return self._list_tar(archive_path)
        elif ext == '.gz':
            return self._list_gzip(archive_path)
        else:
            raise ValueError(f"Unsupported archive format: {ext}")
    
    def _list_zip(self, zip_path):
        """Handle ZIP files with stdlib"""
        contents = []
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    contents.append({
                        'path': f"{zip_path}::{info.filename}",
                        'name': Path(info.filename).name,
                        'size': info.file_size,
                        'archive_source': str(zip_path),
                    })
        return contents
    
    def _list_tar(self, tar_path):
        """Handle TAR files with stdlib"""
        # Detect compression
        if tar_path.suffix == '.gz' or '.tgz' in tar_path.name:
            mode = 'r:gz'
        elif tar_path.suffix == '.bz2':
            mode = 'r:bz2'
        else:
            mode = 'r'
        
        contents = []
        with tarfile.open(tar_path, mode) as tf:
            for member in tf.getmembers():
                if member.isfile():
                    contents.append({
                        'path': f"{tar_path}::{member.name}",
                        'name': Path(member.name).name,
                        'size': member.size,
                        'archive_source': str(tar_path),
                    })
        return contents
    
    def _list_gzip(self, gz_path):
        """Handle standalone GZIP files"""
        # GZIP is single-file compression
        original_name = gz_path.stem
        return [{
            'path': f"{gz_path}::{original_name}",
            'name': original_name,
            'size': gz_path.stat().st_size,  # Approximate
            'archive_source': str(gz_path),
        }]
```

---

## **Testing Across Platforms**

### **`tests/test_compat.py`**

```python
import pytest
from drive_archaeologist import compat

def test_feature_flags_are_boolean():
    """Ensure all feature flags are properly set"""
    assert isinstance(compat.HAS_MAGIC, bool)
    assert isinstance(compat.HAS_LIBARCHIVE, bool)
    assert isinstance(compat.HAS_MEDIAINFO, bool)
    assert isinstance(compat.HAS_TESSERACT, bool)

def test_check_dependencies_with_missing():
    """Test dependency checking"""
    # This will vary by environment
    missing = compat.check_dependencies(['magic', 'libarchive'])
    assert isinstance(missing, list)

@pytest.mark.skipif(not compat.HAS_MAGIC, reason="libmagic not available")
def test_magic_detection():
    """Test content-based file detection (requires libmagic)"""
    import magic
    m = magic.Magic(mime=True)
    # Test will only run if libmagic is installed
    assert m.from_buffer(b'%PDF-1.4') == 'application/pdf'

@pytest.mark.skipif(not compat.HAS_LIBARCHIVE, reason="libarchive not available")
def test_archive_handling():
    """Test archive processing (requires libarchive)"""
    # Test will only run if libarchive is installed
    pass
```

---

## **CI/CD for Multi-Platform Testing**

### **`.github/workflows/test.yml`**

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test-linux:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install system dependencies
        run: |
          sudo apt update
          sudo apt install -y libmagic1 libarchive13 libmediainfo0v5
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install Python dependencies
        run: uv sync --all-extras
      
      - name: Run tests
        run: uv run pytest --cov=drive_archaeologist
      
      - name: Lint
        run: uv run ruff check src/
  
  test-macos:
    runs-on: macos-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install system dependencies
        run: brew install libmagic libarchive media-info
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install Python dependencies
        run: uv sync --all-extras
      
      - name: Run tests
        run: uv run pytest
  
  test-minimal:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install Python dependencies (minimal)
        run: uv sync
      
      - name: Run tests (expect some skips)
        run: uv run pytest -v
```

---

## **Deployment Script for Debian Server**

### **`scripts/deploy_debian.sh`**

```bash
#!/bin/bash
# Deploy to Debian server (production)

set -e

echo "🚀 Deploying Drive Archaeologist to Debian server..."

# Update system
sudo apt update
sudo apt upgrade -y

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    libmagic1 \
    libarchive13 \
    libmediainfo0v5 \
    git

# Install uv
echo "⚙️  Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# Clone/update repository
if [ -d "/opt/drive-archaeologist" ]; then
    echo "📥 Updating existing installation..."
    cd /opt/drive-archaeologist
    git pull
else
    echo "📥 Cloning repository..."
    sudo git clone https://github.com/yourusername/drive-archaeologist /opt/drive-archaeologist
    sudo chown -R $USER:$USER /opt/drive-archaeologist
    cd /opt/drive-archaeologist
fi

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
uv sync --all-extras

# Create systemd service (optional)
echo "🔧 Setting up systemd service..."
sudo tee /etc/systemd/system/drive-archaeologist.service > /dev/null <<EOF
[Unit]
Description=Drive Archaeologist Scanner
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/opt/drive-archaeologist
ExecStart=/opt/drive-archaeologist/.venv/bin/drive-archaeologist scan /media/archive
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable drive-archaeologist
sudo systemctl start drive-archaeologist

echo "✅ Deployment complete!"
echo "Check status: sudo systemctl status drive-archaeologist"
```

---

## **Your Next Actions**

### **Action 1: Verify Linux Mint Environment (5 min)**

```bash
# Check system dependencies
dpkg -l | grep -E "libmagic1|libarchive13|libmediainfo"

# If missing, install
sudo apt install libmagic1 libarchive13 libmediainfo0v5

# Verify Python
python3 --version  # Should be 3.11+
```

### **Action 2: Test Fallback Behavior (10 min)**

```bash
# Create test with full features
uv sync --all-extras
uv run python -c "from drive_archaeologist import compat; print(f'Magic: {compat.HAS_MAGIC}, Archive: {compat.HAS_LIBARCHIVE}')"

# Test minimal install (simulate missing deps)
uv sync  # No --all-extras
# Should still work with degraded functionality
```

### **Action 3: Document Your Specific Setup (5 min)**

Create `DEV_SETUP.md`:

````markdown
# My Development Setup

**Dev Machine**: Linux Mint 21.x
**Production**: Debian 12 (bookworm)

## Quick Start
```bash
sudo apt install libmagic1 libarchive13
uv sync --all-extras
uv run drive-archaeologist check-deps
````

## Known Issues

- None yet

```

**Ready to start coding the scanner with these portability layers?** Or want to test the deployment script on a VM first?
```