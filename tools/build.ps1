# 스크립트 위치 기준으로 프로젝트 폴더를 잡는다 (PC 경로에 의존하지 않음)
Set-Location (Split-Path -Parent $PSScriptRoot)
# 실행 중인 훤히가 있으면 결과물이 잠겨 덮어쓰지 못한다. 그런데도 옛 파일이 남아 있어
# 빌드가 성공한 것처럼 보이므로, 시작 전에 막고 끝난 뒤 파일 시각까지 확인한다.
$running = Get-Process -Name '훤히' -ErrorAction SilentlyContinue
if ($running) { Write-Output ('BUILD STOPPED: 훤히가 실행 중입니다 (PID {0}). 모두 종료한 뒤 다시 빌드하세요.' -f ($running.Id -join ', ')); exit 1 }
$started = Get-Date
Remove-Item -Recurse -Force 'build','dist' -ErrorAction SilentlyContinue
$pyargs = @(
  '-m','PyInstaller','--noconfirm','--onedir','--name','훤히','--windowed','--icon','assets\훤히.ico',
  '--add-data','detector\ui\index.html;ui',
  '--add-data','assets\훤히.ico;assets',
  '--add-data','assets\fonts;assets\fonts',
  '--collect-all','playwright','--collect-all','winrt','--collect-all','pypdfium2','--collect-all','pypdfium2_raw',
  '--exclude-module','webview','--exclude-module','clr','--exclude-module','pythonnet',
  '--exclude-module','clr_loader',
  '--paths','detector','detector\main.py'
)
& '.\.venv\Scripts\python.exe' @pyargs 2>&1 | Select-String -Pattern 'ERROR|Traceback|completed successfully' | Select-Object -Last 3
if ((Test-Path 'dist\훤히\훤히.exe') -and (Get-Item 'dist\훤히\훤히.exe').LastWriteTime -ge $started) {
  $s = (Get-ChildItem -Recurse 'dist\훤히' | Measure-Object -Property Length -Sum).Sum/1MB
  Write-Output ('BUILD OK / {0:N0} MB' -f $s)
  & (Join-Path $PSScriptRoot 'sign.ps1') 'dist\훤히'
} else { Write-Output 'BUILD FAILED (결과물이 새로 만들어지지 않음)' }
