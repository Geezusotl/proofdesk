#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PYTHONPATH="$PWD/src"
if command -v python3 >/dev/null 2>&1; then
  python3 -m proofdesk
else
  echo
  echo "ProofDesk needs Python 3, which is not installed on this computer."
  echo "A download page will open. Install Python, then double-click this file again."
  (command -v xdg-open >/dev/null && xdg-open "https://www.python.org/downloads/") || open "https://www.python.org/downloads/"
fi
echo
read -r -p "Press Return to close this window."
