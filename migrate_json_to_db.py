"""
Migration script: Move JSON data to PostgreSQL database
Run this ONCE before deploying to Railway
Usage: python migrate_json_to_db.py
"""
import json
import os
from datetime import datetime
from database import db

def migrate_trendline_breaks():
    """Migrate trendline breaks from JSON to database"""
    breaks_file = "trendline_breaks.json"

    if not os.path.exists(breaks_file):
        print("  ℹ No trendline_breaks.json found, skipping...")
        return

    try:
        with open(breaks_file, "r") as f:
            data = json.load(f)

        breaks = data.get("breaks", [])
        print(f"  📥 Migrating {len(breaks)} trendline breaks...")

        for brk in breaks:
            db.save_trendline_break({
                "date": brk.get("date"),
                "time": brk.get("time"),
                "symbol": brk.get("symbol", "SPY"),
                "direction": brk.get("direction"),
                "price": brk.get("price"),
                "is_manual": brk.get("manual", False)
            })

        print(f"  ✓ Migrated {len(breaks)} trendline breaks")
    except Exception as e:
        print(f"  ✗ Error migrating trendline breaks: {e}")

def migrate_manual_trades():
    """Migrate manual trades from JSON to database"""
    trades_file = "manual_trades.json"

    if not os.path.exists(trades_file):
        print("  ℹ No manual_trades.json found, skipping...")
        return

    try:
        with open(trades_file, "r") as f:
            trades = json.load(f)

        print(f"  📥 Migrating {len(trades)} manual trades...")

        for trade in trades:
            # Only migrate closed trades (open ones restart)
            if trade.get("closed"):
                db.save_manual_trade({
                    "id": trade.get("id"),
                    "entry_date": trade.get("entry_date"),
                    "entry_time": trade.get("entry_time"),
                    "entry_price": trade.get("entry_price"),
                    "direction": trade.get("direction"),
                    "signal": trade.get("snapshot", {}).get("signal"),
                    "conf_score": trade.get("snapshot", {}).get("conf_tv"),
                    "snapshot": trade.get("snapshot")
                })

                # Close the trade
                if trade.get("exit_price"):
                    db.close_manual_trade(trade.get("id"), trade.get("exit_price"))

        print(f"  ✓ Migrated {len(trades)} manual trades")
    except Exception as e:
        print(f"  ✗ Error migrating manual trades: {e}")

def backup_json_files():
    """Create backup of JSON files before migration"""
    print("\n📋 Creating backups...")

    files_to_backup = [
        "signals.json",
        "paper_trades.json",
        "manual_trades.json",
        "trendline_breaks.json"
    ]

    backup_dir = "json_backups"
    os.makedirs(backup_dir, exist_ok=True)

    for file in files_to_backup:
        if os.path.exists(file):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"{file}.{timestamp}.backup")
            try:
                with open(file, "r") as f:
                    content = f.read()
                with open(backup_path, "w") as f:
                    f.write(content)
                print(f"  ✓ Backed up {file} → {backup_path}")
            except Exception as e:
                print(f"  ✗ Error backing up {file}: {e}")

def main():
    print("\n" + "="*60)
    print("SPY Trader: JSON → PostgreSQL Migration")
    print("="*60)

    # Check if database is connected
    if not db.is_connected:
        print("\n❌ Database not connected!")
        print("   Make sure DATABASE_URL is set in .env")
        return False

    print("\n✓ Database connected")

    # Backup JSON files
    backup_json_files()

    # Migrate data
    print("\n📊 Migrating data...")
    migrate_trendline_breaks()
    migrate_manual_trades()

    print("\n" + "="*60)
    print("✓ Migration complete!")
    print("="*60)
    print("\nNext steps:")
    print("  1. Verify data in database (query your tables)")
    print("  2. Test dashboard loads signals correctly")
    print("  3. Deploy to Railway: git push origin main")
    print("  4. Delete JSON files after confirming all data migrated")
    print("\n")

    return True

if __name__ == "__main__":
    main()
