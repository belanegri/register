$ErrorActionPreference = 'Stop'
$raizEtiquetas = (Get-Location).Path
$zipEtiquetas = Join-Path $raizEtiquetas 'scripts\releases\REGISTER-Etiquetas-Windows.zip'
$pastaEtiquetas = Join-Path $raizEtiquetas 'tmp\etiquetas-instalacao'
Expand-Archive -LiteralPath $zipEtiquetas -DestinationPath $pastaEtiquetas -Force
$pythonEtiquetas = 'C:\Users\Isabela\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
$servidorEtiquetas = Join-Path $raizEtiquetas '.local\register-label-helper\servidor_etiqueta_windows.py'
$legadoEtiquetas = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $pythonEtiquetas -and $_.CommandLine.Contains($servidorEtiquetas) })
if ($legadoEtiquetas.Count -gt 1) { throw 'Mais de um assistente antigo identificado; interrompido.' }
foreach ($processoEtiquetas in $legadoEtiquetas) { Stop-Process -Id $processoEtiquetas.ProcessId }
try {
    & (Join-Path $pastaEtiquetas 'instalar_assistente_etiquetas.ps1')
    $respostaEtiquetas = Invoke-RestMethod 'http://127.0.0.1:17857/status' -TimeoutSec 5
    if ($respostaEtiquetas.versao -ne 'raw30-multicomputador-2') { throw 'Assistente atualizado indisponivel.' }
    $respostaEtiquetas | ConvertTo-Json -Compress
} catch {
    if ($legadoEtiquetas.Count) { Start-Process -FilePath $pythonEtiquetas -ArgumentList ('"' + $servidorEtiquetas + '"') -WindowStyle Hidden }
    throw
}
