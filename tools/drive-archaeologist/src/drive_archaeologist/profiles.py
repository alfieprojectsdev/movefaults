"""
Default classification profiles for Drive Archaeologist.
Maps categories to file extensions.
"""

# Prioritize specific formats (e.g., geospatial over generic binary)
# Order can matter if a file could fit multiple categories, though the
# current implementation uses a simple dictionary lookup.

CLASSIFICATION_PROFILES = {
    # --- Geospatial & Scientific Data ---
    "GNSS Data": [
        ".gns", ".gps", ".nav", ".obs", ".rinex", ".crx", ".crinex", ".rnx",
        ".22o", ".21o", ".20o", ".19o", ".18o", ".17o", ".16o", ".15o",
        ".22n", ".21n", ".20n", ".19n", ".18n", ".17n", ".16n", ".15n",
        ".22g", ".21g", ".20g", ".19g", ".18g", ".17g", ".16g", ".15g",
        ".sp3", ".clk", ".ion", ".bia", ".erp", ".snx",
    ],
    "GIS Data": [
        ".shp", ".shx", ".dbf", ".prj", ".sbn", ".sbx", ".gpx", ".kml", ".kmz",
        ".geojson", ".topojson", ".gml", ".gpkg", ".mbtiles", ".fgb", ".pmtiles"
    ],
    "Seismic Data": [
        ".segy", ".sgy", ".mseed", ".sac",
    ],
    "Scientific & Numeric Data": [
        ".csv", ".tsv", ".json", ".xml", ".hdf5", ".h5", ".nc", ".fits",
        ".dat", ".log",
    ],

    # --- Standard Media Formats ---
    "Image": [
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
        ".svg", ".heic", ".heif", ".raw", ".cr2", ".nef", ".arw", ".dng",
        ".psd", ".ai", ".eps",
    ],
    "Video": [
        ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".mpg",
        ".mpeg", ".m4v",
    ],
    "Audio": [
        ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma",
    ],

    # --- Documents & Text ---
    "Document": [
        ".pdf", ".doc", ".docx", ".odt", ".rtf", ".wpd",
        ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp",
    ],
    "Text": [
        ".txt", ".md", ".markdown", ".html", ".htm", ".rtf", ".tex",
    ],
    "Ebook": [
        ".epub", ".mobi", ".azw3",
    ],

    # --- Code & Development ---
    "Source Code": [
        ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
        ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".kts", ".sh", ".bash",
        ".ps1",
    ],
    "Web Frontend": [
        ".html", ".htm", ".css", ".scss", ".sass", ".less", ".js", ".jsx",
        ".ts", ".tsx", ".vue",
    ],
    "Configuration": [
        ".yaml", ".yml", ".ini", ".cfg", ".conf", ".toml",
        ".editorconfig", ".gitignore", ".gitattributes",
    ],
    "Database": [
        ".db", ".sqlite", ".sqlite3", ".sql", ".dump", ".bak",
    ],

    # --- Compressed Archives ---
    "Archive": [
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz",
    ],

    # --- System & Executable Files ---
    "Executable": [
        ".exe", ".msi", ".bat", ".com", ".sh",
    ],
    "Application Library": [
        ".dll", ".so", ".dylib",
    ],
    "Disk Image": [
        ".iso", ".img", ".dmg", ".vhd", ".vhdx",
    ],

    # --- Other ---
    "Font": [
        ".ttf", ".otf", ".woff", ".woff2",
    ],
}
