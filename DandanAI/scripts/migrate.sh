#!/usr/bin/env bash
# Applies the schema to Neon using DIRECT_URL (creates the pgvector extension, tables, HNSW indexes).
set -e; cd "$(dirname "$0")/../backend"
PY=.venv/bin/python; [ -x $PY ] || PY=python3
$PY -m alembic upgrade head
