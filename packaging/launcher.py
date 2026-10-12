"""Entry point for the downloadable app. Double-click it and ProofDesk opens in your browser."""
import sys

from proofdesk.cli import main

if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001 - a friendly message beats a window that vanishes
        print(f"\nProofDesk could not start: {exc}")
        code = 1
    if code:
        try:
            input("\nPress Enter to close this window.")
        except EOFError:
            pass
    sys.exit(code)
