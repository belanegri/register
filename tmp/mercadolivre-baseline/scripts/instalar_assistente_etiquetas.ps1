$ErrorActionPreference = 'Stop'
try {
    $origemEtiquetas = Join-Path $PSScriptRoot 'REGISTER-Etiquetas'
    $destinoEtiquetas = Join-Path $env:LOCALAPPDATA 'REGISTER\etiquetas\assistente'
    $exeEtiquetas = Join-Path $destinoEtiquetas 'REGISTER-Etiquetas.exe'
    $iniciadorEtiquetas = Join-Path $destinoEtiquetas 'iniciar_assistente_etiquetas.ps1'
    $powershellEtiquetas = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath (Join-Path $origemEtiquetas 'REGISTER-Etiquetas.exe'))) { throw 'Extraia todo o ZIP antes de instalar.' }
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'iniciar_assistente_etiquetas.ps1'))) { throw 'Extraia todo o ZIP antes de instalar.' }
    Get-Process -Name 'REGISTER-Etiquetas' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exeEtiquetas } | Stop-Process
    New-Item -ItemType Directory -Path $destinoEtiquetas -Force | Out-Null
    Get-ChildItem -LiteralPath $origemEtiquetas | Copy-Item -Destination $destinoEtiquetas -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'iniciar_assistente_etiquetas.ps1') -Destination $iniciadorEtiquetas -Force
    Unblock-File -LiteralPath $iniciadorEtiquetas
    $argumentosEtiquetas = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $iniciadorEtiquetas + '"'
    $shellEtiquetas = New-Object -ComObject WScript.Shell
    $atalhoEtiquetas = $shellEtiquetas.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'REGISTER - Etiquetas.lnk'))
    $atalhoEtiquetas.TargetPath = $powershellEtiquetas
    $atalhoEtiquetas.Arguments = $argumentosEtiquetas
    $atalhoEtiquetas.WorkingDirectory = $destinoEtiquetas
    $atalhoEtiquetas.WindowStyle = 7
    $atalhoEtiquetas.Save()
    # Entrada por usuario: nao exige administrador e independe da pasta extraida do ZIP.
    $registroEtiquetas = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    New-Item -Path $registroEtiquetas -Force | Out-Null
    New-ItemProperty -Path $registroEtiquetas -Name 'REGISTER-Etiquetas' -PropertyType String -Value ('"' + $powershellEtiquetas + '" ' + $argumentosEtiquetas) -Force | Out-Null
    $atalhoManualEtiquetas = $shellEtiquetas.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Iniciar etiquetas REGISTER.lnk'))
    $atalhoManualEtiquetas.TargetPath = $powershellEtiquetas
    $atalhoManualEtiquetas.Arguments = $argumentosEtiquetas
    $atalhoManualEtiquetas.WorkingDirectory = $destinoEtiquetas
    $atalhoManualEtiquetas.WindowStyle = 7
    $atalhoManualEtiquetas.Save()
    Start-Process -FilePath $powershellEtiquetas -ArgumentList $argumentosEtiquetas -WorkingDirectory $destinoEtiquetas -WindowStyle Hidden
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
    Write-Host 'Inicio automatico e recuperacao ativados para este usuario do Windows.'
    Write-Host 'Se precisar abrir manualmente, use Iniciar etiquetas REGISTER na area de trabalho, sem reinstalar.'
    Write-Host 'Para impressora compartilhada, conecte-a no Windows antes de selecionar no sistema.'
} catch {
    Write-Host ('Instalacao nao concluida: ' + $_.Exception.Message)
    exit 1
}
