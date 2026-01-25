#!/bin/bash
#
# This script cleans the project by removing the oversized .git directory,
# creating a comprehensive .gitignore, and re-initializing the repository
# to exclude large data files.
#
# To be run from the /home/finch/repos/movefaults directory.
#

set -e

MONOREPO_ROOT="/home/finch/repos/movefaults"
cd "$MONOREPO_ROOT"

echo "--- Removing oversized .git directory ---"
rm -rf .git
echo "Old Git history removed."
echo ""

echo "--- Creating a comprehensive .gitignore ---"
cat <<EOF > .gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
ENV/
env/
pip-wheel-metadata/
.pytest_cache/
.mypy_cache/
.ruff_cache/
build/
dist/
*.egg-info/
htmlcov/
*.bak

# OS / Editor
.DS_Store
.AppleDouble
.LSOverride
.vscode/
.idea/
*.swp
*.swo
*~
.trash/
Thumbs.db

# Large File Types & Data
*.pdf
*.zip
*.7z
*.gz
*.rar
*.exe
*.mp4
*.nc
*.grad
*.kin
*.xlsx
*.xlsm
*.gmt
*.cpt

# Ignore asset folders from saved HTML pages
*_files/

# Specific large files/dirs to ignore if they sneak past extensions
analysis/06 Ku-en Dislocation Model/04 GMT/PH_topo.grad
analysis/06 Ku-en Dislocation Model/04 GMT/PH_topo.nc
analysis/08 Bootstrapping/boostrap.mp4

# Exemption for critical documentation PDFs (if any)
# You can uncomment and specify paths to PDFs that MUST be in the repo.
# !docs/bern52/BERN52_Guide.pdf

EOF
echo ".gitignore created."
echo ""

echo "--- Re-initializing a clean Git repository ---"
git init
git add .
git commit -m "Initial commit of monorepo structure (cleaned)"
echo "New clean repository initialized and initial commit created."
echo ""

echo "--- REPO CLEANUP COMPLETE ---"
echo ""
echo "Your repository is now a manageable size and ready to be pushed."
echo "Please follow the previous instructions to create a new repository on GitHub and push this clean version."
