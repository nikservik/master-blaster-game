#!/bin/sh
# Копирует код симуляции в WSL (~/ml/eco): диск C там не подключён. Запуск из Git Bash на Windows.
set -e
DST="//wsl.localhost/Ubuntu-24.04/home/nikservik/ml/eco"
[ -d "$DST" ] || mkdir "$DST"
cp -r "$(dirname "$0")/ecosystem/." "$DST/"
