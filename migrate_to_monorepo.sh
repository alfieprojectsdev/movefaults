#!/bin/bash
#
# This script migrates drive-archaeologist and vadase-rt-monitor into the
# movefaults project to create a unified monorepo.
#
# !!! IMPORTANT !!!
# This script MUST be run from the /home/finch/repos/ directory.
#

set -e

# --- Configuration ---
MONOREPO_ROOT="/home/finch/repos/movefaults"
ARCHAEOLOGIST_SRC="/home/finch/repos/drive-archaeologist"
VADASE_SRC="/home/finch/repos/vadase-rt-monitor"

echo "--- Preparing 'movefaults' as a Git repository ---"
cd "$MONOREPO_ROOT"
git init
git add .
git commit -m "Initial commit of existing movefaults project"
echo "Git repository initialized."
echo ""

echo "--- Scaffolding monorepo directories ---"
mkdir -p packages services tools
mkdir -p docs/drive-archaeologist docs/vadase-rt-monitor
echo "Directories created."
echo ""

echo "--- Migrating project files ---"
# Use a temporary directory to avoid mv conflicts if script is run from wrong place
TMP_ARCHAEOLOGIST=$(mktemp -d)
TMP_VADASE=$(mktemp -d)
mv ${ARCHAEOLOGIST_SRC}/* "$TMP_ARCHAEOLOGIST"
mv ${VADASE_SRC}/* "$TMP_VADASE"
rm -rf "$ARCHAEOLOGIST_SRC" "$VADASE_SRC" # Remove the now-empty source directories

mv "$TMP_ARCHAEOLOGIST"/* "${MONOREPO_ROOT}/tools/drive-archaeologist/"
mv "$TMP_VADASE"/* "${MONOREPO_ROOT}/services/vadase-rt-monitor/"
rm -rf "$TMP_ARCHAEOLOGIST" "$TMP_VADASE"
echo "Moved 'drive-archaeologist' to tools/"
echo "Moved 'vadase-rt-monitor' to services/"
echo ""

echo "--- Consolidating documentation ---"
# Check if docs directories exist before moving
if [ -d "${MONOREPO_ROOT}/tools/drive-archaeologist/docs" ]; then
    mv "${MONOREPO_ROOT}/tools/drive-archaeologist/docs/"* "${MONOREPO_ROOT}/docs/drive-archaeologist/"
    rm -rf "${MONOREPO_ROOT}/tools/drive-archaeologist/docs"
fi
if [ -d "${MONOREPO_ROOT}/services/vadase-rt-monitor/docs" ]; then
    mv "${MONOREPO_ROOT}/services/vadase-rt-monitor/docs/"* "${MONOREPO_ROOT}/docs/vadase-rt-monitor/"
    rm -rf "${MONOREPO_ROOT}/services/vadase-rt-monitor/docs"
fi
echo "Documentation merged into root 'docs/' directory."
echo ""

echo "--- Creating unified .gitignore ---"
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
EOF
echo ".gitignore created."
echo ""

echo "--- Unifying Python dependencies ---"
# Backup and remove old pyproject.toml files
mv "${MONOREPO_ROOT}/tools/drive-archaeologist/pyproject.toml" "${MONOREPO_ROOT}/tools/drive-archaeologist/pyproject.toml.bak"
mv "${MONOREPO_ROOT}/services/vadase-rt-monitor/pyproject.toml" "${MONOREPO_ROOT}/services/vadase-rt-monitor/pyproject.toml.bak"

# Create a new root pyproject.toml
cat <<EOF > pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "move-faults-monorepo"
version = "0.1.0"
description = "Monorepo for the Philippine Open Geodesy Framework (POGF) and related tools."
requires-python = ">=3.11"
license = "MIT"
authors = [
    { name = "Alfie Pelicano", email = "alfieprojects.dev@gmail.com" },
]

dependencies = [
    # No global dependencies, define them per-project below
]

[project.optional-dependencies]
# Dependencies for the drive-archaeologist tool
drive-archaeologist = [
    # TODO: Copy dependencies from tools/drive-archaeologist/pyproject.toml.bak
    "jsonlines==3.1.0",
    "tqdm==4.64.1",
]

# Dependencies for the vadase-rt-monitor service
vadase-rt-monitor = [
    # TODO: Copy dependencies from services/vadase-rt-monitor/pyproject.toml.bak
    "asyncpg==0.27.0",
    "pynmea2==1.18.0",
    "PyYAML==6.0",
]

# Shared development dependencies
dev = [
    "pytest",
    "pytest-cov",
    "ruff",
    "mypy",
    "black",
    "uv",
]

[tool.ruff]
line-length = 88
select = ["E", "F", "W", "I"]

[tool.hatch.version]
path = "src/__init__.py"

[tool.hatch.envs.default]
dependencies = [
  "pytest",
  "pytest-cov",
]
EOF
echo "Root 'pyproject.toml' created."
echo "Old config files backed up as .bak. Please manually merge dependencies and then delete the .bak files."
echo ""

echo "--- Creating placeholder CI/CD workflow ---"
mkdir -p .github/workflows
cat <<'EOF' > .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint-and-format:
    name: Lint and Check Format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  test-drive-archaeologist:
    name: Test Drive Archaeologist
    runs-on: ubuntu-latest
    if: "contains(github.event.head_commit.message, 'ci:all') or contains(join(github.event.commits.*.message), 'ci:all') or ! (github.event_name == 'push' || github.event_name == 'pull_request') || contains(toJson(github.event.commits), 'tools/drive-archaeologist/')"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install uv
      - run: uv pip install ".[dev,drive-archaeologist]"
      - run: pytest tools/drive-archaeologist/tests

  test-vadase-rt-monitor:
    name: Test VADASE-RT Monitor
    runs-on: ubuntu-latest
    if: "contains(github.event.head_commit.message, 'ci:all') or contains(join(github.event.commits.*.message), 'ci:all') or ! (github.event_name == 'push' || github.event_name == 'pull_request') || contains(toJson(github.event.commits), 'services/vadase-rt-monitor/')"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install uv
      - run: uv pip install ".[dev,vadase-rt-monitor]"
      - run: pytest services/vadase-rt-monitor/tests

EOF
echo "Placeholder GitHub Actions workflow created at .github/workflows/ci.yml"
echo ""

echo "--- Finalizing migration commit ---"
git add .
git commit -m "feat: Migrate drive-archaeologist and vadase-rt-monitor into monorepo"
echo ""

echo "--- MIGRATION SCRIPT COMPLETE ---"
echo ""
echo "Next Steps:"
echo "1. Manually copy the dependencies from the .bak files into the root pyproject.toml."
echo "2. Once verified, delete the .bak files in the sub-project directories."
echo "3. Go to GitHub and create a new, empty repository (e.g., 'movefaults-monorepo')."
echo "4. Follow the instructions on GitHub to push an existing repository from the command line:"
echo "   cd ${MONOREPO_ROOT}"
echo "   git remote add origin <URL_from_GitHub>"
echo "   git branch -M main"
echo "   git push -u origin main"
