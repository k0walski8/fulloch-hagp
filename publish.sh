#!/bin/bash

# Configuration
PRIVATE_REPO_DIR=$(pwd)
PUBLIC_REPO_DIR="../fulloch" # Path to your local public repo clone
COMMIT_MSG="V1.0: $(date +'%Y-%m-%d')"

mkdir -p "$PUBLIC_REPO_DIR"

# 1. Check if public repo is clean
cd "$PUBLIC_REPO_DIR" || exit
if [[ -n $(git status -s) ]]; then
    echo "Error: Public repo has uncommitted changes. Please clean it first."
    exit 1
fi

# 2. Clean out old public files (except .git) to handle deletions
#    Use find to delete everything but .git directory
find . -maxdepth 1 -not -name '.git' -not -name '.' -exec rm -rf {} +

# 3. Export clean snapshot from Private Repo
cd "$PRIVATE_REPO_DIR" || exit
# Creates a tarball of the current HEAD, excluding 'export-ignore' files, and pipes it to tar extract in public dir
git archive HEAD | tar -x -C "$PUBLIC_REPO_DIR"

# 4. Commit and Push Public
cd "$PUBLIC_REPO_DIR" || exit
git add .
git commit -m "$COMMIT_MSG"
git push origin main

echo "✅ Public repo updated successfully!"
