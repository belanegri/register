$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot '.local\pgsql\bin\pg_ctl.exe') -D (Join-Path $projectRoot '.local\pgdata') -m fast -w stop
if ($LASTEXITCODE -ne 0) { throw 'Verifique se o PostgreSQL ja esta parado.' }
