# Wait for the current six-worker process, including its final comparison output.
Write-Host 'Waiting for the current six-worker pass. Eight-worker retries will start afterwards.'
Wait-Process -Id 11608 -ErrorAction SilentlyContinue
& 'C:\Users\HP\AppData\Local\Programs\Python\Python311\python.exe' -u "$PSScriptRoot\retry_b0_errors.py"
