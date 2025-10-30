# Script PowerShell pour démarrer NextPost
Write-Host "🚀 Demarrage du serveur NextPost..." -ForegroundColor Green
Set-Location "c:\Users\sever\Documents\nextpost\backend"
& "c:\Users\sever\Documents\nextpost\.venv\Scripts\python.exe" manage.py runserver