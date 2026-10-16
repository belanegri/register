$ErrorActionPreference = 'Stop'
try {
    $origemEtiquetas = Join-Path $PSScriptRoot 'REGISTER-Etiquetas'
    $destinoEtiquetas = Join-Path $env:LOCALAPPDATA 'REGISTER\etiquetas\assistente'
    $exeEtiquetas = Join-Path $destinoEtiquetas 'REGISTER-Etiquetas.exe'
    if (-not (Test-Path -LiteralPath (Join-Path $origemEtiquetas 'REGISTER-Etiquetas.exe'))) { throw 'Extraia todo o ZIP antes de instalar.' }
    Get-Process -Name 'REGISTER-Etiquetas' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exeEtiquetas } | Stop-Process
    New-Item -ItemType Directory -Path $destinoEtiquetas -Force | Out-Null
    Get-ChildItem -LiteralPath $origemEtiquetas | Copy-Item -Destination $destinoEtiquetas -Recurse -Force
    $shellEtiquetas = New-Object -ComObject WScript.Shell
    $atalhoEtiquetas = $shellEtiquetas.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'REGISTER - Etiquetas.lnk'))
    $atalhoEtiquetas.TargetPath = $exeEtiquetas
    $atalhoEtiquetas.WorkingDirectory = $destinoEtiquetas
    $atalhoEtiquetas.WindowStyle = 7
    $atalhoEtiquetas.Save()
    Start-Process -FilePath $exeEtiquetas -WorkingDirectory $destinoEtiquetas -WindowStyle Hidden
    $prontoEtiquetas = $false
    for ($tentativaEtiquetas = 0; $tentativaEtiquetas -lt 20; $tentativaEtiquetas++) {
        try {
            $statusEtiquetas = Invoke-RestMethod -Uri 'http://127.0.0.1:17857/status' -TimeoutSec 2
            if ($statusEtiquetas.versao -eq 'raw30-multicomputador-2') { $prontoEtiquetas = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $prontoEtiquetas) { throw 'O assistente nao iniciou. Feche uma versao anterior do assistente REGISTER e execute novamente.' }
    Write-Host 'Assistente instalado. No REGISTER, abra uma etiqueta e clique em Atualizar impressoras.'
    Write-Host 'Para impressora compartilhada, conecte-a no Windows antes de selecionar no sistema.'
} catch {
    Write-Host ('Instalacao nao concluida: ' + $_.Exception.Message)
    exit 1
}
