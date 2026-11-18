# Starts the lc idle watcher (no-op if already running). Run at logon.
& 'C:\Users\DaGuest\local-coder\bin\lc.cmd' watch start *>> (Join-Path $env:TEMP 'lc-watch-start.log')
