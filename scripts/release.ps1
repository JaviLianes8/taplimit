# Build and upload to PyPI from a clean clone of main; runs scripts/check.ps1 first.
# The token is read from a secret store at release time, never from git.
$ErrorActionPreference = "Stop"

function Step([string]$name, [scriptblock]$command) {
    & $command
    if ($LASTEXITCODE -ne 0) { throw "$name failed with exit code $LASTEXITCODE" }
}

Set-Location (Split-Path $PSScriptRoot -Parent)
$version = (Select-String -Path src/taplimit/__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
try {
    Invoke-WebRequest -UseBasicParsing "https://pypi.org/pypi/taplimit/$version/json" | Out-Null
    throw "taplimit $version is already on PyPI. Bump the version first."
} catch [System.Net.WebException], [Microsoft.PowerShell.Commands.HttpResponseException] {
    if ($_.Exception.Response.StatusCode.value__ -ne 404) { throw }
}

if (git status --porcelain) { throw "The working tree is not clean." }
if ((git rev-parse --abbrev-ref HEAD) -ne "main") { throw "Release only from main." }
& "$PSScriptRoot\check.ps1"

$token = $env:PYPI_TOKEN
if (-not $token -and (Test-Path "C:\secrets\pypi-token.txt")) {
    $token = (Get-Content "C:\secrets\pypi-token.txt" -Raw).Trim()
}
if (-not $token) {
    throw "No PyPI token. Set `$env:PYPI_TOKEN or save it to C:\secrets\pypi-token.txt (never commit it)."
}

Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Step "build" { python -m build }
Step "twine check" { python -m twine check --strict dist/* }

$env:TWINE_USERNAME = "__token__"
$env:TWINE_PASSWORD = $token
try { Step "upload" { python -m twine upload dist/* } } finally {
    Remove-Item Env:\TWINE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:\TWINE_USERNAME -ErrorAction SilentlyContinue
}
