"""Test trực tiếp API endpoints mà không cần chạy server."""
import sys
sys.path.insert(0, ".")

import database
import utils

# Test 1: DB accounts
print("=== DB ACCOUNTS ===")
accounts = database.get_all_accounts()
print(f"Total accounts: {len(accounts)}")
for acc in accounts[:10]:
    print(f"  - {acc}")

# Test 2: Storage stats
print("\n=== STORAGE STATS ===")
import os
root = database.get_setting("download_folder", "")
print(f"Download folder from DB: {root}")
print(f"Folder exists: {os.path.exists(root)}")
if os.path.exists(root):
    items = os.listdir(root)
    print(f"Items in folder: {items}")
    for item in items:
        full = os.path.join(root, item)
        print(f"  - {item} ({'DIR' if os.path.isdir(full) else 'FILE'})")

# Test 3: Username validation
print("\n=== USERNAME VALIDATION ===")
test_names = ["test", "user123", "john_doe", "../etc", "<script>", ".."]
for name in test_names:
    print(f"  {name!r:20} -> clean={utils.clean_username(name)!r:20} valid={utils.is_valid_username(name)}")
