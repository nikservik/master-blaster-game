#!/bin/sh
# Выводит в контекст сессии карту документов и постоянные правила проекта.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

echo "## Карта документов"
tree docs

for f in docs/documentation-rules.md docs/testing-rules.md docs/mode-piecemeal-growth.md; do
  [ -f "$f" ] || continue
  printf '\n## %s\n\n' "$f"
  cat "$f"
done
