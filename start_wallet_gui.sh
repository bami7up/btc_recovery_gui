#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

SCRIPT="wallet_recovery_gui_final.py"
if [[ ! -f "$SCRIPT" ]]; then
  echo "[ERROR] Не найден $SCRIPT в $(pwd)"
  exit 1
fi

run_with_python() {
  local py="$1"
  if command -v "$py" >/dev/null 2>&1; then
    echo "[INFO] Запуск через $py"
    exec "$py" "$SCRIPT"
  fi
}

run_with_python python3.12
run_with_python python3
run_with_python python

echo "[WARN] Python не найден."
if command -v apt-get >/dev/null 2>&1; then
  echo "[INFO] Пробую установить python3 и python3-tk через apt-get (может запросить sudo)..."
  if sudo apt-get update && sudo apt-get install -y python3 python3-tk; then
    exec python3 "$SCRIPT"
  fi
fi

echo "[ERROR] Не удалось автоматически установить Python."
echo "Установите Python 3.12+ и tkinter, затем повторите запуск:"
echo "  python3 wallet_recovery_gui_final.py"
exit 1
