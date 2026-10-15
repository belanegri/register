$ErrorActionPreference = 'Stop'
$destinoEtiquetas = Join-Path $env:LOCALAPPDATA 'REGISTER\etiquetas\assistente'
$exeEtiquetas = Join-Path $destinoEtiquetas 'REGISTER-Etiquetas.exe'
# Uma unica supervisao por sessao, mesmo se o Windows executar os dois atalhos.
$mutexEtiquetas = New-Object System.Threading.Mutex($false, 'Local\REGISTER-Etiquetas-Supervisor')
$adquiriuEtiquetas = $false
try {
    try { $adquiriuEtiquetas = $mutexEtiquetas.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $adquiriuEtiquetas = $true }
    if (-not $adquiriuEtiquetas) { exit 0 }
    while (Test-Path -LiteralPath $exeEtiquetas) {
        try {
            $processosEtiquetas = @(Get-Process -Name 'REGISTER-Etiquetas' -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -eq $exeEtiquetas })
            if ($processosEtiquetas.Count -eq 0) {
                # Uma ponte de uma instalacao anterior pode estar atendendo na mesma porta.
                $ativoEtiquetas = $false
                try {
                    $statusEtiquetas = Invoke-RestMethod -Uri 'http://127.0.0.1:17857/status' -TimeoutSec 3
                    $ativoEtiquetas = $statusEtiquetas.assistente -eq 'REGISTER'
                } catch {}
                if (-not $ativoEtiquetas) {
                    Start-Process -FilePath $exeEtiquetas -WorkingDirectory $destinoEtiquetas -WindowStyle Hidden
                }
            }
        } catch {
            $logEtiquetas = Join-Path $destinoEtiquetas 'inicializacao.log'
            Add-Content -LiteralPath $logEtiquetas -Value ((Get-Date -Format s) + ' ' + $_.Exception.Message) -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 15
    }
} finally {
    if ($adquiriuEtiquetas) { $mutexEtiquetas.ReleaseMutex() }
    $mutexEtiquetas.Dispose()
}
