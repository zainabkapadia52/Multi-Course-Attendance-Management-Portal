#!/usr/bin/env python3
"""
Test HTTP endpoints for correction requests.
Simulates actual browser requests.
"""

import sys
sys.path.insert(0, '.')

from app import create_app
import json

def test_http_endpoints():
    """Test correction request endpoints via HTTP."""
    
    app = create_app()
    client = app.test_client()
    
    print("=" * 80)
    print("HTTP ENDPOINT TEST")
    print("=" * 80)
    
    # Step 1: Login as instructor
    print("\n1. Logging in as instructor (prof_singh)...")
    response = client.post('/api/auth/login', 
                          json={'username': 'prof_singh', 'password': 'password123'},
                          content_type='application/json')
    
    if response.status_code != 200:
        print(f"   ✗ Login failed: {response.status_code}")
        print(f"   Response: {response.get_json()}")
        return False
    
    print(f"   ✓ Login successful")
    
    # Step 2: Get correction requests list
    print("\n2. Getting correction requests list...")
    response = client.get('/api/instructor/corrections')
    
    if response.status_code != 200:
        print(f"   ✗ List failed: {response.status_code}")
        print(f"   Response: {response.get_json()}")
        return False
    
    corrections = response.get_json()
    print(f"   ✓ Found {len(corrections)} correction requests")
    
    # Find a pending request
    pending = next((c for c in corrections if c['status'] == 'pending'), None)
    
    if not pending:
        print(f"   ✗ No pending requests found!")
        print(f"   All requests: {[c['status'] for c in corrections]}")
        return False
    
    req_id = pending['req_id']
    print(f"   ✓ Found pending request: req_id={req_id}")
    print(f"     Student: {pending.get('student_name')}")
    print(f"     Course: {pending.get('course_name')}")
    print(f"     Status: {pending['status']}")
    
    # Step 3: Accept the correction request
    print(f"\n3. Accepting correction request {req_id}...")
    response = client.post(f'/api/instructor/corrections/{req_id}/accept',
                          content_type='application/json')
    
    if response.status_code != 200:
        print(f"   ✗ Accept failed: {response.status_code}")
        print(f"   Response: {response.get_json()}")
        return False
    
    result = response.get_json()
    print(f"   ✓ Accept successful: {result.get('message')}")
    
    # Step 4: Verify the status changed
    print(f"\n4. Verifying status changed...")
    response = client.get('/api/instructor/corrections')
    
    if response.status_code != 200:
        print(f"   ✗ List failed: {response.status_code}")
        return False
    
    corrections = response.get_json()
    updated_req = next((c for c in corrections if c['req_id'] == req_id), None)
    
    if not updated_req:
        print(f"   ✗ Request {req_id} not found in list!")
        return False
    
    print(f"   ✓ Found request in list:")
    print(f"     req_id: {updated_req['req_id']}")
    print(f"     status: {updated_req['status']}")
    
    if updated_req['status'] != 'accepted':
        print(f"   ✗ Status not updated! Expected 'accepted', got '{updated_req['status']}'")
        return False
    
    print(f"   ✅ Status correctly updated to 'accepted'")
    
    # Step 5: Get logs for this request
    print(f"\n5. Getting logs for request {req_id}...")
    response = client.get(f'/api/instructor/corrections/{req_id}/logs')
    
    if response.status_code != 200:
        print(f"   ✗ Logs failed: {response.status_code}")
        print(f"   Response: {response.get_json()}")
        return False
    
    logs = response.get_json()
    print(f"   ✓ Found {len(logs)} log entries")
    
    if logs:
        log = logs[0]
        print(f"     Action: {log.get('action')}")
        print(f"     Role: {log.get('role')}")
        print(f"     Username: {log.get('username')}")
        print(f"     Acted at: {log.get('acted_at')}")
    
    # Step 6: Rollback for next test
    print(f"\n6. Rolling back to 'pending' for next test...")
    from app.shard_router import SHARD_CONFIGS
    import mysql.connector
    
    for shard_id in SHARD_CONFIGS:
        try:
            cfg = SHARD_CONFIGS[shard_id]
            conn = mysql.connector.connect(
                host=cfg['host'], port=cfg['port'],
                user=cfg['user'], password=cfg['password'],
                database=cfg['database'],
                connection_timeout=5
            )
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE shard_{shard_id}_correction_requests "
                "SET status='pending', acted_by=NULL, acted_role=NULL, acted_at=NULL "
                "WHERE req_id = %s",
                (req_id,)
            )
            conn.commit()
            if cursor.rowcount > 0:
                print(f"   ✓ Rolled back in shard {shard_id}")
            cursor.close()
            conn.close()
        except Exception:
            continue
    
    print("\n" + "=" * 80)
    print("✅ HTTP TEST COMPLETED SUCCESSFULLY")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    try:
        success = test_http_endpoints()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ TEST FAILED WITH EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
