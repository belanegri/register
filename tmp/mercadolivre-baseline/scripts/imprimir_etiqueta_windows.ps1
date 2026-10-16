param([Parameter(Mandatory=$true)][string]$Imagem)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$impressao = New-Object System.Drawing.Printing.PrintDocument
$impressao.PrinterSettings.PrinterName = 'REGISTER - Etiquetas 57x30'
if (-not $impressao.PrinterSettings.IsValid) { throw 'Fila REGISTER - Etiquetas 57x30 indisponivel.' }
$impressao.PrinterSettings.Copies = 1
$impressao.PrintController = New-Object System.Drawing.Printing.StandardPrintController
$impressao.DefaultPageSettings.Margins = New-Object System.Drawing.Printing.Margins(0,0,0,0)
$impressao.DocumentName = 'REGISTER - etiqueta do sistema'
$figura = [System.Drawing.Image]::FromFile($Imagem)
$impressao.add_PrintPage({
    param($sender,$pagina)
    $area = [System.Drawing.RectangleF]::new(-$pagina.PageSettings.HardMarginX,
        -$pagina.PageSettings.HardMarginY,$pagina.PageBounds.Width,$pagina.PageBounds.Height)
    $pagina.Graphics.DrawImage($figura,$area)
    $pagina.HasMorePages = $false
})
try { $impressao.Print() }
finally { $figura.Dispose(); $impressao.Dispose() }
