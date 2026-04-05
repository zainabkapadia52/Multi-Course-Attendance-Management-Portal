import sys
import os
import threading
import random
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.table import Table
from database.column import Column
from database.transactions import Transaction

def clean():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

def run_brutal_isolation_tests():
    clean()
    print("=" * 70)
    print("Setting up BRUTAL schema for Isolation and Numerical Correctness...")

    # ---------------------------------------------------------
    # Schema Setup
    # ---------------------------------------------------------
    accounts = Table("accounts", "acc_id", [
        Column("acc_id", "INT", nullable=False),
        Column("balance", "INT", nullable=False)
    ])

    # A table to test partial-update isolation via Table's internal lock
    cols = [Column("id", "INT", nullable=False)] + [Column(f"flag_{i}", "INT", nullable=True) for i in range(50)]
    flags_table = Table("flags", "id", cols)
    
    print("\n[TEST 1] Multithreaded Brutal Inserts (Heap Integrity)")
    print("  Dynamically spawning 20 threads creating 100 accounts each.")
    
    NUM_THREADS = 20
    NUM_ACC_PER_THREAD = 100
    STARTING_BALANCE = 1000

    def insert_worker(t_id):
        for i in range(NUM_ACC_PER_THREAD):
            acc_id = t_id * 1000 + i
            accounts.insert({"acc_id": acc_id, "balance": STARTING_BALANCE})

    threads = [threading.Thread(target=insert_worker, args=(t,)) for t in range(NUM_THREADS)]
    for t in threads: t.start()
    for t in threads: t.join()

    all_accs = accounts.all_rows()
    total_accs = len(all_accs)
    assert total_accs == NUM_THREADS * NUM_ACC_PER_THREAD, f"Lost inserts! Expected {NUM_THREADS * NUM_ACC_PER_THREAD}, got {total_accs}"
    total_balance = sum(a["balance"] for a in all_accs)
    expected_balance = total_accs * STARTING_BALANCE
    assert total_balance == expected_balance, f"Numerical corruption! Expected {expected_balance}, got {total_balance}"
    print("  Success: Exact numerical values and row counts survived heavy concurrency perfectly.")

    # ---------------------------------------------------------
    # TEST 2: High Contention Partial Updates on the EXACT same row
    # ---------------------------------------------------------
    print("\n[TEST 2] High Contention Partial Updates (DB internal isolation)")
    print("  Spawning 50 threads. Each thread updates a UNIQUE column on the EXACT SAME row.")
    print("  If isolation drops reads/writes, columns will overwrite each other and go missing.")
    
    flags_table.insert({"id": 1}) # Insert empty row with 50 flag columns as None
    
    def flag_worker(flag_index):
        # Update only this specific column in-place.
        # Tests Table.update() internal serialized extraction/packing logic.
        flags_table.update(1, {f"flag_{flag_index}": 1})

    flag_threads = [threading.Thread(target=flag_worker, args=(i,)) for i in range(50)]
    for t in flag_threads: t.start()
    for t in flag_threads: t.join()

    flag_row = flags_table.find(1)
    sum_flags = sum(flag_row[f"flag_{i}"] for i in range(50) if flag_row.get(f"flag_{i}") is not None)
    print(f"  Final aggregated flag sum: {sum_flags} / 50")
    assert sum_flags == 50, f"Isolation failure! Expected sum 50, but got {sum_flags} (some updates got overwritten!)"
    print("  Success: Internal DB locking perfectly serialized partial updates on the same row!")

    # ---------------------------------------------------------
    # TEST 3: Serialized Concurrent Transactions (App-Level Locking)
    # ---------------------------------------------------------
    print("\n[TEST 3] Threaded Bank Transfers via Serialized Transactions")
    print("  Running thousands of randomized inter-account transfers.")
    print("  'Basic locking or serialized execution is sufficient', so we use a global lock to secure Transact windows.")
    
    txn_lock = threading.Lock()
    TRANSFER_THREADS = 10
    TRANSFERS_PER_THREAD = 200

    # Pre-fetch account IDs to randomly pick from
    acc_ids = [a["acc_id"] for a in accounts.all_rows()]

    def transfer_worker():
        for _ in range(TRANSFERS_PER_THREAD):
            a_id, b_id = random.sample(acc_ids, 2)
            amount = random.randint(1, 50)
            
            with txn_lock:  # Enforce serialized execution as requested by spec
                with Transaction(accounts) as txn:
                    a_row = txn.find(accounts, a_id)
                    b_row = txn.find(accounts, b_id)
                    
                    if a_row["balance"] >= amount:
                        txn.update(accounts, a_id, {"balance": a_row["balance"] - amount})
                        txn.update(accounts, b_id, {"balance": b_row["balance"] + amount})

    transfer_threads = [threading.Thread(target=transfer_worker) for _ in range(TRANSFER_THREADS)]
    for t in transfer_threads: t.start()
    for t in transfer_threads: t.join()

    # Re-calculate aggregate numerical balances to prove pure correctness
    final_accs = accounts.all_rows()
    final_balance = sum(a["balance"] for a in final_accs)
    
    print(f"  Original System Balance: {expected_balance}")
    print(f"  Final System Balance:    {final_balance}")
    assert final_balance == expected_balance, "CRITICAL ERROR: Money was lost or created during transactions! Numerical isolation failed!"
    print("  Success: Total network balance remained absolutely identical! Money was transferred perfectly.")

    print("\n" + "=" * 70)
    print("All BRUTAL numerical isolation and locking tests passed natively!")
    clean()

if __name__ == "__main__":
    run_brutal_isolation_tests()