$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:CUFOOD_SQLITE = '1'
$env:DEBUG = '1'
python manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Migration failed. Install requirements-local.txt first.' }
python manage.py seed_demo
if ($LASTEXITCODE -ne 0) { throw 'Demo setup failed.' }
Write-Host 'CU Food is available at http://127.0.0.1:8000'
python manage.py runserver 127.0.0.1:8000
