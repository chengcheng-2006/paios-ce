# Local CI Equivalent Script for PAIOS CE
# Runs the EXACT frozen GitHub CI test command offline, using only the venv's
# own python/pip/pytest executables (no reliance on activation state or global tools).
# Mirrors .github/workflows/ci.yml thresholds: line >= 86.2%, branch >= 66.7%.

param(
    [string]$PythonExe = "python",
    [string]$WorkDir = $PWD
)

$ErrorActionPreference = "Stop"
$global:LASTEXITCODE = 0

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
if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }

# Always use the venv's own executables explicitly; never rely on PATH/activation.
$venvPy = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "venv python not found: $venvPy" }
$venvPip = @($venvPy, "-m", "pip")
$venvPytest = @($venvPy, "-m", "pytest")

# All install/test/build steps run inside WorkDir
Push-Location $WorkDir
try {
    # Install
    Write-Host "Installing package via venv python -m pip..." -ForegroundColor Yellow
    & $venvPy -m pip install --upgrade pip --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $venvPy -m pip install -e ".[dev]" --quiet
    if ($LASTEXITCODE -ne 0) { throw "editable install failed" }

    # Run tests with the EXACT frozen CI command (includes --cov-branch)
    Write-Host "`n=== Running Tests (exact CI command) ===" -ForegroundColor Cyan
    & $venvPy -m pytest --cov=paios_ce --cov-branch --cov-report=xml:coverage_ci.xml --cov-report=term-missing -ra -q
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }

    # Coverage gate (same thresholds as ci.yml)
    Write-Host "`n=== Coverage Gate ===" -ForegroundColor Cyan
    & $venvPy -c @"
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
    if ($LASTEXITCODE -ne 0) { throw "coverage gate failed" }

    # CLI tests via venv console script
    Write-Host "`n=== CLI Tests ===" -ForegroundColor Cyan
    $cliExe = Join-Path $venvPath "Scripts\paios-ce.exe"
    & $cliExe health
    if ($LASTEXITCODE -ne 0) { throw "paios-ce health failed" }
    & $cliExe demo
    if ($LASTEXITCODE -ne 0) { throw "paios-ce demo failed" }
    & $cliExe validate-config
    if ($LASTEXITCODE -ne 0) { throw "paios-ce validate-config failed" }

    # Build package (venv python -m build)
    Write-Host "`n=== Package Build ===" -ForegroundColor Cyan
    & $venvPy -m pip install "build>=1.2,<2" --quiet
    if ($LASTEXITCODE -ne 0) { throw "build install failed" }
    & $venvPy -m build --wheel --sdist
    if ($LASTEXITCODE -ne 0) { throw "build failed" }
}
finally {
    Pop-Location
}

Write-Host "`n=== LOCAL CI PASS ===" -ForegroundColor Green
exit 0
