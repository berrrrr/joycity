#Requires -Version 5.1
# JoyTalk Item Tracker launcher (PowerShell)
#   Doubleclick .bat 또는 직접 실행 가능.
#   인자: <preset_name> 또는 'custom' "<args>"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'

$toolsDir = Join-Path $PSScriptRoot 'tools'
Set-Location $toolsDir

$presetArg = if ($args.Count -gt 0) { $args[0] } else { $null }
$customArgs = $null

if (-not $presetArg) {
    Write-Host ""
    Write-Host "============================" -ForegroundColor Cyan
    Write-Host "  JoyTalk Item Tracker"
    Write-Host "============================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  1. default       (notify only + web UI)"
    Write-Host "  2. flower_farm   (auto pickup flowers)"
    Write-Host "  3. wander        (auto pickup + idle patrol)"
    Write-Host "  4. map_rotate    (auto pickup + map cycling)"
    Write-Host "  5. animal_hunt   (cycle 13 maps, follow pig/poo)"
    Write-Host "  6. custom        (enter args manually)"
    Write-Host ""

    $choice = Read-Host "Select [1-6]"

    switch ($choice.Trim()) {
        '1' { $presetArg = 'default' }
        '2' { $presetArg = 'flower_farm' }
        '3' { $presetArg = 'wander' }
        '4' { $presetArg = 'map_rotate' }
        '5' { $presetArg = 'animal_hunt' }
        '6' {
            $customArgs = Read-Host "Args (e.g. --filter flower --pickup --web)"
        }
        default {
            Write-Host "Invalid choice: '$choice'" -ForegroundColor Red
            Read-Host "Press Enter to close"
            exit 1
        }
    }
}
elseif ($presetArg -eq 'custom') {
    if ($args.Count -gt 1) {
        $customArgs = $args[1]
    } else {
        $customArgs = Read-Host "Args"
    }
}

Write-Host ""
if ($customArgs) {
    Write-Host "Launching with args: $customArgs" -ForegroundColor Green
    Write-Host ""
    $argList = $customArgs.Split(' ', [StringSplitOptions]::RemoveEmptyEntries)
    & py -3.11 -m item_tracker @argList
} else {
    Write-Host "Launching preset: $presetArg" -ForegroundColor Green
    Write-Host ""
    & py -3.11 -m item_tracker --preset $presetArg
}
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "  Tracker exited (code $exitCode)" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow
Read-Host "Press Enter to close"
