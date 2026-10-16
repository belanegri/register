$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pgCtl = Join-Path $projectRoot '.local\pgsql\bin\pg_ctl.exe'
$pgData = Join-Path $projectRoot '.local\pgdata'
if (Test-Path -LiteralPath $pgData) {
    & $pgCtl -D $pgData status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $pgCtl -D $pgData -l (Join-Path $projectRoot '.local\postgres.log') -w start
        if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel iniciar o PostgreSQL.' }
    }
}
& '.\.venv\Scripts\python.exe' manage.py runserver 127.0.0.1:8000
