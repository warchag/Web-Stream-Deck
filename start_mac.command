#!/bin/zsh
cd "$(dirname "$0")" || exit 1

PORT="${WEB_DECK_PORT:-5001}"
TOKEN="${WEB_DECK_TOKEN:-1234}"
URL="http://127.0.0.1:${PORT}/?token=${TOKEN}"

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "Python 3 not found. Please install Python 3 first."
  read "?Press Enter to close..."
  exit 1
fi

echo "Starting Web Stream Deck..."
echo "Deck URL: ${URL}"

(sleep 1.2 && open "${URL}") &
"${PYTHON}" app.py
