<#
.SYNOPSIS
Idempotent setup and verification of a Windows workstation as the governed
runtime host per docs/RUNTIME_HOST_DECISION.md.

.DESCRIPTION
Brings a workstation to the state the Monday runbook assumes, and verifies it:

  1. Python 3.12 located (the full lock resolves for 3.12 only).
  2. Dedicated venv OUTSIDE any synced folder (default: ~\.venvs\joeyyy) --
     a venv inside OneDrive churns sync on every byte-compiled file.
  3. Dependencies installed from requirements/lock-2026-07-24.txt with
     Linux-only pins (uvloop) filtered out. The repo lockfile is never edited;
     the filtered copy is written to a temp file.
  4. Trusted-launcher signing key at ~\.agent007\launch_key (32 random bytes),
     ACL-restricted to the current user. An existing key is never overwritten.
  5. The repository verification surface: verify_runtime_stack,
     privacy_guard, validate_specialist_corps, generate_claude_agents --check.
  6. MCP mount probe (informational): reports whether Node/npx and Docker are
     present; their absence blocks connector mounts, not the governed runtime.
  7. Promotion coverage snapshot from MissionRunner.

Safe to re-run at any time: every step detects existing state and skips work
already done. Nothing here changes any lifecycle stage or writes to the repo.

Known limits on native Windows, recorded rather than hidden: the POSIX 0600
custody checks in scripts/issue_instruction.py cannot pass (os.chmod is a
no-op), and the full unittest suite has environment-caused failures (chmod
semantics, autocrlf hashing). Run the suite under WSL2 for a clean signal, or
use -RunTests here to see the native result with that caveat attached.

.PARAMETER VenvPath
Where the venv lives. Default: $env:USERPROFILE\.venvs\joeyyy

.PARAMETER SkipInstall
Skip dependency installation (verification only).

.PARAMETER RunTests
Also run the full unittest suite (slow; expect known environmental failures
on native Windows).
#>
[CmdletBinding()]
param(
    [string]$VenvPath = (Join-Path $env:USERPROFILE ".venvs\joeyyy"),
    [switch]$SkipInstall,
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$results = [ordered]@{}

function Step([string]$name, [scriptblock]$body) {
    Write-Host ""
    Write-Host "== $name" -ForegroundColor Cyan
    try {
        & $body
        $script:results[$name] = "ok"
    } catch {
        $script:results[$name] = "FAILED: $($_.Exception.Message)"
        Write-Host $_.Exception.Message -ForegroundColor Red
    }
}

# ---------------------------------------------------------------- 1. python
Step "python 3.12" {
    $script:BasePython = $null
    foreach ($candidate in @("3.12", "3.11")) {
        & py "-$candidate" -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $script:BasePython = $candidate; break }
    }
    if (-not $script:BasePython) {
        throw "No Python 3.12 or 3.11 found via the py launcher. Install 3.12 from python.org."
    }
    if ($script:BasePython -ne "3.12") {
        Write-Host "Found only $script:BasePython -- repository validation works, but requirements/lock-2026-07-24.txt is resolved for 3.12 only." -ForegroundColor Yellow
    }
    Write-Host "Using Python $script:BasePython"
}

# ---------------------------------------------------------------- 2. venv
Step "venv (outside synced folders)" {
    if ($VenvPath -like "*OneDrive*") {
        throw "Refusing a venv inside OneDrive ($VenvPath): sync churn. Pass -VenvPath outside any synced folder."
    }
    $script:VenvPython = Join-Path $VenvPath "Scripts\python.exe"
    if (Test-Path $script:VenvPython) {
        Write-Host "Exists: $VenvPath"
    } else {
        & py "-$script:BasePython" -m venv $VenvPath
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
        Write-Host "Created: $VenvPath"
    }
    $v = & $script:VenvPython --version
    Write-Host "Interpreter: $v"
}

# ---------------------------------------------------------------- 3. install
Step "dependencies (filtered lock)" {
    if ($SkipInstall) { Write-Host "Skipped (-SkipInstall)"; return }
    $lock = Join-Path $RepoRoot "requirements\lock-2026-07-24.txt"
    if (-not (Test-Path $lock)) { throw "Lock not found: $lock" }

    # Drop Linux-only pins. The lock was compiled without --universal, so
    # uvloop (which does not build on Windows) appears unconditionally: skip
    # its package line and the indented "# via" continuation lines under it.
    $filtered = Join-Path $env:TEMP "joeyyy-lock-filtered.txt"
    $skipping = $false
    $out = foreach ($line in Get-Content $lock) {
        if ($line -match '^(uvloop)==') { $skipping = $true; continue }
        if ($skipping) {
            if ($line -match '^\s') { continue } else { $skipping = $false }
        }
        $line
    }
    $out | Out-File -FilePath $filtered -Encoding utf8
    Write-Host "Filtered lock -> $filtered (repo lockfile untouched)"

    & $script:VenvPython -m pip install --quiet --require-virtualenv -r $filtered
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }
    $count = (& $script:VenvPython -m pip list --format=freeze | Measure-Object -Line).Lines
    Write-Host "Installed packages in venv: $count"
}

# ---------------------------------------------------------------- 4. key
Step "trusted-launcher signing key" {
    $keyDir = Join-Path $env:USERPROFILE ".agent007"
    $keyPath = Join-Path $keyDir "launch_key"   # DEFAULT_KEY_PATH in scripts/trusted_launcher.py
    if (Test-Path $keyPath) {
        $len = (Get-Item $keyPath).Length
        if ($len -ne 32) { throw "Existing key at $keyPath is $len bytes, expected 32. Not touching it; resolve manually." }
        Write-Host "Exists: $keyPath (32 bytes) -- not overwritten"
    } else {
        New-Item -ItemType Directory -Force $keyDir | Out-Null
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($bytes)
        [System.IO.File]::WriteAllBytes($keyPath, $bytes)
        Write-Host "Created: $keyPath (32 random bytes)"
    }
    # Windows equivalent of 0600: strip inheritance, grant only the current user.
    $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    icacls $keyPath /inheritance:r /grant:r "${me}:(R,W)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls failed to restrict $keyPath" }
    Write-Host "ACL restricted to: $me"
    Write-Host "Note: POSIX 0600 custody checks (issue_instruction.py) still require WSL2 or the Windows-ACL port -- open decision in docs/RUNTIME_HOST_DECISION.md." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 5. verify
$verifications = @(
    @{ name = "verify_runtime_stack";       args = @("scripts\verify_runtime_stack.py") },
    @{ name = "privacy_guard";              args = @("scripts\privacy_guard.py") },
    @{ name = "validate_specialist_corps";  args = @("scripts\validate_specialist_corps.py") },
    @{ name = "generate_claude_agents --check"; args = @("scripts\generate_claude_agents.py", "--check") }
)
foreach ($v in $verifications) {
    Step $v.name {
        Push-Location $RepoRoot
        try {
            & $script:VenvPython @($v.args)
            if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
        } finally { Pop-Location }
    }
}

# ---------------------------------------------------------------- 6. mounts
Step "mcp mounts (informational)" {
    $npx = Get-Command npx.cmd -ErrorAction SilentlyContinue
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $npx)    { Write-Host "npx not found: Node-based MCP mounts unavailable until Node.js is installed." -ForegroundColor Yellow }
    if (-not $docker) { Write-Host "docker not found: github/terraform container mounts unavailable." -ForegroundColor Yellow }
    Push-Location $RepoRoot
    try {
        & $script:VenvPython "scripts\verify_mcp_mounts.py"
        Write-Host "verify_mcp_mounts exit code: $LASTEXITCODE (informational -- mounts gate connectors, not the governed runtime)"
    } finally { Pop-Location }
}

# ---------------------------------------------------------------- 7. tests
if ($RunTests) {
    Step "unittest suite (native Windows caveat applies)" {
        Push-Location $RepoRoot
        try {
            & $script:VenvPython -m unittest discover -s tests
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Failures on native Windows are expected from POSIX chmod semantics and autocrlf hashing; see docs/RUNTIME_HOST_DECISION.md before treating them as regressions." -ForegroundColor Yellow
                throw "suite exit code $LASTEXITCODE"
            }
        } finally { Pop-Location }
    }
}

# ---------------------------------------------------------------- 8. status
Step "promotion coverage snapshot" {
    Push-Location $RepoRoot
    try {
        & $script:VenvPython -c "from runtime.mission_runner import MissionRunner; import json; r = MissionRunner().promotion_status(); print(json.dumps({k: r[k] for k in ('covered_modes','total_modes','agents_fully_covered','ledger_trustworthy')}, indent=2))"
        if ($LASTEXITCODE -ne 0) { throw "promotion_status failed" }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------- summary
Write-Host ""
Write-Host "== Summary" -ForegroundColor Cyan
$failed = $false
foreach ($entry in $results.GetEnumerator()) {
    $color = "Green"
    if ($entry.Value -ne "ok") { $color = "Red"; $failed = $true }
    Write-Host ("{0,-45} {1}" -f $entry.Key, $entry.Value) -ForegroundColor $color
}
if ($failed) { exit 1 } else { Write-Host "`nWorkstation ready. Next: docs/MONDAY_ACTIVATION_RUNBOOK.md and docs/PROMOTION_CHECKLISTS.md." -ForegroundColor Green; exit 0 }
