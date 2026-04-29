# PXR File Watcher - Monitors _1 INPUT FOLDER for new PDFs
# When a PDF is dropped in, auto-runs the part number extractor
# and pushes extracted data to GitHub

$InputFolder = "C:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY\_1 INPUT FOLDER"
$WorkspaceRoot = "C:\_3 EVF-Bricks\_02 UI for Spec Sheets - Part Number ONLY"
$Extractor = "$WorkspaceRoot\Engines\part_number_extractor.py"

Write-Host "=== PXR File Watcher ===" -ForegroundColor Cyan
Write-Host "Monitoring: $InputFolder" -ForegroundColor DarkGray
Write-Host "Drop a PDF to trigger extraction + GitHub push." -ForegroundColor DarkGray
Write-Host ""

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $InputFolder
$watcher.Filter = "*.pdf"
$watcher.EnableRaisingEvents = $true

$action = {
    $name = $Event.SourceEventArgs.Name
    $time = Get-Date -Format "HH:mm:ss"
    Write-Host "[$time] Detected: $name" -ForegroundColor Yellow

    Start-Sleep -Seconds 2  # Wait for file write to finish

    Write-Host "[$time] Running extractor..." -ForegroundColor Cyan
    python $using:Extractor

    Write-Host "[$time] Pushing to GitHub..." -ForegroundColor Cyan
    Set-Location $using:WorkspaceRoot
    git add "_2 Output Data/" 2>$null
    git commit -m "Auto-extract: $name" 2>$null
    git push origin main 2>$null

    Write-Host "[$time] Done. UI will reflect new data on refresh." -ForegroundColor Green
}

Register-ObjectEvent $watcher "Created" -Action $action | Out-Null

Write-Host "[ACTIVE] Watcher running. Press Ctrl+C to stop." -ForegroundColor Green
while ($true) { Start-Sleep -Seconds 1 }
