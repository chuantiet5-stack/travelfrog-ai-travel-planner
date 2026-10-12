@echo off
chcp 65001 >nul
powershell -NoProfile -Command "$items = Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue; if ($items) { $items | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }; Write-Host '旅游推荐系统已停止。' } else { Write-Host '系统当前没有运行。' }"
pause
