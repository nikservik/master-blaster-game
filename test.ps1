# Основной прогон: спеки и технические тесты игры без окна (gdUnit4).
# Время управляемое: --fixed-fps 60 — один кадр равен одному шагу физики, независимо от реального времени.
$ErrorActionPreference = 'Stop'
$game = Join-Path $PSScriptRoot 'game'
$godot = (Get-Command godot_console).Source

# Свежий клон: сначала импорт, чтобы Godot знал классы проекта и аддонов.
if (-not (Test-Path (Join-Path $game '.godot'))) {
	& $godot --headless --path $game --import | Out-Null
}

# -c: не останавливаться на первом провале.
& $godot --headless --fixed-fps 60 --path $game `
	-s res://addons/gdUnit4/bin/GdUnitCmdTool.gd --ignoreHeadlessMode -c -a res://specs -a res://tests
exit $LASTEXITCODE
