# Executar em um terminal interativo. Usuario/e-mail/senha sao informados por voce.
$ErrorActionPreference = "Stop"
$repoRegister = Split-Path -Parent $PSScriptRoot
$cliRegister = Join-Path $repoRegister ".local/railway-cli/node_modules/@railway/cli/bin/railway.exe"
if (-not (Test-Path -LiteralPath $cliRegister)) { $cliRegister = "railway" }
$argumentosRegister = @("ssh", "--project", "d4ac502c-7bf0-4112-9a30-676a1168b148", "--service", "5dee3a98-a5b8-4e48-a953-15942458ccef", "--environment", "9d6bafc8-6eef-4d1d-8ce5-90afe643bb74")
$chaveRegister = Join-Path $repoRegister ".local/register_railway_ed25519"
if (Test-Path -LiteralPath $chaveRegister) { $argumentosRegister += @("-i", $chaveRegister) }
$argumentosRegister += @("--", "python", "manage.py", "createsuperuser")
& $cliRegister @argumentosRegister
if ($LASTEXITCODE -ne 0) { throw "O administrador nao foi criado. Confira a mensagem do terminal." }
