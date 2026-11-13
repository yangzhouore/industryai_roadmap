[CmdletBinding()]
param(
    [ValidateSet('start', 'stop', 'status')][string]$Action = 'start',
    [string]$BinDirectory,
    [ValidateRange(1024,65535)][int]$Port = 55432
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$artifactRoot = Join-Path $workspace 'artifacts/local-postgres'
$dataDirectory = Join-Path $artifactRoot 'data'
if (-not $BinDirectory) {
    $candidate = Get-ChildItem -LiteralPath (Join-Path $workspace 'artifacts') -Filter pg_ctl.exe -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) { $BinDirectory = $candidate.DirectoryName }
}
if (-not $BinDirectory) { throw 'Supply -BinDirectory for trusted portable PostgreSQL binaries; no system installation is required.' }
$BinDirectory = (Resolve-Path -LiteralPath $BinDirectory).Path
$pgctl = Join-Path $BinDirectory 'pg_ctl.exe'
$initdb = Join-Path $BinDirectory 'initdb.exe'
$psql = Join-Path $BinDirectory 'psql.exe'
foreach ($binary in @($pgctl,$initdb)) {
    if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw "Missing binary: $binary" }
}
if ($Action -eq 'stop') {
    & $pgctl -D $dataDirectory -m fast -w stop
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL stop failed' }
    exit
}
if ($Action -eq 'status') {
    & $pgctl -D $dataDirectory status
    exit $LASTEXITCODE
}
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $dataDirectory 'PG_VERSION'))) {
    & $initdb -D $dataDirectory -U digest --encoding=UTF8 --locale=C --auth=trust
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed' }
}
& $pgctl -D $dataDirectory status *> $null
if ($LASTEXITCODE -ne 0) {
    & $pgctl -D $dataDirectory -l (Join-Path $artifactRoot 'server.log') -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL start failed; inspect artifacts/local-postgres/server.log' }
}
if (Test-Path -LiteralPath $psql) {
    foreach ($database in @('digest','digest_pipeline_test')) {
        $exists = & $psql -h 127.0.0.1 -p $Port -U digest -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$database'"
        if ($LASTEXITCODE -ne 0) { throw 'Cannot connect to the isolated database' }
        if ($exists -ne '1') {
            & $psql -h 127.0.0.1 -p $Port -U digest -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $database"
            if ($LASTEXITCODE -ne 0) { throw "Could not create database: $database" }
        }
    }
} else {
    & python (Join-Path $PSScriptRoot 'bootstrap_local.py') --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Database creation requires psql or the declared psycopg Python dependency' }
}
Write-Output "DATABASE_URL=postgresql://digest@127.0.0.1:$Port/digest"
Write-Output "TEST_DATABASE_URL=postgresql://digest@127.0.0.1:$Port/digest_pipeline_test"
Write-Output 'Disposable loopback test instance uses local trust authentication; stop it after verification.'
