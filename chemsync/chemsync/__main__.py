"""ChemSync - eLabFTW Chemical Database Synchronization Tool."""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="ChemSync - eLabFTW Chemical DB Sync")
    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")
    parser.add_argument("--csv", type=str, help="CSV file to import")
    parser.add_argument("--mapping", type=str, help="Mapping profile JSON file")
    parser.add_argument("--url", type=str, help="eLabFTW API URL")
    parser.add_argument("--api-key", type=str, help="eLabFTW API key")
    parser.add_argument("--category", type=int, default=17, help="Item category ID (default: 17)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode (default: on)")
    parser.add_argument("--execute", action="store_true", help="Actually execute sync (disables dry-run)")

    args = parser.parse_args()

    if args.gui:
        try:
            from chemsync.gui.main_window import run_gui
            run_gui()
        except ImportError:
            print("GUI requires PyQt6. Install with: pip install chemsync[gui]", file=sys.stderr)
            sys.exit(1)
    elif args.csv:
        from chemsync.engine.sync_engine import run_cli_sync
        run_cli_sync(
            csv_path=args.csv,
            mapping_path=args.mapping,
            url=args.url,
            api_key=args.api_key,
            category=args.category,
            dry_run=not args.execute,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
