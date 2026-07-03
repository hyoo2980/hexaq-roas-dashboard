$running = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*realtime_order_watcher.py*" }

if (-not $running) {
    Start-ScheduledTask -TaskName "HexaqAquaMedinOrderWatcher"
    $logPath = "C:\Users\hyoo2\OneDrive\바탕 화면\클로드 자동화\헥사큐아쿠아메딘\data\watcher.log"
    $line = "[{0}] 감시자: 워처가 죽어있어 재시작함" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}
