# Рабочее место

Разработка идёт на Windows-компьютере с видеокартой. Агент — Claude Code в `C:\Dev\master-blaster-game`: он работает с редакторами через MCP, а Сергей ведёт его с Мака или телефона через Remote Control.

## Запуск агента

```powershell
claude --continue --dangerously-skip-permissions --remote-control "Master Blaster"
```

Режим `bypassPermissions` задаёт `permissions.defaultMode` в `%USERPROFILE%\.claude\settings.json`. С Мака этот режим не включается, а сессия, запущенная в нём на Windows, в нём и остаётся. MCP-серверы подхватываются только после перезапуска Claude.

## Программы

Всё ставится через winget.

| Программа | Версия | Доступ из PowerShell |
|---|---|---|
| Godot, стандартная сборка без .NET | 4.7.2 | `godot`, `godot_console` (`%LOCALAPPDATA%\Microsoft\WinGet\Links`) |
| Blender | 5.2.1 LTS | `blender` (`C:\Program Files\Blender Foundation\Blender 5.2` в PATH) |
| uv | 0.12.19 | `uvx` |

## MCP

Оба сервера подключены в scope `user`, телеметрия выключена.

| Сервер | Что нужно для работы | Подключение |
|---|---|---|
| `blender` — [mcp-for-blender](https://github.com/ahujasid/blender-mcp) | Blender открыт с окном: аддон сам поднимает сервер на порту 9876, в `--background` его нет | `uvx --python 3.11 mcp-for-blender`, `DISABLE_TELEMETRY=true`. Аддон ставится командой `uvx mcp-for-blender install-addon` |
| `godot-ai` — [godot-ai](https://github.com/hi-godot/godot-ai) 4.2.3 | Редактор Godot открыт с окном и с включённым плагином `addons/godot_ai` | `godot-ai attach --port 8000 --ws-port 9500 --disable-telemetry`. Команду генерирует сам плагин (`ClientConfigurator.configure("claude_code")`) |

Плагин godot-ai лежит в каждом Godot-проекте, в `addons/godot_ai/`, и включается в `project.godot`, в секции `[editor_plugins]`. Архив релиза сверяется по SHA256 из манифеста; подпись `.sig` не проверялась.

## Что учитывать

- Редакторы агент открывает сам. Во время импорта окно Godot должно быть на переднем плане и не свёрнуто: в фоне Godot почти не перерисовывается, и импорт стоит на месте. Если импорт завис, агент выводит окно вперёд (`SetForegroundWindow`).
- Сцены и игру можно запускать без окна и без MCP: `godot_console --headless --path <проект> res://<сцена>.tscn --quit-after <кадры>`.
- `.blend` Godot импортирует сам через установленный Blender.
- В Blender через MCP нельзя вызывать `read_factory_settings`: он выгружает аддон MCP.
