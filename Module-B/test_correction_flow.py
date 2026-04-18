#!/usr/bin/env python3
"""
Test script to verify correction request flow end-to-end.
Tests: List → Accept → Verify status updated
"""

import sys
sys.path.insert(0, '.')

from app import create_app
from app.db import get_db
from app.shard_router import (
    get_correction_requests_for_student,
    get_correction_request_by_id,
    update_correction_request_status,
    get_pending_corrections_for_course
)
import mysql.connector
from app.shard_router import SHARD_CONFIGS

def test_correction_flow():
    """Test the full correction request flow."""
    
    app = create_app()
    
    with app.app_context():
        db = get_db()
        
        print("=" * 80)
        print("CORRECTION REQUEST FLOW TEST")
        print("=" * 80)
        
        # Step 1: Get a pending correction request from MySQL
        print("\n1. Finding a pending correction request in MySQL shards...")
        pending_req = None
        for shard_id in SHARD_CONFIGS:
            try:
                cfg = SHARD_CONFIGS[shard_id]
                conn = mysql.connector.connect(
                    host=cfg['host'], port=cfg['port'],
                    user=cfg['user'], password=cfg['password'],
                    database=cfg['database'],
                    connection_timeout=5
                )
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    f"SELECT * FROM shard_{shard_id}_correction_requests "
                    "WHERE status='pending' LIMIT 1"
                )
                pending_req = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if pending_req:
                    print(f"   ✓ Found pending request in shard {shard_id}")
                    print(f"     req_id: {pending_req['req_id']}")
                    print(f"     student_id: {pending_req['student_id']}")
                    print(f"     course_id: {pending_req['course_id']}")
                    print(f"     status: {pending_req['status']}")
                    break
            except Exception as e:
                print(f"   ✗ Shard {shard_id}: {str(e)}")
                continue
        
        if not pending_req:
            print("   ✗ No pending correction requests found!")
            return False
        
        req_id = pending_req['req_id']
        student_id = pending_req['student_id']
        course_id = pending_req['course_id']
        
        # Step 2: Get instructor for this course
        print(f"\n2. Finding instructor for course {course_id}...")
        instructor = db.execute(
            "SELECT instructor_id FROM course_instructors WHERE course_id = ? LIMIT 1",
            (course_id,)
        ).fetchone()
        
        if not instructor:
            print(f"   ✗ No instructor found for course {course_id}")
            return False
        
        instructor_id = instructor['instructor_id']
        instructor_user = db.execute(
            "SELECT username FROM users WHERE user_id = ?",
            (instructor_id,)
        ).fetchone()
        
        print(f"   ✓ Instructor: {instructor_user['username']} (ID: {instructor_id})")
        
        # Step 3: Test get_correction_request_by_id
        print(f"\n3. Testing get_correction_request_by_id({req_id})...")
        req = get_correction_request_by_id(req_id)
        
        if not req:
            print(f"   ✗ get_correction_request_by_id returned None!")
            return False
        
        print(f"   ✓ Found request:")
        print(f"     req_id: {req['req_id']}")
        print(f"     student_id: {req['student_id']}")
        print(f"     course_id: {req['course_id']}")
        print(f"     status: {req['status']}")
        print(f"     acted_by: {req.get('acted_by')}")
        print(f"     acted_role: {req.get('acted_role')}")
        print(f"     acted_at: {req.get('acted_at')}")
        
        # Step 4: Test update_correction_request_status
        print(f"\n4. Testing update_correction_request_status({req_id}, 'accepted', {instructor_id}, 'instructor')...")
        success = update_correction_request_status(req_id, 'accepted', instructor_id, 'instructor')
        
        if not success:
            print(f"   ✗ update_correction_request_status returned False!")
            return False
        
        print(f"   ✓ Update successful")
        
        # Step 5: Verify the update
        print(f"\n5. Verifying the update...")
        updated_req = get_correction_request_by_id(req_id)
        
        if not updated_req:
            print(f"   ✗ Could not retrieve updated request!")
            return False
        
        print(f"   ✓ Updated request:")
        print(f"     req_id: {updated_req['req_id']}")
        print(f"     status: {updated_req['status']}")
        print(f"     acted_by: {updated_req.get('acted_by')}")
        print(f"     acted_role: {updated_req.get('acted_role')}")
        print(f"     acted_at: {updated_req.get('acted_at')}")
        
        if updated_req['status'] != 'accepted':
            print(f"   ✗ Status not updated! Expected 'accepted', got '{updated_req['status']}'")
            return False
        
        if updated_req.get('acted_by') != instructor_id:
            print(f"   ✗ acted_by not set! Expected {instructor_id}, got {updated_req.get('acted_by')}")
            return False
        
        if updated_req.get('acted_role') != 'instructor':
            print(f"   ✗ acted_role not set! Expected 'instructor', got '{updated_req.get('acted_role')}'")
            return False
        
        print(f"\n   ✅ ALL CHECKS PASSED!")
        
        # Step 6: Test get_correction_requests_for_student
        print(f"\n6. Testing get_correction_requests_for_student({student_id})...")
        student_reqs = get_correction_requests_for_student(student_id)
        
        print(f"   ✓ Found {len(student_reqs)} requests for student {student_id}")
        
        # Find our updated request
        our_req = next((r for r in student_reqs if r['req_id'] == req_id), None)
        if our_req:
            print(f"   ✓ Our request is in the list with status: {our_req['status']}")
        else:
            print(f"   ✗ Our request not found in student's list!")
        
        # Step 7: Rollback for next test
        print(f"\n7. Rolling back to 'pending' for next test...")
        rollback_success = update_correction_request_status(req_id, 'pending', None, None)
        
        # Manually set acted_* to NULL
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
            except Exception as e:
                continue
        
        print("\n" + "=" * 80)
        print("✅ TEST COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
        return True

if __name__ == "__main__":
    try:
        success = test_correction_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ TEST FAILED WITH EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
