#!/bin/bash
# Environment setup for SQLite + SQLModel migration mission
# Idempotent — safe to run multiple times

cd C:\exp\puzzle-solver

if command -v uv >/dev/null 2>&1; then
    uv sync >/dev/null 2>&1 || true
elif [ -f ".venv/Scripts/python" ]; then
    .venv/Scripts/python -m pip install -e . >/dev/null 2>&1 || true
fi

echo "Environment prepared for SQLite migration mission."
