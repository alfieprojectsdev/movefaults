# Technical Review: Work Instructions for Processing GPS Data
## MOVE Faults Project - PHIVOLCS

**Document:** Work_Instructions_ao20251017.docx.pdf  
**Reviewed by:** Alfie R. Pelicano (Technical Co-Author)  
**Review Date:** October 22, 2025  
**Document Version:** October 2025

---

## Executive Summary

### Overall Assessment: **STRONG** (8/10)

This work instruction document represents a **comprehensive, well-structured technical manual** that successfully balances procedural detail with accessibility. The document demonstrates strong technical expertise and thoughtful organization, making complex GNSS processing workflows approachable for both new staff and experienced practitioners.

### Key Strengths
✅ Clear hierarchical structure with logical progression  
✅ Excellent use of visual aids (screenshots, sample outputs)  
✅ Comprehensive definitions section (Section 3)  
✅ Troubleshooting guidance included (Section 4.5)  
✅ Consistent formatting and terminology  
✅ Practical examples throughout  

### Areas for Improvement
⚠️ Some procedural ambiguities (e.g., when to use automation vs. manual methods)  
⚠️ Missing error handling guidance in several sections  
⚠️ Inconsistent detail level across similar procedures  
⚠️ Limited cross-referencing between related sections  
⚠️ No appendix for quick reference commands  

### Priority Recommendations
1. Add decision flowcharts for workflow branches (manual vs. automated)
2. Expand error handling guidance throughout
3. Create command quick-reference appendix
4. Standardize prerequisite checks across sections
5. Add troubleshooting subsections to major procedures

---

## Section-by-Section Review

---

## **Section 1: Objective** ✓ GOOD

### Content Quality: 8/10

**Strengths:**
- Clear statement of purpose
- Explicitly mentions accuracy, efficiency, and consistency
- Ties to broader project goals

**Issues Identified:**
- None critical

**Suggested Revisions:**

```diff
- The objective of this work instruction is to provide a clear and standardized workflow
- for handling and processing GNSS data. By documenting the procedure in detail, this
- ensures the accuracy and efficiency in executing office tasks related to GPS data
- processing, as well as consistency in producing reliable results that support the
- Project's monitoring and research activities.

+ The objective of this work instruction is to provide a clear and standardized workflow
+ for handling and processing GNSS data. By documenting these procedures in detail, this
+ manual ensures accuracy and efficiency in executing office tasks related to GNSS data
+ processing, as well as consistency in producing reliable results that support the
+ Project's monitoring and research activities. This document serves as both a training
+ resource for new staff and a reference guide for experienced processors.
```

**Rationale:** Minor grammatical improvement ("these procedures") and added explicit mention of dual purpose (training + reference).

---

## **Section 2: Scope** ✓ GOOD

### Content Quality: 8/10

**Strengths:**
- Clearly delineates what is/isn't covered
- Three main tasks explicitly enumerated
- Appropriate boundaries set (no fieldwork, advanced analytics)

**Issues Identified:**
1. **Ambiguity**: "routine data handling" is vague
2. **Missing context**: What constitutes "regular GNSS processing workflow"?

**Suggested Revisions:**

```diff
  This work instruction covers office-based GNSS data processing activities,
  specifically these three main tasks: (1) data conversion of raw GNSS files into RINEX
  format, (2) data processing using the Bernese GNSS 5.2 software, and (3)
  generation of time series plots from processed station coordinates. The procedures
- are limited to routine data handling and do not extend to fieldwork, coseismic
- measurements, or advanced analytical techniques beyond the regular GNSS
- processing workflow.

+ are limited to routine daily/campaign data processing and do not extend to fieldwork 
+ operations, coseismic displacement analysis, or advanced analytical techniques such as 
+ strain modeling, velocity field inversion, or specialized studies beyond the standard 
+ coordinate determination workflow.
```

**Additional Recommendation:** Add a sentence about who should use this document:

```markdown
**Target Users:** This document is intended for GNSS data processors, quality control 
analysts, and technical staff responsible for maintaining the Project's coordinate time 
series database. Basic familiarity with geodetic concepts is assumed.
```

---

## **Section 3: Definitions** ✓ EXCELLENT

### Content Quality: 9/10

**Strengths:**
- Comprehensive coverage of domain-specific terms
- Clear, concise definitions
- Appropriate technical depth
- Well-organized alphabetically within categories
- Distinguishes between different uses of same term (Campaign)

**Issues Identified:**
1. **Missing terms**: Some terms used later aren't defined here (e.g., "Julian Day", "ECEF", "ENU")
2. **Format inconsistency**: Some definitions include examples, others don't

**Suggested Additions:**

```markdown
● Carrier Phase
  The phase measurement of the satellite signal's carrier wave, providing millimeter-level 
  precision for positioning when processed differentially.

● Cycle Slip
  A discontinuity in the carrier phase measurement caused by signal obstruction or 
  receiver tracking loss, requiring detection and correction during processing.

● Earth-Centered, Earth-Fixed (ECEF) Coordinates
  A Cartesian coordinate system with origin at Earth's center of mass, where X-axis 
  points to the intersection of the equator and prime meridian, Z-axis points to the 
  North Pole, and Y-axis completes the right-handed system.

● East-North-Up (ENU) Coordinates
  A local topocentric coordinate system with origin at the station, where East and North 
  are tangent to the reference ellipsoid and Up points away from Earth's center.

● Julian Day of Year (DOY)
  The sequential day number within a calendar year (001 to 365/366), used in GPS data 
  file naming conventions.

● Multipath
  Signal interference caused by reflected satellite signals reaching the antenna from 
  multiple paths, degrading positioning accuracy.
```

**Minor Revision:**

```diff
● Sessions (Bernese processing context)
- A defined time interval that covers all GNSS observations and associated
- products that are to be processed together.

+ A defined time interval (typically 24 hours) that covers all GNSS observations and 
+ associated products that are to be processed together. For daily processing, a session 
+ corresponds to one calendar day.
```

---

## **Section 4: Procedure: Data Conversion** ⚠️ NEEDS IMPROVEMENT

### Overall Assessment: 7/10

**Major Strengths:**
- Excellent prerequisite documentation
- Clear distinction between manual and automated workflows
- Comprehensive troubleshooting section (4.5)
- Good use of visual examples

**Critical Issues:**

### **Issue 1: Workflow Decision Logic Unclear**

**Problem:** Section 4.2 says "For the automated version using Python, skip this section..." but doesn't explain WHEN to use which method.

**Impact:** New users won't know which workflow to follow.

**Recommended Fix:** Add decision flowchart at start of Section 4:

```markdown
## 4. Procedure: Data Conversion

### 4.0. Choosing Your Workflow

Use this decision tree to determine which conversion method to use:

```
Do you have multiple files to convert?
├─ YES → Is this campaign data (mixed sites/dates)?
│   ├─ YES → Use Section 4.3 (campaign_v5.py)
│   └─ NO → Is this continuous data (single site, many days)?
│       ├─ YES → Use Section 4.4 (continuous_v5.py)
│       └─ NO → Use Section 4.2 (command-line)
└─ NO → Use Section 4.2 (command-line)
```

**When to use command-line (Section 4.2):**
- Learning how the conversion process works
- Converting single files for testing
- Troubleshooting conversion issues
- Automated scripts aren't available

**When to use Python automation (Sections 4.3/4.4):**
- Batch processing multiple files (>5 files)
- Routine daily processing
- Consistent, repeatable workflows
```

---

### **Section 4.1: Prerequisites** ✓ EXCELLENT

**Content Quality:** 9/10

**Strengths:**
- Clear installation instructions with URLs
- Important file location notes (System32 placement)
- Good explanation of naming conventions
- Excellent use of formatted examples

**Minor Issues:**

**Issue 1:** Step 4.1.1 doesn't mention administrator privileges

**Suggested Addition:**

```diff
4.1.1. Open an internet browser. Download and install the following on your
designated computer:
+ 
+ **Note:** Some installations (particularly runpkr00.exe and teqc.exe placement 
+ in System32) may require administrator privileges. Contact your IT administrator 
+ if you encounter "Access Denied" errors.
```

**Issue 2:** Python installation has no version specification

```diff
- ● Python - downloadable at python.org

+ ● Python (version 3.8 or newer) - downloadable at python.org
+   After installation, verify by opening Command Prompt and typing: python --version
```

**Issue 3:** Missing information about required Python packages

**Suggested Addition after Step 4.1.1:**

```markdown
4.1.1.5. Install required Python packages. Open Command Prompt and run:

pip install pandas openpyxl

These packages are required for the campaign_v5.py and continuous_v5.py scripts.
```

---

### **Section 4.1.3: File Naming Conventions** ✓ EXCELLENT

**Content Quality:** 9/10

**Strengths:**
- Excellent explanatory structure
- Clear breakdown of filename components
- Good examples throughout

**Suggested Enhancement:**

Add a **comparison table** summarizing all formats for quick reference:

```markdown
**Quick Reference: GNSS File Naming Conventions**

| Receiver Type | Raw Format | Extension | Example | Key Pattern |
|--------------|------------|-----------|---------|-------------|
| Trimble 5700 | Proprietary | .T00-.T04 | 68511430.T01 | SSSSDDDN |
| Trimble NetR9 | Proprietary | .T02 | MAR2______202406021430A.T02 | SITE______YYYYMMDDHHMM[A-C] |
| Leica | MDB | .m[0-9][0-9] | PIVS001a.m00 | SITEDDDs.m## |
| Standard | RINEX v2 | .YYo | MAR21540.24o | SITEDDD0.YYo |

**Legend:**
- SSSS = Last 4 digits of receiver S/N or site code
- DDD/JJJ = Julian day of year (001-366)
- N = File sequence (0-9, a-x)
- s = Session identifier (a-x for hourly, 'a' for daily)
- ## = File segment number (00, 01, 02...)
- YY = 2-digit year
```

---

### **Section 4.2: Command-line Conversion** ⚠️ NEEDS CLARITY

**Content Quality:** 7/10

**Critical Issues:**

### **Issue 1: Missing Error Handling**

**Problem:** Steps assume perfect execution. What if `runpkr00` fails? What if no .DAT files are created?

**Example at Step 4.2.1.6:**

```diff
4.2.1.6. Execute runpkr00.exe by double-clicking the batch file
convert2dattgd.bat. 
- This will create new files with .DAT or .TGD extension inside the current directory.

+ This will create new files with .DAT or .TGD extension inside the current directory.
+ 
+ **Verification:** Check that .DAT or .TGD files were created (one for each raw file). 
+ If files are missing or you see error messages:
+   - Verify raw files are not corrupted (check file size > 0)
+   - Ensure runpkr00.exe is in System32 or current directory
+   - Check for GPS week rollover issues (see Section 4.5)
```

### **Issue 2: Insufficient Explanation of TEQC Parameters**

**Problem:** Step 4.2.2.1 lists parameters but doesn't explain their importance or common errors.

**Recommended Addition:**

```markdown
**Critical Parameters Explained:**

- **-O.pe (antenna height)**: Must match field log sheet EXACTLY. Common error: using 
  slant height instead of vertical height. Use compute_ant-h.xlsx to calculate.
  
- **-O.dec (decimation)**: Must match your data logging rate. If unsure, check RINEX 
  header after conversion. Mismatch will cause Bernese processing errors.
  
- **INPUT file pattern**: Use wildcards carefully:
  - `*.tgd` = all TGD files in directory (may include unwanted files)
  - `MAR2*.tgd` = only MAR2 files
  - `MAR2______????????0000A.tgd` = specific format only (recommended)
```

### **Issue 3: Antenna Height Computation Not Explained**

**Problem:** Step 4.2.2.1 mentions "use compute_ant-h.xlsx for the height computation" but never explains HOW.

**Recommended Addition (new subsection):**

```markdown
### 4.2.0. Antenna Height Computation

Before running TEQC, calculate the correct vertical antenna height:

**For Slant Height Measurements:**

1. Open compute_ant-h.xlsx (downloaded in Step 4.1.2)
2. Enter measured slant heights (typically 3 measurements around antenna)
3. The spreadsheet automatically computes the vertical height (h)
4. Use this h value in the -O.pe parameter

**Example:**
```
Slant measurements: 1.456m, 1.458m, 1.454m
Average slant: 1.456m
Vertical height: 1.3938m  ← Use this in TEQC
```

**For Direct Vertical Measurements:**
- If using a height pole with bubble level, use measured value directly
- Always cross-check with field log sheet

**Common Mistakes:**
- ❌ Using slant height instead of vertical height → 5-15cm coordinate error
- ❌ Forgetting to account for antenna reference point (ARP) → systematic offset
- ❌ Mixing units (cm vs. m) → 100× scaling error
```

---

### **Section 4.2.2: Sample RINEX Output** ✓ EXCELLENT

**Content Quality:** 9/10

**Strengths:**
- Actual sample file shown with annotations
- Key header fields highlighted
- Good pedagogical value

**Suggested Enhancement:**

Add troubleshooting note:

```markdown
**Validation Checklist for RINEX Files:**

After conversion, check these header fields:
- ☑ APPROX POSITION XYZ: Should be within ~100km of expected location
- ☑ ANTENNA: DELTA H/E/N: Height should match your -O.pe value
- ☑ INTERVAL: Should match your logging rate (30.000 for 30-second)
- ☑ TIME OF FIRST OBS: Should match observation date
- ☑ # / TYPES OF OBSERV: Should include L1, L2, C1, P2 at minimum

**Common Red Flags:**
- ⚠️ Position at (0, 0, 0) → RINEX header corrupt
- ⚠️ Antenna height = 0 → Missing -O.pe parameter
- ⚠️ Wrong date in filename vs. header → GPS week rollover (see Section 4.5)
```

---

### **Section 4.3: Automated Campaign Conversion** ⚠️ NEEDS IMPROVEMENT

**Content Quality:** 7/10

**Critical Issues:**

### **Issue 1: Missing Prerequisite Validation**

**Problem:** Script assumes files are in correct location, but Step 4.3.2 says "organize it into subfolders by their site name" without validation steps.

**Recommended Addition after Step 4.3.2:**

```markdown
4.3.2.5. Verify folder structure before running script:

```
Documents\
├── COTD\
│   ├── 68511430.T01
│   ├── 68511440.T01
│   └── ...
├── SITE\
│   ├── raw_file1.T02
│   └── ...
```

**Common Mistakes:**
- ❌ Files in Documents root (not in site subfolder)
- ❌ Multiple site files mixed in one folder
- ❌ Incorrect site name (COTD vs COTD_2018)
```

### **Issue 2: No Error Recovery Guidance**

**Problem:** What if Step 4.3.3.2 (runpkr00) fails for some files?

**Recommended Addition:**

```markdown
4.3.3.2. Input "Y" to run runpkr00.exe. [...existing text...]

**Troubleshooting:**
- If conversion fails for specific files, note the filename and continue with others
- After batch completion, manually inspect failed files:
  ```
  dir *.T01  # Check which raw files exist
  dir *.tgd  # Check which TGD files were created
  ```
- Files with 0 bytes or missing TGD files indicate:
  - Corrupted raw data (re-download from receiver)
  - GPS week rollover (proceed to Section 4.5)
  - Incompatible receiver firmware version (contact technical support)
```

### **Issue 3: Script Behavior Not Fully Explained**

**Problem:** User doesn't know what happens behind the scenes. What if script crashes? Can they resume?

**Recommended Addition (new subsection before 4.3.3):**

```markdown
### 4.3.2.5. Understanding campaign_v5.py Behavior

**What the script does:**
1. Scans Documents\{SITE}\ for raw files
2. Runs runpkr00 to create .DAT/.TGD files (Trimble only)
3. Prompts for each file's metadata (site name, antenna type, height)
4. Runs TEQC with appropriate parameters
5. Outputs RINEX files in same directory
6. Logs all operations to campaign_conversion.log

**Important Notes:**
- ✓ Script can be interrupted (Ctrl+C) and resumed later
- ✓ Already-converted files are skipped (checks for existing RINEX)
- ✓ Each file is processed independently (one failure doesn't stop others)
- ✓ All TEQC commands are logged for troubleshooting

**Log File Location:** Documents\{SITE}\campaign_conversion.log
```

---

### **Section 4.4: Automated Continuous Conversion** ⚠️ NEEDS IMPROVEMENT

**Content Quality:** 7/10

**Issues Identified:**

### **Issue 1: Inconsistent with Section 4.3**

**Problem:** Different level of detail compared to campaign conversion. Users might wonder if something is missing.

**Recommendation:** Match structure of 4.3 (add prerequisite checks, error handling notes).

### **Issue 2: Trimble vs. Leica Branching Unclear**

**Problem:** Step 4.4.2.2 splits into "a" and "b" but doesn't explain how to KNOW which one to use if you're unsure.

**Recommended Addition before 4.4.2.2:**

```markdown
**Determining Your Receiver Type:**

**If you're unsure whether your data is Trimble or Leica:**
1. Check file extensions:
   - `.T00`, `.T01`, `.T02` → Trimble (proceed to 4.4.2.2.a)
   - `.m00`, `.m01`, `.m##` → Leica (proceed to 4.4.2.2.b)

2. Check filename pattern:
   - `SITE______YYYYMMDDHHMM[A-C].T02` → Trimble NetR9
   - `SITEDDDs.m##` → Leica

3. Check receiver documentation or field log sheets

**If files are mixed formats:**
- Process each receiver type separately
- Create separate subfolders: MAR2_Trimble, MAR2_Leica
- Run script twice with appropriate site folders
```

---

### **Section 4.5: Troubleshooting** ✓ EXCELLENT

**Content Quality:** 9/10

**Strengths:**
- Addresses real, common problem (GPS week rollover)
- Step-by-step fix procedure
- Clear validation criteria (incorrect .YYo extension)
- Good use of screenshots

**Suggested Enhancements:**

**1. Add Context:**

```markdown
### 4.5. Troubleshooting

This section covers common issues encountered during data conversion. For Bernese 
processing errors, refer to Section 5 troubleshooting subsections.

#### 4.5.1. GPS Week Rollover Issue

**Background:** GPS week numbers reset every 1024 weeks (~19.7 years). Older Trimble 
receivers (especially 5700 series) may incorrectly interpret the current week number, 
causing wrong dates in RINEX files.

**Symptoms:**
- RINEX file extension shows wrong year (e.g., `.05o` instead of `.25o`)
- File dates are exactly 1024 weeks (19.7 years) off
- Bernese rejects files with "Date mismatch" error

**Affected Receivers:** Primarily Trimble 5700, some 5800 units

**When This Occurs:**
- After GPS week rollover events (April 2019, November 2038)
- Receivers with outdated firmware
- Long periods without receiver time synchronization
```

**2. Add Prevention Note:**

```markdown
**Preventing GPS Week Issues:**

For future data collection:
- Update receiver firmware before April 2038 rollover
- Verify RINEX dates immediately after download
- Include date verification in automated ingestion pipeline (see Section 4.3 enhancements)
```

**3. Add General Troubleshooting Table:**

```markdown
### 4.5.11. Quick Troubleshooting Reference

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| runpkr00 fails with "Invalid format" | Corrupted raw file | Re-download from receiver |
| TEQC produces empty RINEX | Wrong receiver type flag (-tr) | Check file extension, use correct flag |
| RINEX has wrong year | GPS week rollover | Use fixdatweek.exe (Section 4.5) |
| "Command not found" error | Program not in PATH | Place in System32 or add to PATH |
| RINEX position at (0,0,0) | Receiver never achieved lock | Check antenna setup, re-observe |
| Antenna height = 0 in RINEX | Missing -O.pe parameter | Add height to TEQC command |
| Site name truncated in RINEX | Special characters in -O.mo | Use 4-character alphanumeric site codes only |

For issues not listed here, check:
1. Raw file integrity (file size, not 0 bytes)
2. TEQC log output (usually in current directory)
3. Campaign log files (campaign_conversion.log, continuous_conversion.log)
4. Section 5.7 for Bernese-specific errors
```

---

## **Section 5: Procedure: Post-processing using Bernese** ⚠️ MIXED QUALITY

### Overall Assessment: 7.5/10

**Major Strengths:**
- Very comprehensive coverage of Bernese workflow
- Excellent screenshots and visual aids
- Good separation of first-time setup vs. routine processing
- Practical examples throughout

**Critical Weaknesses:**
- Inconsistent error handling guidance
- Some steps assume too much prior knowledge
- Missing validation checks between major steps
- Limited explanation of WHY certain steps are necessary

---

### **Section 5.1: Installation** ⚠️ INSUFFICIENT

**Content Quality:** 5/10

**Critical Issues:**

### **Issue 1: Incomplete Installation Guidance**

**Problem:** Says "installation guide...located in Bernese_Install folder on the Project's server" but gives NO guidance if that's not accessible.

**Impact:** New users or external collaborators cannot use this section.

**Recommended Fix:**

```diff
### 5.1. Installation

The Bernese GNSS Software is a commercial scientific software developed at
AIUB for high-precision processing of multi-GNSS data. 

+ **License Requirement:** Bernese is commercial software requiring a valid license from 
+ AIUB. Contact the Project Leader for license information and installation media access.
+ 
+ **For PHIVOLCS Staff:** Installation files and guides are located in the Bernese_Install 
+ folder on the Project's server at \\server\GPS\Software\Bernese_Install\
+ 
+ **For External Users:** Refer to the official Bernese website (https://www.bernese.unibe.ch/) 
+ for licensing, purchase, and installation instructions. This work instruction assumes 
+ Bernese 5.2 is already installed.

The software is installed using three setup wizards: BERN52, GPSUSER52, and CAMPAIGN52.
- These, along with the installation guide and the update procedure, are located in the
- Bernese_Install folder on the Project's server. 

It is strongly recommended that the software be installed in a single folder directly on 
- the root drive (e.g., C:\Bernese or D:\Bernese). After the execution of the Bernese 
- installers, the following folders are automatically created:
+ the root drive (e.g., C:\Bernese or D:\Bernese).
+ 
+ **Installation Verification:**
+ After installation, verify the following folders exist:
```

**Issue 2: Prerequisite Software Installation Under-Explained**

**Problem:** Lists software to install "before Bernese" but doesn't explain WHY or HOW they integrate.

**Recommended Addition:**

```markdown
### 5.1.1. Prerequisite Software

The following software must be installed BEFORE running the Bernese installers, as they 
are required for the BPE (Bernese Processing Engine) automation system:

**Software Requirements:**

| Software | Version | Purpose | Installation Notes |
|----------|---------|---------|-------------------|
| Perl | 5.24+ | BPE scripting language | Install from ActiveState, use default settings |
| gzip | Latest | Compress/decompress IGS products | Add to %PATH% variable |
| Hatanaka | Latest | RINEX compression | Add to %PATH% variable, verify with `rnx2crx -h` |
| FTPSSL | 0.40 | Secure FTP for IGS downloads | Install via `ppm install Net-FTPSSL` |

**Adding to %PATH% Variable (Windows 10/11):**
1. Search for "Environment Variables" in Start Menu
2. Click "Edit the system environment variables"
3. Click "Environment Variables" button
4. Under "System variables", select "Path" and click "Edit"
5. Click "New" and add the directory containing gzip.exe and crx2rnx.exe
6. Click OK on all dialogs
7. Restart Command Prompt to verify: `gzip --version`

**Verification Commands:**
```
perl --version     # Should show 5.24 or newer
gzip --version     # Should return version info
crx2rnx           # Should show usage info
```

If any command fails, installation was incomplete.
```

**Issue 3: No Troubleshooting for Common Installation Problems**

**Recommended Addition:**

```markdown
### 5.1.2. Common Installation Issues

**Problem:** Bernese installer fails with "Perl not found"
- **Solution:** Ensure Perl is installed FIRST, then rerun Bernese installer

**Problem:** BPE fails with "gzip: command not found"
- **Solution:** Verify gzip is in %PATH%, restart computer, test in new Command Prompt

**Problem:** FTPSSL module installation fails
- **Solution:** Run Command Prompt as Administrator, retry `ppm install Net-FTPSSL`

**Problem:** "Access Denied" when creating Campaign folders
- **Solution:** Install Bernese in directory where user has write permissions (not C:\Program Files)

For complex installation issues, consult:
- BERN52 Solutions and Updates (\\server\GPS\GPS Processing\02 Guide)
- Bernese FAQ: https://www.bernese.unibe.ch/faq/
- Project technical lead
```

---

### **Section 5.2: Campaign Setup** ✓ GOOD

**Content Quality:** 8/10

**Strengths:**
- Clear step-by-step instructions
- Good screenshots of interface
- Explains purpose of each subfolder
- Notes about Campaign naming constraints

**Issues Identified:**

### **Issue 1: No Validation Step**

**Problem:** After creating Campaign, user doesn't verify it worked.

**Recommended Addition after Step 5.2.4:**

```markdown
5.2.4.1. Verify Campaign Creation

Navigate to C:\Bernese\GPSDATA\CAMPAIGN52\PHIVOLCS\ using File Explorer. 
Confirm all 11 subfolders were created:

☑ ATM   ☑ BPE   ☑ GRD   ☑ OBS   ☑ ORB   ☑ ORX  
☑ OUT   ☑ RAW   ☑ SOL   ☑ STA

If any folders are missing:
1. Check for error messages in Bernese status bar
2. Verify disk space is available (>10GB recommended)
3. Confirm user has write permissions to GPSDATA folder
4. Rerun Campaign > Create new campaign
```

### **Issue 2: Session Table Not Explained**

**Problem:** Step 5.2.5 creates SESSIONS.SES but never explains what it's used for.

**Recommended Addition:**

```diff
5.2.5. Create a session table by selecting Campaign > Edit session table. The
default SESSION TABLE panel for a daily session will be displayed. 
+ 
+ **About Session Tables:** The SESSIONS.SES file defines how your observation data is 
+ divided into processing intervals. For daily processing, each session = 1 calendar day. 
+ The default settings (24-hour sessions starting at 00:00 UTC) are appropriate for most 
+ applications.
+ 
+ **When to Modify:** Advanced users may create custom session definitions (e.g., 
+ 3-hour sessions for kinematic processing, multi-day sessions for campaigns). For routine 
+ processing, use the default.
+ 
Click Save or press Ctrl + S to save the Session Table. This will produce a SESSIONS.SES
file inside the STA folder.
```

---

### **Section 5.3: Preparation of Campaign Files** ⚠️ NEEDS IMPROVEMENT

**Content Quality:** 7/10

**Critical Issues:**

### **Issue 1: No Overview of 8 Required Files**

**Problem:** User doesn't understand the big picture before diving into creation steps.

**Recommended Addition (new subsection before 5.3.1):**

```markdown
### 5.3.0. Overview: The 8 Essential Campaign Files

Before processing, Bernese requires detailed information about your stations. This 
information is stored in 8 files, all located in the Campaign's STA folder:

| File | Full Name | Purpose | Generated How |
|------|-----------|---------|---------------|
| .STA | Station Information | Receiver/antenna types, dates | RNX2STA (from RINEX headers) |
| .CRD | Coordinates | Approximate XYZ positions | RXOBV3 (from RINEX headers) |
| .ABB | Abbreviations | Site name lookup table | RXOBV3 (auto-generated) |
| .ATL | Atmospheric Tidal Loading | Atmospheric pressure corrections | GRDS1S2 (from CRD) |
| .PLD | Plate Definition | Tectonic plate assignments | EDITPLD (manual assignment) |
| .VEL | Velocities | Expected station motion | NUVELO (from CRD + PLD) |
| .CLU | Cluster | Station grouping for processing | EDITCLU (usually all in cluster 1) |
| .BLQ | Ocean Tide Loading | Ocean tidal corrections | Web service (external) |

**Processing Flow:**
```
RINEX files → STA + CRD + ABB → ATL
              CRD + PLD → VEL
              CRD → CLU
              CRD → BLQ (via web service)
```

**Important:** These files must be created IN ORDER as dependencies exist. Follow 
sections 5.3.1 through 5.3.10 sequentially.

**File Naming Convention:** All 8 files should use the same name as your Campaign 
(e.g., PHIVOLCS.STA, PHIVOLCS.CRD, etc.) for consistency and easy identification.
```

---

### **Issue 2: Critical Step Missing Context**

**Problem:** Step 5.3.1 says "Copy RINEX files to RAW folder" but doesn't explain WHY or verify files are correct.

**Recommended Revision:**

```diff
5.3.1. Open File Explorer (or your preferred file manager like Total Commander).
Manually create a folder in the DATAPOOL directory. Name this folder with the
same name as the Campaign name. Copy the RINEX observation files to the
folder you created.

+ **About DATAPOOL Organization:**
+ DATAPOOL serves as your master archive of all RINEX data. The Campaign-named 
+ subfolder (e.g., DATAPOOL\PHIVOLCS) allows you to maintain separate datasets for 
+ different processing campaigns without mixing files.
+ 
+ **File Requirements:**
+ - Files must be RINEX V2 format (extension .YYo)
+ - Include both local stations AND IGS reference stations (if available)
+ - Files should be for the same date range
+ - Verify files are not 0 bytes (corrupted)
+ 
+ Example DATAPOOL structure:
+ ```
+ DATAPOOL\
+ ├── PHIVOLCS\
+ │   ├── MAR21540.24o
+ │   ├── ALCO1540.24o
+ │   ├── S01R1540.24o  ← IGS station
+ │   └── ...
+ ```

5.3.2. To set the starting date of the Campaign session, go to the Bernese
interface and click on Configure > Set session. [...]

+ **Important:** Choose the date of your EARLIEST available RINEX file. This 
+ establishes the reference date for creating the coordinate files.
```

---

### **Issue 3: Multi-Step Procedures Need Validation Checkpoints**

**Problem:** Steps 5.3.4-5.3.10 create files but never verify they're correct until much later.

**Recommended Addition after each major file creation:**

**After Step 5.3.4 (STA file):**

```markdown
5.3.4.4. Verify the STA File

Open PHIVOLCS.STA with Notepad++ and check:
- ☑ Each site appears with correct 4-character code
- ☑ Receiver and antenna types match your equipment
- ☑ Dates are in correct format (YYYY MM DD HH MM SS)
- ☑ No duplicate entries (same site with same date)

**Common Issues:**
- Site code shows as "****" → RINEX marker name was empty
- Antenna type shows as "UNKNOWN" → RINEX header incomplete, edit manually
- Dates show as "0000 00 00" → RINEX time stamps corrupted

If errors are found, you can manually edit the STA file or regenerate from corrected RINEX.
```

**After Step 5.3.5 (CRD and ABB files):**

```markdown
5.3.5.5. Verify CRD and ABB Files

**Check PHIVOLCS.CRD:**
- Open with Notepad++ and verify approximate coordinates are reasonable
- Coordinates should be in meters (XYZ values ~6 million for typical locations)
- Each site should have one entry with "A" flag (Adjusted) or "U" (Unadjusted)

Example valid entry:
```
  NUM  STATION NAME           X (M)         Y (M)         Z (M)     FLAG
  001  MAR2                -3045123.4567   5123456.7890   1234567.8901  A
```

**Check PHIVOLCS.ABB:**
- Each site should have one line: `MAR2  001`
- Numbers should be sequential (001, 002, 003...)
- No duplicate site codes

**Red Flags:**
- Coordinates all at (0, 0, 0) → RINEX headers missing position
- Negative X, Y, Z values in wrong magnitude → hemisphere error
```

---

### **Issue 4: External Dependencies Not Clearly Marked**

**Problem:** Step 5.3.10 requires internet access and external web service, but this isn't flagged upfront.

**Recommended Addition at start of 5.3.10:**

```markdown
5.3.10. Create the Ocean Tide Loading Coefficients (BLQ) File. This is the only
file created outside of Bernese.

⚠️ **Prerequisites for this step:**
- Active internet connection
- Email address to receive results
- 30-60 minutes wait time for email response

**Note:** If internet is unavailable, you can use a template BLQ file from a previous 
campaign and manually add new sites using the same web service at a later time. BLQ 
coefficients change minimally for nearby sites, but should be computed for each unique 
station location.
```

---

### **Issue 5: Critical Information Buried**

**Problem:** The note about copying files to REF52 (Step 5.3.11) is extremely important but formatted as a simple step.

**Recommended Revision:**

```diff
5.3.11. Go to the STA folder. Then, copy all eight Campaign files (STA, CRD,
ABB, ATL, PLD, VEL, CLU, and BLQ) and paste them into DATAPOOL\REF52.

+ **⚠️ CRITICAL STEP:** The DATAPOOL\REF52 folder serves as the master reference 
+ for all Campaign files. The BPE processing scripts will look here for station 
+ information. Failure to copy files to REF52 will cause processing errors.
+ 
+ **Verification:**
+ Navigate to DATAPOOL\REF52 and confirm all 8 files are present:
+ ```
+ REF52\
+ ├── PHIVOLCS.STA
+ ├── PHIVOLCS.CRD
+ ├── PHIVOLCS.ABB
+ ├── PHIVOLCS.ATL
+ ├── PHIVOLCS.PLD
+ ├── PHIVOLCS.VEL
+ ├── PHIVOLCS.CLU
+ └── PHIVOLCS.BLQ
+ ```
+ 
+ **Important:** Whenever you update any of these files (e.g., adding a new site), 
+ you must also update the corresponding file in REF52.
```

---

### **Section 5.4: BPE Setup** ⚠️ NEEDS CLARITY

**Content Quality:** 6/10

**Critical Issues:**

### **Issue 1: Insufficient Explanation of PCF Purpose**

**Problem:** User edits PHIVOL_REL.PCF without understanding what it does or why.

**Recommended Addition before 5.4.1:**

```markdown
### 5.4. BPE Setup

**About the BPE (Bernese Processing Engine):**
The BPE is Bernese's automation system that chains together multiple processing programs 
(scripts) to run sequentially. Instead of manually running 20+ programs for each session, 
the BPE executes them automatically using instructions from a Process Control File (PCF).

**About PHIVOL_REL.PCF:**
This file, customized for PHIVOLCS operations, defines:
- Which scripts to run (e.g., RINEX import, orbit download, coordinate estimation)
- Order of execution
- Parameters for each script
- File naming conventions
- Campaign-specific settings

**Why We Edit It:**
The PCF contains variables (V_ATLINF, V_BLQINF, etc.) that point to your Campaign files. 
These must match your Campaign name for the BPE to find the correct station information.
```

---

### **Issue 2: Editing Instructions Too Vague**

**Problem:** Step 5.4.2 says "Edit the default value" but doesn't show WHAT to look for.

**Recommended Revision:**

```diff
5.4.2. Click Next (or press Ctrl + N) until you reach the EDITPCF 4 panel. 
- Edit the default value for V_ATLINF, V_BLQINF, V_CRDINF, and V_RNXDIR and
- change it to the Campaign name. Click Save or press Ctrl + S.

+ Edit the default value for the following variables, changing them from the default 
+ values to your Campaign name (e.g., PHIVOLCS):
+ 
+ | Variable | Default Value | Change To | Purpose |
+ |----------|--------------|-----------|---------|
+ | V_ATLINF | EXAMPLE | PHIVOLCS | Atmospheric loading file |
+ | V_BLQINF | EXAMPLE | PHIVOLCS | Ocean loading file |
+ | V_CRDINF | EXAMPLE | PHIVOLCS | Coordinate file |
+ | V_RNXDIR | EXAMPLE | PHIVOLCS | RINEX directory in DATAPOOL |
+ 
+ **Before:**
+ ```
+ V_ATLINF = EXAMPLE
+ ```
+ 
+ **After:**
+ ```
+ V_ATLINF = PHIVOLCS
+ ```
+ 
+ Repeat for all four variables, then click Save or press Ctrl + S.
+ 
+ **Verification:** Look at the status bar at the bottom of the Bernese window. 
+ It should say "File saved successfully" or similar confirmation.
```

---

### **Issue 3: RNXGRA Settings Lack Context**

**Problem:** Step 5.4.3 shows different values for campaign vs. continuous but doesn't explain the RATIONALE.

**Recommended Addition:**

```markdown
**Why These Settings Differ:**

**Campaign surveys** typically have:
- Shorter observation durations (2-4 hours)
- More setup/teardown errors (antenna bumps)
- Variable data quality depending on field conditions
- → More lenient thresholds needed to include data

**Continuous stations** typically have:
- 24/7 operation with stable setup
- Consistent data quality
- More observations per session
- → Stricter thresholds to maintain quality standards

**Parameter Explanations:**

- **Minimum observations per file:** Too few observations indicate receiver didn't track 
  satellites properly (obstructed sky view, antenna problem). Campaign: 100 allows 
  3-hour sessions; Continuous: 200 ensures full-day coverage.

- **Maximum bad epochs:** An epoch is "bad" if most satellites have poor signal or cycle 
  slips. Campaign: 70 tolerates field conditions; Continuous: 10 flags equipment issues.

- **Max observations defining bad epoch:** If fewer than 3 satellites are tracked in an 
  epoch, it's considered bad. This threshold is the same for both because it's a 
  fundamental data quality requirement.

**Impact of Wrong Settings:**
- Too lenient → Poor quality data enters processing → Coordinate outliers
- Too strict → Good campaign data rejected → Missing time series gaps
```

---

### **Section 5.5: First BPE Processing** ⚠️ NEEDS IMPROVEMENT

**Content Quality:** 7/10

**Critical Issues:**

### **Issue 1: No Pre-Flight Checklist**

**Problem:** User jumps into processing without verifying prerequisites. If something is wrong, they won't know until BPE fails hours later.

**Recommended Addition (new subsection before 5.5.1):**

```markdown
### 5.5.0. Pre-Processing Checklist

Before running the BPE, verify all prerequisites are met. This saves time troubleshooting 
later.

**☑ Campaign Files Checklist:**
- [ ] All 8 Campaign files exist in both STA and DATAPOOL\REF52 folders
- [ ] RINEX files are in DATAPOOL\{CAMPAIGN}\ folder
- [ ] Session date (Configure > Set session) matches RINEX file dates
- [ ] Active Campaign selected (should show in Bernese status bar)
- [ ] PCF variables edited to match Campaign name (Section 5.4.2)
- [ ] RNXGRA settings configured (Section 5.4.3)

**☑ External Dependencies:**
- [ ] Internet connection active (for IGS downloads)
- [ ] FTP credentials configured (if required)
- [ ] Perl, gzip, Hatanaka installed and in PATH

**☑ Disk Space:**
- [ ] At least 5GB free space on C:\ drive
- [ ] SAVEDISK folder has write permissions

**If any item is unchecked, resolve before continuing.**

**Estimated Processing Time:**
- First session with IGS downloads: 2-4 hours
- Subsequent sessions: 30-60 minutes per session
```

---

### **Issue 2: Error Handling Completely Missing**

**Problem:** Step 5.5.1.5 shows success message but doesn't address what to do if files DON'T download.

**Recommended Addition after 5.5.1.5:**

```markdown
**Troubleshooting Failed Downloads:**

If the success message doesn't appear or log shows errors:

**1. Check Internet Connection:**
```bash
ping gdc.cddis.eosdis.nasa.gov
```
If no response, internet/firewall issue.

**2. Check FTP_DWLD Log File:**
Location: `CAMPAIGN\BPE\{YYDDD}0_000_000.LOG`

Common errors:
- `Connection refused` → CDDIS server temporarily down, retry in 1 hour
- `Login failed` → Check credentials in PCF file
- `File not found` → IGS products not yet available (wait 12-48 hours after session date)
- `FTPSSL module not found` → Perl module installation incomplete (see Section 5.1)

**3. Manual Download Alternative:**
If automated download fails repeatedly, proceed to Section 5.7 for manual download 
instructions via FileZilla.

**4. Verify Downloaded Files:**
Check these locations:
- IGS orbits: `DATAPOOL\IGS\igswwwwd.sp3.Z`
- IGS RINEX: `DATAPOOL\{CAMPAIGN}\{SITE}{DDD}0.{YY}o`

Files should be >0 bytes. If 0 bytes, download was incomplete.
```

---

### **Issue 3: Station Information Update (5.5.3) Critically Under-Explained**

**Problem:** This is one of the most complex procedures but has minimal guidance. Merging STA files incorrectly will break processing.

**Recommended Complete Rewrite of 5.5.3.1:**

```markdown
### 5.5.3.1. Updating STA File

The STA file must include information for BOTH your local stations AND IGS reference 
stations. This section combines them.

**Step-by-Step Process:**

**5.5.3.1.1.** Generate a temporary STA file from all RINEX (local + IGS):

Follow Step 5.3.4, but this time select ALL RINEX files in the RAW folder:
- Your local stations (MAR2, ALCO, etc.)
- IGS stations (S01R, AIRA, PIMO, etc.)

Name this file: `PHIVOLCS_TEMP.STA`

**5.5.3.1.2.** Open three files side-by-side in Notepad++:
1. `PHIVOLCS_TEMP.STA` (just created)
2. `PHIVOLCS.STA` (your original local stations file)
3. `IGS.STA` (master IGS reference from DATAPOOL\REF52)

**5.5.3.1.3.** Merge station information:

**For local stations (MAR2, ALCO, COTD, etc.):**
- Keep the information from `PHIVOLCS_TEMP.STA` (generated from your RINEX headers)
- These are authoritative for your equipment

**For IGS stations (S01R, AIRA, PIMO, etc.):**
- REPLACE the information from `PHIVOLCS_TEMP.STA` with the corresponding entries 
  from `IGS.STA`
- Why? IGS.STA contains complete, validated equipment history for reference stations
- PHIVOLCS_TEMP.STA only has partial information from the single RINEX file

**5.5.3.1.4.** Example of merging:

**Before (PHIVOLCS_TEMP.STA for S01R - INCOMPLETE):**
```
S01R  001 2019 01 01 00 00 00 2099 12 31 23 59 59 TRIMBLE NETR9       TRM59800.00
```

**After (copied from IGS.STA - COMPLETE):**
```
S01R  001 2011 07 14 00 00 00 2019 12 31 23 59 59 TRIMBLE NETR9       TRM59800.00
S01R  001 2020 01 01 00 00 00 2099 12 31 23 59 59 TRIMBLE NETR9       TRM115000.00
```
Notice the IGS.STA version includes equipment change information (antenna upgraded in 2020).

**5.5.3.1.5.** Save the merged result as `PHIVOLCS.STA`, overwriting the original.

**5.5.3.1.6.** Verify the merged file:
- Count total number of stations (should = local + IGS)
- Check that IGS stations have complete date ranges
- Ensure no duplicate lines for same station/date

**Alternative Method (Using STAMERGE):**
The document mentions using the STAMERGE program as an alternative. This is 
RECOMMENDED for beginners:

1. Service > Station information files > Merge station information files
2. Master station information file: `IGS`
3. Secondary station information file: `PHIVOLCS`
4. Station information file: `PHIVOLCS` (output)
5. Run

This automatically merges with priority to the master (IGS) file for conflicts.

**Common Mistakes:**
- ❌ Using PHIVOLCS_TEMP entries for IGS stations → Missing equipment history
- ❌ Forgetting to include IGS stations at all → Processing fails with "Reference station not found"
- ❌ Mixing up date formats (YYYY MM DD vs DD/MM/YYYY) → Parsing errors
```

---

### **Section 5.5.4: Full BPE Processing** ✓ GOOD

**Content Quality:** 8/10

**Strengths:**
- Clear instructions for running complete BPE
- Good explanation of output files
- Appropriate level of detail

**Suggested Enhancement:**

Add progress monitoring guidance:

```markdown
**Monitoring BPE Progress:**

While processing runs, you can monitor progress in real-time:

**1. Watch the BPE window:**
- Current script name displays in window title
- Progress bar shows session completion percentage
- Estimated time remaining updates every few minutes

**2. Check log files during processing:**
Navigate to `CAMPAIGN\BPE\` and look for newest .LOG files. Open with Notepad++ 
and search for:
- `ERROR` → Processing problem detected
- `WARNING` → Non-critical issue noted
- `successfully completed` → Script finished normally

**3. Common progress checkpoints:**
- Script 000 (FTP_DWLD): 10-20 minutes (downloads IGS products)
- Script 212 (RNXGRA): 2-5 minutes (quality checks RINEX)
- Script 514 (HELMCHK): 5-10 minutes (validates coordinates)
- Scripts 601-615 (GPSEST series): 30-60 minutes (main processing)

**Total expected time:** 2-4 hours for first session with 45 stations + IGS references.

**If Processing Seems Stuck:**
- Wait at least 30 minutes before interrupting (some scripts are slow)
- Check Task Manager: Is BPE.EXE or GPSEST.EXE using CPU?
- If CPU = 0% for >10 minutes, processing likely hung (see Section 5.5.4 for Kill procedure)
```

---

### **Section 5.5.5: Output Files** ⚠️ NEEDS IMPROVEMENT

**Content Quality:** 7/10

**Issues:**

### **Issue 1: Output Validation Not Explained**

**Problem:** Lists output files but doesn't tell user how to verify they're CORRECT.

**Recommended Addition:**

```markdown
### 5.5.5.1. Validating Processing Results

After BPE completes, verify results before proceeding:

**1. Check R2S$YSS+0.PRC (Processing Summary):**

Open file in Notepad++ and search for:
- `Processing finished normally` → Success indicator
- `Number of sites processed: XX` → Should match your expected count
- `RMS of post-fit residuals` → Should be <10mm for good solutions

**Red flags:**
- `FATAL ERROR` anywhere in file → Processing failed
- RMS >50mm → Poor quality solution, check data
- "No solution" for specific sites → Investigate those sites

**2. Check F1_$YSS+0.CRD (Final Coordinates):**

Open file and verify:
- All expected sites have coordinate entries
- Coordinate values are reasonable (compare to approximate values)
- No coordinates at (0, 0, 0) → Indicates failed solution
- Flag column shows:
  - `W` for IGS stations (weighted/fixed) ✓ Correct
  - `A` for local stations (adjusted) ✓ Correct
  - `U` (unadjusted) ⚠️ Indicates processing problem

**Example good CRD entry:**
```
  NUM  STATION NAME           X (M)         Y (M)         Z (M)     FLAG  SIGMA
  001  MAR2                -3045123.4567   5123456.7890   1234567.8901  A    0.003
```

**3. Coordinate Quality Checks:**

Compare final coordinates to approximate coordinates:
```
Final - Approximate = Difference
```

**Expected differences:**
- Horizontal (X, Y): 0.01-0.50 meters (1-50 cm) ✓ Normal
- Vertical (Z): 0.01-1.00 meters (1-100 cm) ✓ Normal
- >5 meters ⚠️ Investigate: Wrong approximate position or processing error
- >100 meters ❌ Fatal error: Wrong station or corrupted data

**4. Check for Missing Output:**

If any expected file is missing:
- Check corresponding .LOG file in BPE folder for errors
- Verify previous steps completed (chain dependency)
- Example: Missing F1_$YSS+0.NQ0 means GPSEST processing failed
```

---

### **Section 5.6: Routine Processing** ✓ GOOD

**Content Quality:** 8/10

**Strengths:**
- Clear distinction between daily processing and special cases
- Good organization of subsections
- Practical guidance for common tasks

**Suggested Enhancements:**

### **Issue 1: Section 5.6.2 (Updating Station Information) Needs Examples**

**Add after existing text:**

```markdown
**Example Scenarios:**

**Scenario 1: Antenna Height Changed During Campaign**

Log sheet shows antenna height changed mid-day:
- Morning session: 1.543 m
- Afternoon session: 1.678 m

**STA file update:**
```
Before:
MAR2  001 2024 06 01 00 00 00 2024 06 01 23 59 59 TRIMBLE NETR9       TRM115000.00

After:
MAR2  001 2024 06 01 00 00 00 2024 06 01 12 00 00 TRIMBLE NETR9       TRM115000.00
MAR2  001 2024 06 01 12 00 01 2024 06 01 23 59 59 TRIMBLE NETR9       TRM115000.00
```
Note: Times must not overlap (12:00:00 end, 12:00:01 start).

**Scenario 2: Receiver Replacement**

Receiver failed and was replaced on 2024-06-15:

```
Before:
MAR2  001 2024 01 01 00 00 00 2099 12 31 23 59 59 TRIMBLE NETR9 5700 TRM115000.00

After:
MAR2  001 2024 01 01 00 00 00 2024 06 14 23 59 59 TRIMBLE NETR9 5700 TRM115000.00
MAR2  001 2024 06 15 00 00 00 2099 12 31 23 59 59 TRIMBLE NETR9 5800 TRM115000.00
```

**Critical:** Always update STA file BEFORE processing data with new equipment. 
Failure to do so will cause Bernese to use wrong antenna models → coordinate errors.
```

---

### **Issue 2: Section 5.6.3 (Adding New Site) is Complex but Well-Structured**

**Suggested Addition - Add Troubleshooting Subsection:**

```markdown
### 5.6.3.7. Troubleshooting New Site Addition

**Problem:** BPE fails with "Site XXXX not found in abbreviation table"
- **Solution:** ABB file not updated. Repeat Step 5.6.3.4.2 and verify site appears in ABB.

**Problem:** Coordinate outliers for new site in first few sessions
- **Cause:** Approximate coordinates far from true position (>1km off)
- **Solution:** Run 2-3 more sessions. Coordinates will converge. If not, check:
  - Antenna setup (height, cable connections)
  - Sky obstructions (trees, buildings)
  - Reference station availability

**Problem:** "No valid observations for site XXXX"
- **Cause:** RINEX file empty or corrupted, or failed RNXGRA quality checks
- **Solution:** Check RNXGRA log (BPE folder, script 212). Look for rejection reason:
  - "Too few observations" → Re-observe site or adjust RNXGRA thresholds
  - "Excessive cycle slips" → Antenna problem, check connections
  - "Time span too short" → Session duration insufficient

**Problem:** New site processed but coordinates seem incorrect (>10m from expected)
- **Checklist:**
  - [ ] Correct RINEX file for this site? (Check marker name in header)
  - [ ] Antenna height entered correctly in STA file?
  - [ ] Site located in expected geographic region? (Not confused with another site)
  - [ ] IGS reference stations available for this session?
```

---

### **Section 5.7: Manual Download of External Inputs** ✓ EXCELLENT

**Content Quality:** 9/10

**Strengths:**
- Clear FTP credentials provided
- Well-organized tables showing file locations
- Good explanation of CODE vs. CDDIS products
- Helpful links to documentation

**Only Minor Issue:**

Add security note at the beginning:

```markdown
### 5.7. Manual Download of External Inputs

**When to Use Manual Download:**
- FTP_DWLD script consistently fails
- Processing historical data where automated download is unavailable
- Verifying that automated downloads are correct
- Internet connection is unstable (manual allows resume capability)

**Security Note:** The credentials provided (anonymous FTP with email password) are 
standard for public geodetic data archives. Your email is used only for server logs 
and you will not be contacted unless there are access issues.

**Download Tool Recommendations:**
- **FileZilla (GUI):** Best for occasional manual downloads, visual file browser
- **Total Commander (GUI):** Integrates well with file management workflow
- **wget/curl (Command-line):** Best for scripted bulk downloads

[Continue with existing content...]
```

---

## **Section 6: Procedure: Time Series** ⚠️ NEEDS IMPROVEMENT

### Overall Assessment: 7/10

**Strengths:**
- Good prerequisite documentation
- Clear step-by-step process
- Practical examples with screenshots
- Good explanation of outlier removal

**Critical Issues:**

---

### **Section 6.1: Prerequisites** ✓ GOOD

**Content Quality:** 8/10

**Suggested Addition:**

Specify Python package requirements:

```diff
6.1.1. Before proceeding, the following programs need to be installed on your
computer:
  ● Python - Downloadable at python.org.
+   Required version: 3.8 or newer
+   Required packages: Install via Command Prompt:
+   ```
+   pip install numpy pandas matplotlib scipy
+   ```
  ● MATLAB - Downloadable at mathworks.com.
+   Required version: R2018b or newer
+   Required toolboxes: Statistics and Machine Learning Toolbox
```

---

### **Section 6.2: Plotting of Final Coordinates** ⚠️ NEEDS CLARITY

**Content Quality:** 7/10

**Critical Issues:**

### **Issue 1: Batch File Functionality Not Explained**

**Problem:** Step 6.2.3 runs filter-fncrd.bat but doesn't explain what it does or how to verify success.

**Recommended Addition:**

```markdown
6.2.3. Run the filter-fncrd.bat by double-clicking the batch file to generate
FNYYDDD0.CRD files for each corresponding F1_YYDDD0.CRD files. This also
automatically creates an F1CRD folder and moves all the F1_YYDDD0.CRD
files into this folder.

**What filter-fncrd.bat Does:**
This script extracts only the local PHIVOLCS stations and IGS reference stations from 
each daily coordinate file, removing:
- Bernese internal stations
- Duplicate entries
- Processing metadata

This filtering reduces file size and speeds up subsequent plotting steps.

**Verification:**
After running, check:
- [ ] F1CRD folder created with all original F1_* files moved inside
- [ ] FN*.CRD files created in main folder (one per original F1_* file)
- [ ] FN files are smaller than F1 files (typically 10-50% of original size)

**If batch file fails:**
- Error: "Permission denied" → Close any Excel/Notepad++ files that have CRD files open
- Error: "File not found" → Verify F1_* files exist in current directory
- No FN files created → Check batch file with Notepad++, verify filter commands are correct
```

---

### **Issue 2: Reference Station Choice Not Well Explained**

**Problem:** Step 6.2.4.2 says to use S01R as reference, but doesn't explain implications or alternatives.

**Recommended Expansion:**

```markdown
6.2.4.2. When prompted to "Input the reference station", enter
"S01R". This site in Taiwan is used as the reference point for velocity
computations relative to the Eurasian Plate. 

+ **About Reference Station Selection:**
+ 
+ The reference station defines your velocity reference frame. All velocities will be 
+ computed RELATIVE to this station (i.e., velocity of reference station = 0).
+ 
+ **Why S01R?**
+ - Located on stable Chinese continental margin (minimal local deformation)
+ - Continuously operating since 2011 (long-term stability verified)
+ - High data quality and availability
+ - Represents stable Eurasia Plate motion
+ 
+ **Alternative Reference Stations:**
+ - **PIMO** (Manila Observatory): Use for Luzon-specific studies
+ - **IGS global network average**: Use for plate motion studies
+ - **Another PHIVOLCS site**: Use for relative baseline analysis
+ 
+ **Important:** Once chosen, use the SAME reference station for entire time series to 
+ maintain consistency. Changing reference stations will shift all velocities.
+ 
+ **If reference station data is missing:**
+ - Choose backup reference with similar characteristics
+ - Document the change in processing notes
+ - Expect slight velocity discontinuity at transition date

The resulting output is an ENU file [...]
```

---

### **Issue 3: Script Output Not Validated**

**Problem:** Steps 6.2.4-6.2.5 generate files but never verify they're correct before moving to plotting.

**Recommended Addition after 6.2.4.3:**

```markdown
6.2.4.4. Verify Script Outputs

**Check the ENU file:**
Open the ENU file with Notepad++ or Excel. Format should be:
```
SITE    DATE        EAST        NORTH       UP
MAR2    2024.0027   0.0234      0.0156     -0.0089
MAR2    2024.0055   0.0245      0.0162     -0.0091
...
```

**Validation checks:**
- [ ] All your sites are present (search for each 4-character code)
- [ ] Dates are sequential with no large gaps (missing data = missing CRD files)
- [ ] Coordinate values are in meters (typical range: -0.5 to +0.5 m)
- [ ] No "NaN" or empty values (indicates processing error)

**Check individual site files:**
A separate file should exist for each site (e.g., MAR2, ALCO, COTD...). Open one:
```
2024.0027    0.0234    0.0156   -0.0089
2024.0055    0.0245    0.0162   -0.0091
```

**Common issues:**
- Missing site files → Site not in FNYYDDD0.CRD files or script failed
- Empty site files → Site has no coordinate solutions
- Unrealistic coordinates (>10m from origin) → Reference frame issue or processing error
```

---

### **Section 6.2.6: Offsets File** ⚠️ NEEDS SIGNIFICANT EXPANSION

**Content Quality:** 6/10

**Critical Issue:** The offsets file is CRUCIAL for accurate velocity estimation but is barely explained.

**Recommended Complete Rewrite:**

```markdown
### 6.2.6. Prepare the Offsets File

The `offsets` file documents known coordinate discontinuities (jumps) that should NOT be 
included in velocity calculations. This file is critical for accurate velocity estimation.

**File Format:**
```
SITE  YYYY.DDDD  TYPE
MAR2  2023.9199  EQ
ALCO  2022.5123  CE
PIVS  2021.3456  VE
COTD  2020.1234  UK
```

Where:
- SITE = 4-character station code
- YYYY.DDDD = Decimal year of offset (YYYY + DOY/365.25)
- TYPE = Offset classification (see below)

**Offset Types:**

| Code | Type | Description | Example |
|------|------|-------------|---------|
| EQ | Earthquake | Coseismic displacement from tectonic event | M7.0 earthquake causes 50mm jump |
| VE | Volcanic Eruption | Magmatic intrusion or eruption-related deformation | Taal 2020 eruption |
| CE | Change of Equipment | Antenna or receiver replacement | Antenna height remeasured incorrectly |
| UK | Unknown | Offset detected but cause undetermined | Possible site disturbance |

**How to Identify Offsets:**

**1. Earthquake-related (EQ):**
- Cross-reference time series with USGS/PHIVOLCS earthquake catalog
- Look for sudden jumps (>10mm) coinciding with M5.0+ events within 200km
- Check if multiple nearby stations show coherent jumps (tectonic deformation)
- Example: 2019 Luzon M6.1 earthquake caused offsets at multiple stations

**2. Equipment changes (CE):**
- Check equipment deployment database (Section 3.2) for maintenance dates
- Look for coordinate jumps coinciding with field operations
- Vertical component most sensitive (antenna height changes)
- Horizontal offsets may indicate antenna centering errors

**3. Volcanic eruptions (VE):**
- Check PHIVOLCS volcano bulletins
- Look for inflation/deflation patterns around eruption dates
- Typically affects stations within 10-20km of volcano

**4. Unknown causes (UK):**
- Detected offset but no documented cause
- Possible sources: Monument instability, landslide, flooding, vandalism
- Requires field investigation

**Example: Creating an Offset Entry**

**Scenario:** MAR2 time series shows 35mm northward jump on 2023 DOY 336.

**Step 1:** Convert to decimal year
```
Decimal year = 2023 + (336 / 365.25) = 2023.9199
```

**Step 2:** Investigate cause
- Check USGS catalog: M6.3 earthquake occurred 2023-12-02 (DOY 336) 100km from MAR2
- Confirms earthquake-related offset

**Step 3:** Add to offsets file
```
MAR2  2023.9199  EQ
```

**Step 4:** Document
Add note to processing log: "MAR2 offset on 2023.9199 attributed to M6.3 Mindoro EQ"

**Maintaining the Offsets File:**

**When to update:**
- After major earthquakes affecting PHIVOLCS network
- After equipment maintenance campaigns
- When visual inspection of plots reveals obvious jumps
- After running MATLAB outlier detection (may suggest new offsets)

**Best practices:**
- Keep file sorted by SITE, then DATE
- Maintain separate backup copy
- Version control with Git (track history of changes)
- Document reasons in comments: `# MAR2 2023.9199 EQ - Mindoro M6.3`

**Impact on Velocity Calculation:**

Without offset documentation:
```
Linear fit includes jump → velocity appears artificially high/low
```

With proper offset documentation:
```
Fit computed separately before/after jump → accurate velocity
```

**Example visualization:**
[Would include figure showing time series with/without offset correction]

**Common Mistakes:**
- ❌ Forgetting to add recently detected offsets → Velocity errors
- ❌ Wrong decimal year calculation → Offset correction applied at wrong time
- ❌ Classifying equipment changes as earthquakes → Incorrect interpretation
- ❌ Not removing false offsets (outliers mistaken for real jumps) → Over-correction
```

---

### **Section 6.2.7: MATLAB Processing** ⚠️ NEEDS TROUBLESHOOTING

**Content Quality:** 7/10

**Issues:**

### **Issue 1: No Error Handling for MATLAB Issues**

**Recommended Addition after 6.2.7:**

```markdown
### 6.2.7.1. Troubleshooting MATLAB Processing

**Problem:** "Undefined function or variable 'plot'"
- **Cause:** MATLAB path not set correctly
- **Solution:** In MATLAB Command Window, type: `addpath(pwd)` and retry

**Problem:** "Error using load: Unable to read file 'ALCO'"
- **Cause:** Site file has wrong format or is empty
- **Solution:** Open site file in Notepad++, check format matches Step 6.2.4.4 validation

**Problem:** Script runs but no JPG files created
- **Cause:** File permissions issue or disk full
- **Solution:** Check disk space, verify write permissions in PLOTS folder

**Problem:** "Index exceeds array dimensions"
- **Cause:** Inconsistent data (date mismatches between files)
- **Solution:** Re-run plot_v2.py with debug mode to check data integrity

**Problem:** Velocities in output file are unrealistic (>100 mm/year)
- **Cause:** Offsets not properly documented, or insufficient data span
- **Solution:** 
  - Check offsets file is in correct folder
  - Verify at least 2 years of data (1 year minimum for rough estimates)
  - Visually inspect time series for undocumented jumps

**Problem:** "Warning: Unable to fit linear model"
- **Cause:** Too few data points (needs at least 10 epochs) or all same value
- **Solution:** Check if site has sufficient observations, may need longer time span
```

---

### **Section 6.3: Outlier Removal** ✓ GOOD

**Content Quality:** 8/10

**Strengths:**
- Clear workflow for interactive outlier identification
- Good use of Python script for visual selection
- Practical iteration approach

**Suggested Enhancements:**

### **Issue 1: Outlier Selection Criteria Not Defined**

**Recommended Addition after 6.3.2:**

```markdown
### 6.3.2.1. Outlier Identification Guidelines

**What qualifies as an outlier?**

Use these criteria when visually inspecting time series:

**Definite outliers (always remove):**
- Points >3σ (3 standard deviations) from linear trend
- Isolated points not part of any pattern
- Points known to be from bad processing (check BPE logs)
- Coordinates clearly wrong (e.g., 500mm jump for 1 day then return)

**Possible outliers (evaluate carefully):**
- Points 2-3σ from trend but form a cluster (may be real short-term signal)
- Points near equipment changes (check if real monument motion)
- Points during extreme weather (heavy rain, typhoons can cause multipath)

**Not outliers (keep):**
- Points part of seasonal pattern (annual/semi-annual signals)
- Points showing post-seismic relaxation (gradual decay after earthquake)
- Points showing slow slip event (multi-day coherent signal)
- Points consistent with nearby stations (network-wide signal)

**Decision Tree:**
```
Is point >3σ from trend?
├─ YES → Is it isolated or part of cluster?
│   ├─ Isolated → REMOVE (likely processing error)
│   └─ Cluster → Check nearby stations
│       ├─ Similar signal → KEEP (real deformation)
│       └─ Not in other stations → REMOVE (site-specific error)
└─ NO → KEEP
```

**Examples:**

**Example 1: Clear outlier**
```
2024.1234: 0.045m (all other points between -0.005 to +0.005)
→ REMOVE: Isolated, 9σ deviation
```

**Example 2: Seasonal signal (NOT outlier)**
```
Every summer: +10mm
Every winter: -10mm
→ KEEP: Annual thermal expansion pattern
```

**Example 3: Ambiguous case**
```
3 consecutive days with +8mm, then return to trend
→ CHECK: Look at nearby stations, weather records, equipment logs
→ If isolated to this site → REMOVE
→ If seen at multiple sites → KEEP (possible slow slip)
```

**Best Practice:** When in doubt, keep the point initially. You can always remove it 
later if velocity estimates look wrong.
```

---

### **Issue 2: Iteration Process Not Explained**

**Recommended Addition after 6.3.5:**

```markdown
### 6.3.6. Iteration and Convergence

Outlier removal is often an iterative process:

**Iteration 1:** Remove obvious outliers (>5σ)
→ Recompute velocities → Plot updated

**Iteration 2:** Remove moderate outliers (3-5σ) now visible
→ Recompute velocities → Plot updated

**Iteration 3:** Evaluate remaining 2-3σ points
→ Keep if justified, remove if unexplained

**Convergence criteria:**
Stop iterating when:
- RMS of residuals stabilizes (<2mm change between iterations)
- No more points exceed 3σ threshold
- Further removal would eliminate genuine deformation signals

**Typical iterations needed:** 2-3 for most stations, up to 5 for noisy sites

**Warning signs of over-removal:**
- >20% of data points removed → Check if real signal mistaken for noise
- Velocity changes by >50% after outlier removal → Re-evaluate outlier criteria
- Seasonal patterns disappear → May have removed genuine annual signal

**Documentation:**
Keep log of outliers removed and reason:
```
MAR2: Removed 2024.1234 (8σ outlier, BPE log shows processing failed)
ALCO: Removed 2023.4567 (isolated spike, equipment maintenance that day)
```
```

---

## **Cross-Cutting Issues**

### **1. Inconsistent Terminology**

**Issue:** Same concepts described with different terms across sections.

**Examples:**
- "Julian Day" vs "Julian Day of Year" vs "DOY" vs "DDD"
- "RINEX observation files" vs "RINEX files" vs "observation files"
- "Campaign folder" vs "Campaign directory" vs "Campaign"

**Recommendation:** Create a "Terminology Conventions" table in Section 3 and use consistently:

```markdown
**Standardized Terms Used in This Document:**

| Preferred Term | Synonyms (avoid) | Usage |
|----------------|------------------|-------|
| Julian Day of Year (DOY) | Julian Day, DDD, JJJ | Always use "DOY" after first mention |
| RINEX observation file | RINEX file, observation file | Specify "observation" to distinguish from navigation files |
| Campaign directory | Campaign folder, Campaign | Use "directory" for technical accuracy |
| Session | Day | Use "session" in Bernese context, "day" in calendar context |
```

---

### **2. Missing Cross-References**

**Issue:** Related procedures in different sections don't reference each other.

**Examples:**
- Section 4.5 (fixdatweek) should reference Section 4.3.3 (where to resume after fix)
- Section 5.6.3 (adding new site) should reference Section 4.3 (converting new site data)
- Section 6.3 (outlier removal) should reference Section 5.5.5 (checking processing quality)

**Recommendation:** Add "See also" boxes throughout:

```markdown
📌 **See Also:**
- Section 4.3: Converting raw data for the new site before processing
- Section 5.3.10: Generating BLQ coefficients for new coordinates
- Section 5.5.3: Updating station information files with IGS references
```

---

### **3. Insufficient "Why" Explanations**

**Issue:** Many procedures explain WHAT and HOW but not WHY, making it hard for users to adapt or troubleshoot.

**Examples needing "why" context:**
- Why copy files to REF52 folder? (BPE scripts look there)
- Why use S01R as reference? (Stable Eurasia Plate)
- Why create 8 separate station files? (Each serves different processing purpose)
- Why update STA file when equipment changes? (Antenna models affect coordinates)

**Recommendation:** Add "Why This Matters" callout boxes:

```markdown
💡 **Why This Matters:**
The STA file tells Bernese which antenna calibration model to use. If the antenna 
type is wrong, coordinates can be off by 10-20cm vertically. Equipment changes MUST 
be documented to maintain coordinate accuracy over time.
```

---

### **4. Error Messages Not Documented**

**Issue:** Common error messages never explicitly shown, making troubleshooting difficult.

**Recommendation:** Add appendix:

```markdown
## Appendix A: Common Error Messages

**"Station XXXX not found in CRD file"**
- **Meaning:** Bernese can't find coordinate information for this station
- **Cause:** Site not added to CRD file, or typo in site name
- **Solution:** Section 5.6.3 (Adding a new site)

**"GPS week number incorrect"**
- **Meaning:** RINEX file has wrong date stamp
- **Cause:** GPS week rollover issue in older receivers
- **Solution:** Section 4.5 (Troubleshooting GPS week rollover)

**"No valid observations for session"**
- **Meaning:** All RINEX files rejected by quality control
- **Cause:** Corrupted data, wrong RNXGRA thresholds, or receiver malfunction
- **Solution:** Check Section 5.4.3 (RNXGRA settings) and Section 4.2 (RINEX validation)

[Continue with 20-30 most common errors...]
```

---

### **5. No Quick Start Guide**

**Issue:** New users must read entire 62-page document before processing their first dataset.

**Recommendation:** Add Section 1.5: Quick Start Guide:

```markdown
## 1.5. Quick Start Guide (For Experienced Users)

**Already familiar with GNSS processing? Here's the workflow in 5 steps:**

**Step 1:** Convert raw data to RINEX (Section 4.3 or 4.4)
- Run `campaign_v5.py` or `continuous_v5.py`
- Input: Raw receiver files → Output: RINEX .YYo files

**Step 2:** Set up Bernese Campaign (Section 5.2-5.3, first time only)
- Create Campaign directory
- Generate 8 station files (STA, CRD, ABB, ATL, PLD, VEL, CLU, BLQ)

**Step 3:** Run BPE processing (Section 5.5 or 5.6.1)
- Configure session date
- Execute BPE from script 000 to 999
- Output: Daily coordinates in SAVEDISK

**Step 4:** Generate time series (Section 6.2)
- Extract coordinates with `filter-fncrd.bat`
- Run `plot_v2.py` to convert to ENU
- Run MATLAB `vel_line_v8.m` to plot and compute velocities

**Step 5:** Remove outliers (Section 6.3)
- Visually identify outliers with `outlier_input-site.py`
- Edit PLOT files
- Rerun MATLAB to get final velocities

**Typical time:** 4-6 hours for first campaign setup, 1-2 hours for routine daily processing.

**For detailed explanations, see the full sections referenced above.**
```

---

### **6. No Glossary of File Extensions**

**Issue:** Document uses many file extensions (.T01, .TGD, .CRD, .NQ0, etc.) without centralized reference.

**Recommendation:** Add Appendix B:

```markdown
## Appendix B: File Extension Reference

### Raw GNSS Data
| Extension | Format | Receiver Type | Description |
|-----------|--------|---------------|-------------|
| .T00, .T01, .T02, .T04 | Binary | Trimble | Proprietary raw observation format |
| .m00, .m01, .m## | MDB | Leica | Proprietary raw observation format |

### Intermediate Formats
| Extension | Format | Tool | Description |
|-----------|--------|------|-------------|
| .DAT, .TGD | Binary | runpkr00 | Trimble data converted to teqc-readable format |
| .YYo | ASCII | RINEX V2 | Standard observation file (YY = 2-digit year) |

### Bernese Formats
| Extension | Format | Program | Description |
|-----------|--------|---------|-------------|
| .CRD | ASCII | Various | Coordinate file (XYZ + station info) |
| .STA | ASCII | RNX2STA | Station information (equipment, dates) |
| .ABB | ASCII | RXOBV3 | Abbreviation/numbering table |
| .NQ0 | Binary | GPSEST | Normal equation file |
| .SNX | ASCII | ADDNEQ | SINEX format solution |
| .TRP, .TRO | ASCII | GPSEST | Tropospheric estimates |

### Processing Outputs
| Extension | Format | Purpose | Description |
|-----------|--------|---------|-------------|
| .PRC | ASCII | BPE summary | Processing log (human-readable) |
| .LOG | ASCII | BPE scripts | Detailed log for each script execution |
| .OUT | ASCII | GPSEST | Program output (residuals, statistics) |
| .SUM | ASCII | GPSXTR | Summary of GPSEST output |

### Time Series
| Extension | Format | Tool | Description |
|-----------|--------|------|-------------|
| .JPG | Image | MATLAB | Time series plot |
| (none) | ASCII | plot_v2.py | Site-specific ENU coordinates |
```

---

## **Section-Specific Grammar & Style Issues**

### **Section 4.1.3.c (RINEX Naming)**

**Issue:** Grammatical error in file type description.

```diff
- o = file type indicating raw observation data, containing
-     measurements such as time, pseudo-range, and carrier
-     phase.

+ o = file type indicating raw observation data, containing
+     measurements such as time, pseudorange, and carrier
+     phase
```
**Note:** "pseudo-range" should be one word "pseudorange" (standard GNSS terminology).

---

### **Section 5.3.10.5 (BLQ File Example)**

**Issue:** Confusing instruction about pasting email content.

```diff
5.3.10.5. Copy everything from the e-mail after the END HEADER line.
Replace the content after the END HEADER line in the EXAMPLE.BLQ
file. Refer to the sample below.

EXAMPLE.BLQ file
$
$ END HEADER
$
- * paste the content from the e-mail *

+ [Paste the tidal loading coefficients from email here]
+ [Each station's data will be in a multi-line block]
+ [Example format:]
+   MAR2
+     $ Computed by M.S. Bos and H.-G. Scherneck
+     $ Ocean tide loading...
+     [coefficient data]

$ END TABLE
```

---

### **Section 5.5.4 (Kill Button)**

**Issue:** Passive voice makes instruction unclear.

```diff
Should the need arise, you can terminate the BPE processing immediately by
- clicking the "Kill" button on the lower left side of the window, or closing the
- window using the "X" button on the upper right.

+ **To stop BPE processing immediately:**
+ 1. Click the "Kill" button (lower left of BPE window), OR
+ 2. Click the "X" button (upper right of window)
```

---

### **Section 6.2.4.2 (Reference Station)**

**Issue:** Run-on sentence, unclear pronoun reference.

```diff
- This site in Taiwan is used as the reference point for velocity
- computations relative to the Eurasian Plate. Note that the choice of
- reference station for velocity computations is not fixed, as other stations
- may be used based on needs or the intended analysis.

+ This site, located in Taiwan, serves as the reference point for computing 
+ velocities relative to the Eurasian Plate. 
+ 
+ **Note:** The choice of reference station is not fixed. Other stations may be 
+ used depending on your analysis goals or geographic focus.
```

---

## **Overall Document Recommendations**

### **Priority 1: Add Missing Content (Critical)**

1. **Decision flowcharts** for workflow branches (manual vs. automated, Trimble vs. Leica)
2. **Validation checkpoints** after each major file creation step
3. **Error handling guidance** throughout all procedural sections
4. **Troubleshooting appendix** with common errors and solutions
5. **Quick reference appendix** for commands and file extensions

---

### **Priority 2: Improve Clarity (High)**

1. **Expand "why" explanations** for non-obvious procedures
2. **Add cross-references** between related sections
3. **Standardize terminology** (create style guide table)
4. **Include more examples** of correct vs. incorrect outputs
5. **Add "common mistakes" callouts** throughout

---

### **Priority 3: Enhance Usability (Medium)**

1. **Quick start guide** for experienced users (Section 1.5)
2. **Glossary of file extensions** (Appendix B)
3. **Command quick reference** (Appendix C)
4. **Checklist templates** for routine procedures (Appendix D)
5. **Troubleshooting decision trees** (Appendix E)

---

### **Priority 4: Polish (Low)**

1. Fix minor grammatical issues throughout
2. Standardize screenshot formatting
3. Improve table readability (consistent column widths)
4. Add page numbers and running headers (if PDF)
5. Create comprehensive index (if PDF)

---

## **Suggested New Appendices**

### **Appendix C: Command Quick Reference**

```markdown
## Appendix C: Command Quick Reference

### RINEX Conversion Commands

**Trimble to RINEX (via runpkr00 + teqc):**
```bash
# Step 1: Convert to TGD
runpkr00 -g -d rawfile.T01

# Step 2: Convert to RINEX
teqc -tr d -O.r NAME -O.o OPERATOR -O.ag AGENCY \
     -O.dec 30 -O.mo SITE -O.mn SITE -O.pe 1.543 0 0 \
     +C2 +obs + -tbin 1d SITE rawfile.tgd
```

**Leica to RINEX (via teqc):**
```bash
teqc -lei mdb -O.r NAME -O.o OPERATOR -O.ag AGENCY \
     -O.dec 30 -O.mo SITE -O.mn SITE -O.pe 1.543 0 0 \
     +C2 +obs + -tbin 1d SITE SITE*.m??
```

### Bernese Navigation

**Keyboard Shortcuts:**
- `Ctrl + N`: Next panel
- `Ctrl + R`: Run program
- `Ctrl + S`: Save
- `Ctrl + Q`: Quit program
- `F1`: Online help

**Common Menu Paths:**
- Create Campaign: Campaign > Create new campaign
- Import RINEX: RINEX > Import RINEX to Bernese format > Observation files
- Run BPE: BPE > Start BPE processing
- Set Session: Configure > Set session

### File Locations

**Input Files:**
- Raw data: `DATAPOOL\{CAMPAIGN}\`
- RINEX ready for import: `CAMPAIGN\RAW\`
- Station files: `CAMPAIGN\STA\` and `DATAPOOL\REF52\`

**Output Files:**
- Processing logs: `CAMPAIGN\BPE\`
- Final coordinates: `GPSDATA\SAVEDISK\YYYY\STA\`
- Normal equations: `GPSDATA\SAVEDISK\YYYY\SOL\`
```

---

### **Appendix D: Processing Checklists**

```markdown
## Appendix D: Processing Checklists

### First-Time Campaign Setup Checklist

- [ ] Bernese 5.2 installed with all prerequisites (Section 5.1)
- [ ] Campaign directory created (Section 5.2)
- [ ] 11 subfolders exist in Campaign directory
- [ ] RINEX files collected and converted (Section 4)
- [ ] Session date configured (Configure > Set session)
- [ ] 8 station files created (Section 5.3):
  - [ ] STA - Station information
  - [ ] CRD - Coordinates
  - [ ] ABB - Abbreviations
  - [ ] ATL - Atmospheric loading
  - [ ] PLD - Plate definition
  - [ ] VEL - Velocities
  - [ ] CLU - Cluster
  - [ ] BLQ - Ocean loading
- [ ] All 8 files copied to DATAPOOL\REF52
- [ ] PCF variables edited (Section 5.4.2)
- [ ] RNXGRA settings configured (Section 5.4.3)
- [ ] Internet connection active for IGS downloads
- [ ] At least 5GB disk space available

### Daily Processing Checklist

- [ ] New RINEX files in DATAPOOL\{CAMPAIGN}\
- [ ] Session date set correctly
- [ ] IGS products available for date (or will download automatically)
- [ ] Disk space sufficient (>1GB per session)
- [ ] Previous session completed successfully (check SAVEDISK)
- [ ] Run BPE from script 000 to 999
- [ ] Verify output files created in SAVEDISK
- [ ] Check processing log for errors
- [ ] Archive results if processing successful

### Time Series Generation Checklist

- [ ] Final coordinate files (F1_*) collected from SAVEDISK
- [ ] filter-fncrd.bat executed successfully
- [ ] FN* files created
- [ ] plot_v2.py executed, ENU files generated
- [ ] Reference station selected (e.g., S01R)
- [ ] 123 file lists all sites for plotting
- [ ] offsets file updated with recent events
- [ ] MATLAB vel_line_v8.m executed
- [ ] JPG plots generated for all sites
- [ ] Velocities file created
- [ ] Outliers file reviewed
- [ ] Visual inspection of all plots completed
- [ ] Outliers removed and reprocessed if needed
```

---

## **Final Recommendations Summary**

### **For Immediate Action:**

1. **Add decision flowcharts** at Section 4.0 and 5.0 (workflow navigation)
2. **Insert validation checkpoints** after Steps 5.3.4, 5.3.5, 5.3.11, 5.5.5, 6.2.4
3. **Expand Section 4.5** with general troubleshooting table
4. **Rewrite Section 6.2.6** with comprehensive offsets guidance
5. **Add Appendices** A-D (errors, glossary, commands, checklists)

### **For Next Revision:**

1. **Standardize terminology** using style guide table
2. **Add cross-references** between related sections
3. **Include more examples** of correct vs. incorrect outputs
4. **Expand "why" context** for non-obvious procedures
5. **Create Quick Start Guide** (Section 1.5)

### **For Long-Term Improvement:**

1. **Convert to web-based documentation** (searchable, versioned)
2. **Add video tutorials** for complex procedures
3. **Create interactive troubleshooter** (decision tree web app)
4. **Develop automated validation scripts** to check file integrity
5. **Integrate with automation roadmap** (Section 1 of separate document)

---

## **Document Quality Metrics**

| Criterion | Current Score | Target Score | Gap |
|-----------|---------------|--------------|-----|
| Completeness | 8/10 | 10/10 | Missing error handling, validation steps |
| Clarity | 7/10 | 9/10 | Needs more "why" context, examples |
| Consistency | 7/10 | 10/10 | Terminology varies, detail level uneven |
| Usability | 7/10 | 9/10 | Needs quick ref, better navigation |
| Accuracy | 9/10 | 10/10 | Technical content correct, minor typos |
| **Overall** | **7.6/10** | **9.6/10** | **Strong foundation, needs polish** |

---

## **Acknowledgment**

This is an **excellent technical document** that demonstrates deep domain expertise and thoughtful organization. The core content is technically sound and comprehensive. The recommended improvements focus on:

1. Making the document more **accessible** to new users
2. Adding **defensive guidance** (error handling, validation)
3. Improving **discoverability** (cross-refs, appendices)
4. Enhancing **pedagogical value** (examples, context)

With these enhancements, this work instruction will become a **best-in-class reference** for GNSS processing operations.

---

**Reviewed by:** Alfie R. Pelicano  
**Review Date:** October 22, 2025  
**Review Type:** Technical Content, Grammar, Flow  
**Recommendation:** **APPROVE with revisions** (Priority 1 items should be addressed before next printing)