#!/bin/bash
# Environment setup for puzzle-solver Repository Abstraction mission
# Idempotent — safe to run multiple times

cd D:\exp\puzzle-solver

# Ensure dependencies are installed
if [ -f ".venv/Scripts/python" ]; then
    .venv/Scripts/python -m pip install -e . --quiet 2>/dev/null || true
elif [ -f ".venv/bin/python" ]; then
    .venv/bin/python -m pip install -e . --quiet 2>/dev/null || true
fi

# Verify baseline tests pass
echo "Verifying baseline tests..."
if [ -f ".venv/Scripts/python" ]; then
    .venv/Scripts/python -m pytest tests/ -q --tb=line 2>&1 | tail -3
elif [ -f ".venv/bin/python" ]; then
    .venv/bin/python -m pytest tests/ -q --tb=line 2>&1 | tail -3
fi
