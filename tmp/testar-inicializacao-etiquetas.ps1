$ErrorActionPreference = 'Stop'
foreach ($arquivo in @('scripts/iniciar_assistente_etiquetas.ps1', 'scripts/instalar_assistente_etiquetas.ps1')) {
    $erros = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Get-Location) $arquivo), [ref]$null, [ref]$erros) | Out-Null
    if ($erros.Count) { throw ($erros | Out-String) }
}
$codigo = [ScriptBlock]::Create((Get-Content scripts/iniciar_assistente_etiquetas.ps1 -Raw))
function Test-Path { param($LiteralPath) $script:consultas++; return $script:consultas -le 3 }
function Get-Process { param($Name, $ErrorAction) if ($script:rodando) { [pscustomobject]@{Path=(Join-Path $env:LOCALAPPDATA 'REGISTER\etiquetas\assistente\REGISTER-Etiquetas.exe')} } }
function Invoke-RestMethod { param($Uri, $TimeoutSec) throw 'Indisponivel no teste' }
function Start-Process { param($FilePath, $WorkingDirectory, $WindowStyle) $script:inicios++ }
function Start-Sleep { param($Seconds) }
foreach ($rodando in @($false,$true)) {
    $script:rodando=$rodando; $script:consultas=0; $script:inicios=0
    & $codigo
    $esperado=if ($rodando) {0} else {3}
    if ($script:inicios -ne $esperado) { throw "Esperado $esperado, obtido $script:inicios" }
}
Write-Output 'Sintaxe valida; recuperacao apos encerramento e prevencao de duplicatas verificadas sem iniciar o assistente real.'
