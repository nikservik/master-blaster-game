# Основной прогон: спеки и технические тесты игры без окна (gdUnit4).
# Время управляемое: --fixed-fps 60 — один кадр равен одному шагу физики, независимо от реального времени.
# -Window: те же спеки с окном; дополнительно проверяется захват курсора ОС (MOV-S17).
param([switch]$Window)
$ErrorActionPreference = 'Stop'
$game = Join-Path $PSScriptRoot 'game'
$godot = (Get-Command godot_console).Source

# Свежий клон: сначала импорт, чтобы Godot знал классы проекта и аддонов.
if (-not (Test-Path (Join-Path $game '.godot'))) {
	& $godot --headless --path $game --import | Out-Null
}

# -c: не останавливаться на первом провале.
$runner = @('-s', 'res://addons/gdUnit4/bin/GdUnitCmdTool.gd', '-c', '-a', 'res://specs', '-a', 'res://tests')
if ($Window) {
	& $godot --fixed-fps 60 --path $game @runner
} else {
	& $godot --headless --fixed-fps 60 --path $game @runner --ignoreHeadlessMode
}
exit $LASTEXITCODE
