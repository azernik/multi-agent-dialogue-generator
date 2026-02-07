#!/bin/bash
# Quick test script to demonstrate the diagnostic tool

echo "========================================================================"
echo "Testing Failure Diagnostic Tools"
echo "========================================================================"
echo ""

# Find python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python not found"
    exit 1
fi

echo "Using Python: $PYTHON"
echo ""

# Test 1: Diagnose a specific failure
echo "Test 1: Diagnosing conversation os_to_001"
echo "------------------------------------------------------------------------"
$PYTHON scripts/diagnose_failures.py --conversation-id os_to_001
echo ""

# Test 2: Analyze all failures (dry run)
echo ""
echo "Test 2: Analyzing all failures (dry run)"
echo "------------------------------------------------------------------------"
$PYTHON scripts/analyze_and_fix_failures.py --dry-run | head -40
echo ""

echo "========================================================================"
echo "Tests complete!"
echo ""
echo "For full analysis, run:"
echo "  $PYTHON scripts/analyze_and_fix_failures.py --output report.txt"
echo ""
echo "To attempt fixes:"
echo "  $PYTHON scripts/analyze_and_fix_failures.py --fix-syntax --reeval"
echo "========================================================================"

