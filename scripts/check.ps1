# Local quality gate. Run before every commit. No CI runs in the cloud.
$ErrorActionPreference = "Stop"

ruff format --check .
if ($LASTEXITCODE) { exit $LASTEXITCODE }
ruff check .
if ($LASTEXITCODE) { exit $LASTEXITCODE }
mypy --strict src tests
if ($LASTEXITCODE) { exit $LASTEXITCODE }
pytest
if ($LASTEXITCODE) { exit $LASTEXITCODE }
