#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$ROOT_DIR"

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Error: frontend/ directory not found."
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Error: frontend/package.json not found."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: this directory is not a Git repository."
  exit 1
fi


cd "$ROOT_DIR"

if [[ -z "$(git status --porcelain)" ]]; then
  echo
  echo "No changes to commit. Working tree is clean."
  exit 0
fi

echo
echo "===== CHANGES TO COMMIT ====="
git status --short

echo
read -r -p "Commit message: " COMMIT_MESSAGE

if [[ -z "${COMMIT_MESSAGE//[[:space:]]/}" ]]; then
  echo "Error: commit message cannot be empty."
  exit 1
fi

git add -A
git commit -m "$COMMIT_MESSAGE"

BRANCH="$(git branch --show-current)"

if [[ -z "$BRANCH" ]]; then
  echo "Error: could not determine current branch."
  exit 1
fi

echo
echo "===== PUSHING TO ORIGIN/$BRANCH ====="
git push -u origin "$BRANCH"

echo
echo "Push completed successfully."
