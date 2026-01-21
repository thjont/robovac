#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "=== Robovac Development Container ==="
echo ""
echo "Tool versions:"
echo "  Python:  $(python3 --version 2>&1 | cut -d' ' -f2)"
echo "  uv:      $(uv --version 2>&1 | cut -d' ' -f2)"
echo "  Task:    $(task --version 2>&1 | cut -d' ' -f3)"
echo "  gh:      $(gh --version 2>&1 | head -1 | cut -d' ' -f3)"
echo ""
echo "Available tasks (run 'task <name>'):"
task --list
echo ""
echo "Quick start:"
echo "  task ha-start        # Start Home Assistant"
echo "  task test            # Run tests"
echo "  task all             # Run all checks (test, lint, type-check)"
echo ""
