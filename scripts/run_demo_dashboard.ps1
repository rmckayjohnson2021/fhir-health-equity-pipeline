param(
    [int]$Port = 8765,
    [switch]$SkipDemo,
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$dashboardUrl = "http://127.0.0.1:$Port/"

function Test-DashboardServer {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Head -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    }
    catch {
        return $false
    }
}

Push-Location $repoRoot
try {
    if (-not $SkipDemo) {
        Write-Host "Step 1/3: running the full local demo..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "demo.ps1")
    }
    else {
        Write-Host "Step 1/3: skipping demo refresh because -SkipDemo was provided." -ForegroundColor Yellow
    }

    Write-Host "Step 2/3: starting the local dashboard control server..." -ForegroundColor Cyan
    if (Test-DashboardServer -Url $dashboardUrl) {
        Write-Host "Dashboard server already appears to be running at $dashboardUrl" -ForegroundColor Yellow
    }
    else {
        $serverCommand = "Set-Location -LiteralPath '$repoRoot'; uv run python -m scripts.dashboard_control_server --port $Port"
        Start-Process powershell.exe -ArgumentList @(
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            $serverCommand
        )
        Start-Sleep -Seconds 3
    }

    Write-Host "Step 3/3: opening the dashboard..." -ForegroundColor Cyan
    if (-not $NoBrowser) {
        Start-Process $dashboardUrl
    }

    Write-Host ""
    Write-Host "Dashboard: $dashboardUrl" -ForegroundColor Green
    Write-Host "Use Open pipeline monitor -> Run next synthetic load to advance to the next synthetic panel." -ForegroundColor Green
}
finally {
    Pop-Location
}
