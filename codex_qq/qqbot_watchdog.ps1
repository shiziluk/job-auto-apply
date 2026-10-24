# -*- coding: utf-8 -*-
# QQbot 常驻保活看门狗：开机登录后自动拉起 codex_qq 桥接并保持在线（不随 Codex 开关）；
# 桥接意外崩溃时自动重启，并把崩溃证据（stderr/stdout 尾部）写入 data/bridge.crash.log；
# 连续快速崩溃达到阈值后停止自动重启，避免死循环。
# 注册为开机启动：qqbot_watchdog_autostart.vbs（放在用户启动文件夹）。
$ErrorActionPreference = 'SilentlyContinue'

$watchInterval = 10
$crashStreakLimit = 5     # 连续快速崩溃多少次后停止自动重启
$quickCrashSeconds = 30   # 启动后多少秒内崩溃算"快速崩溃"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $root
$python = 'C:\Python311\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$bridgeLog = Join-Path $root 'data\bridge.log'
$bridgeErr = Join-Path $root 'data\bridge.log.err'
$crashLog = Join-Path $root 'data\bridge.crash.log'
$watchLog = Join-Path $root 'data\watchdog.log'

# 单实例保护：已有本脚本在跑就直接退出
$already = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.Name -match 'powershell' -and $_.CommandLine -match 'qqbot_watchdog\.ps1'
}
if ($already) { exit }

function Write-WatchLog($msg) {
    Add-Content -Encoding UTF8 -Path $watchLog -Value ("{0} [watchdog] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
}

function Write-CrashReport($deadPid, $streak) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $errTail = ''
    if (Test-Path $bridgeErr) { $errTail = Get-Content $bridgeErr -Tail 40 -Encoding UTF8 | Out-String }
    $outTail = ''
    if (Test-Path $bridgeLog) { $outTail = Get-Content $bridgeLog -Tail 10 -Encoding UTF8 | Out-String }
    $report = @"

===== $stamp 桥接异常退出 (PID $deadPid, 连续快速崩溃 $streak 次) =====
--- stderr (bridge.log.err) 尾部 ---
$errTail
--- stdout (bridge.log) 尾部 ---
$outTail
"@
    Add-Content -Encoding UTF8 -Path $crashLog -Value $report
    Write-WatchLog ("桥接异常退出 (PID {0})，原因已记录到 data/bridge.crash.log" -f $deadPid)
}

function Get-RunningBridge {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'codex_qq\.cli' }
}

Write-WatchLog ("看门狗已启动，QQbot 将保持常驻在线 (PID {0})" -f $PID)

$bridgePid = $null
$lastStartAt = $null
$crashStreak = 0
while ($true) {
    $myAlive = $bridgePid -and (Get-Process -Id $bridgePid -ErrorAction SilentlyContinue)
    $anyBridge = Get-RunningBridge

    if ($myAlive) {
        # 桥接稳定运行超过阈值后重置崩溃计数
        if ($lastStartAt -and ((Get-Date) - $lastStartAt).TotalSeconds -ge $quickCrashSeconds) {
            $crashStreak = 0
        }
    } else {
        if ($bridgePid) {
            # 我们拉起的桥接挂了：先抓崩溃证据，再决定是否重启
            $uptime = 999
            if ($lastStartAt) { $uptime = ((Get-Date) - $lastStartAt).TotalSeconds }
            if ($uptime -lt $quickCrashSeconds) { $crashStreak++ } else { $crashStreak = 1 }
            Write-CrashReport $bridgePid $crashStreak
            if ($crashStreak -ge $crashStreakLimit) {
                Write-WatchLog ("桥接连续快速崩溃 {0} 次，已停止自动重启，请查看 data/bridge.crash.log 修复原因" -f $crashStreak)
                $bridgePid = $null
                $lastStartAt = $null
                Start-Sleep -Seconds $watchInterval
                continue
            }
        }
        if (-not $anyBridge) {
            $proc = Start-Process -FilePath $python -ArgumentList '-m','codex_qq.cli','bridge' `
                -WorkingDirectory $projectRoot -WindowStyle Hidden `
                -RedirectStandardOutput $bridgeLog -RedirectStandardError $bridgeErr -PassThru
            $bridgePid = $proc.Id
            $lastStartAt = Get-Date
            Write-WatchLog ("QQbot 不在线，自动拉起 (PID {0})" -f $proc.Id)
        } else {
            # 已有其他桥接在跑（手动启动的），不干预
            $bridgePid = $null
            $lastStartAt = $null
        }
    }
    Start-Sleep -Seconds $watchInterval
}