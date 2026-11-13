"""Standalone Windows Thermal Print Agent for DOINEEK Supershop.

Run on the shop Windows PC attached to the USB/POS thermal printer:
    python pc_print_agent.py          # Listen continuously via Firestore & local queue
    python pc_print_agent.py --check  # Show detected Windows printers & active target
    python pc_print_agent.py --test   # Print a test slip on the configured printer
"""

import argparse
import os
import sys
import time

os.environ.setdefault("SUPERSHOP_PC_PRINT_AGENT", "1")

import database
import remote_control
import thermal_printer


def main():
    parser = argparse.ArgumentParser(description="DOINEEK Supershop Windows Thermal Print Agent")
    parser.add_argument("--check", action="store_true", help="List detected Windows printers and exit")
    parser.add_argument("--test", action="store_true", help="Print a test receipt on the shop printer and exit")
    args = parser.parse_args()

    database.init_db()
    conn = database.get_connection()
    target = thermal_printer.resolve_target_printer(conn)
    conn.close()

    print("=" * 60)
    print("  DOINEEK Supershop - PC Thermal Print Agent")
    print("=" * 60)
    print(f"Detected printers: {thermal_printer.list_windows_printers()}")
    print(f"Active target printer: {target or 'NONE'}")

    if args.check:
        return

    if args.test:
        res = thermal_printer.enqueue_or_print_receipt(
            source_type="test",
            invoice_number="AGENT-TEST",
            requested_by="PC Agent",
            requested_from="pc_agent_cli",
        )
        print("Test print result:", res)
        return

    remote_control.start()
    print("[PC Print Agent] Listening for local & Firestore mobile print jobs... (Ctrl+C to stop)")

    try:
        while True:
            res = thermal_printer.process_pending_pc_print_jobs(limit=10)
            if res.get("printed", 0) or res.get("failed", 0):
                print(f"[PC Print Agent] Processed queue -> printed={res['printed']}, failed={res['failed']}")
            time.sleep(4)
    except KeyboardInterrupt:
        print("\n[PC Print Agent] Stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
