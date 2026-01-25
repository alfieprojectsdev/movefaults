#!/bin/bash
#
# This script fixes the corrupted Git repository by creating a "clean room"
# copy of the project and re-initializing a fresh Git history.
#
# To be run from your home directory or any directory outside the project.
#

set -e

# --- Configuration ---
OLD_REPO="/home/finch/repos/movefaults"
NEW_REPO="/home/finch/repos/movefaults_clean"

echo "--- Creating a fresh, clean copy of the project source files ---"
if [ -d "$NEW_REPO" ]; then
    echo "Warning: Clean directory '$NEW_REPO' already exists. Removing it."
    rm -rf "$NEW_REPO"
fi
mkdir -p "$NEW_REPO"

# Use rsync to copy everything EXCEPT the broken .git directory
rsync -av --exclude='.git' "$OLD_REPO/" "$NEW_REPO/"
echo "Source files copied to '$NEW_REPO'."
echo ""

echo "--- Initializing a new, clean Git repository in '$NEW_REPO' ---"
cd "$NEW_REPO"
git init
git add .
git commit -m "Initial commit of unified monorepo"
echo "New repository created successfully."
echo ""

echo "--- SCRIPT COMPLETE ---"
echo ""
echo "A clean version of your repository has been created at: ${NEW_REPO}"
echo "You can now push this clean repository to GitHub."
echo ""
echo "Please run these commands:"
echo "---------------------------------------------------------------------"
echo "cd ${NEW_REPO}"
echo "git remote add origin git@github.com:alfieprojectsdev/movefaults.git"
echo "git branch -M main"
echo "git push -u origin main"
echo "---------------------------------------------------------------------"
echo ""
echo "After you have successfully pushed and verified the repository on GitHub,"
echo "you can safely delete the old, broken directory with: rm -rf ${OLD_REPO}"
