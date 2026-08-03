# Local CI Equivalent Script for PAIOS CE
# Run offline tests matching GitHub Actions CI

param(
    [string]$PythonExe = "python",
    [string]$WorkDir = $PWD
)

$ErrorActionPreference = "Stop"

Write-Host "=== PAIOS CE Local CI Equivalent ===" -ForegroundColor Cyan
Write-Host "WorkDir: $WorkDir"
Write-Host "Python: $PythonExe"

# Check Python version
$pyVersion = & $PythonExe --version 2>&1
Write-Host "Python version: $pyVersion"

# Create venv
$venvPath = Join-Path $WorkDir ".venv_ci"
if (Test-Path $venvPath) {
    Remove-Item $venvPath -Recurse -Force
}
Write-Host "Creating venv: $venvPath" -ForegroundColor Yellow
& $PythonExe -m venv $venvPath

# Activate
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
& $activateScript

# Install
Write-Host "Installing package..." -ForegroundColor Yellow
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet

# Run tests
Write-Host "`n=== Running Tests ===" -ForegroundColor Cyan
pytest --cov=paios_ce --cov-report=xml:coverage_ci.xml --cov-report=term-missing -ra

# Coverage gate
Write-Host "`n=== Coverage Gate ===" -ForegroundColor Cyan
python -c @"
import xml.etree.ElementTree as ET
tree = ET.parse('coverage_ci.xml')
root = tree.getroot()
line_rate = float(root.attrib.get('line-rate', 0))
branch_rate = float(root.attrib.get('branch-rate', 0))
line_pct = line_rate * 100
branch_pct = branch_rate * 100
print(f'Line coverage: {line_pct:.2f}% (gate: 86.2%)')
print(f'Branch coverage: {branch_pct:.2f}% (gate: 66.7%)')
if line_pct < 86.2:
    raise SystemExit(f'FAILED: Line coverage {line_pct:.2f}% below gate 86.2%')
if branch_pct < 66.7:
    raise SystemExit(f'FAILED: Branch coverage {branch_pct:.2f}% below gate 66.7%')
print('PASS: Coverage gates met')
"@

# CLI tests
Write-Host "`n=== CLI Tests ===" -ForegroundColor Cyan
paios-ce health
paios-ce demo
paios-ce validate-config

# Build package
Write-Host "`n=== Package Build ===" -ForegroundColor Cyan
pip install build --quiet
python -m build --wheel --sdist

Write-Host "`n=== LOCAL CI PASS ===" -ForegroundColor Green