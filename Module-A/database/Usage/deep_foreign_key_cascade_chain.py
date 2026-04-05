import sys
import os
# Add parent directory to path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.table import Table
from database.column import Column

def cleanup():
    for f in os.listdir("."):
        if f.endswith(".heap") or f.endswith(".wal") or f.endswith(".meta.json"):
            os.remove(f)

def print_all(msg, db_objs):
    print(f"\n--- {msg} ---")
    for name, table in db_objs.items():
        print(f"Table {name}: {len(table.all_rows())} rows")
        for row in table.all_rows():
            print(f"  {row}")

def test_deep_cascading():
    cleanup()
    print("Setting up deeply nested schema...")

    # schema definition
    countries = Table("countries", "id", [
        Column("id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])

    states = Table("states", "id", [
        Column("id", "INT", nullable=False),
        Column("country_id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])
    states.add_foreign_key("country_id", countries, "id", on_delete="CASCADE")

    cities = Table("cities", "id", [
        Column("id", "INT", nullable=False),
        Column("state_id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])
    cities.add_foreign_key("state_id", states, "id", on_delete="CASCADE")

    universities = Table("universities", "id", [
        Column("id", "INT", nullable=False),
        Column("city_id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])
    universities.add_foreign_key("city_id", cities, "id", on_delete="CASCADE")

    students = Table("students", "id", [
        Column("id", "INT", nullable=False),
        Column("university_id", "INT", nullable=True, default=None),
        Column("name", "VARCHAR(50)")
    ])
    students.add_foreign_key("university_id", universities, "id", on_delete="SET NULL")

    courses = Table("courses", "id", [
        Column("id", "INT", nullable=False),
        Column("name", "VARCHAR(50)")
    ])

    enrollments = Table("enrollments", "id", [
        Column("id", "INT", nullable=False),
        Column("student_id", "INT", nullable=True),
        Column("course_id", "INT", nullable=True)
    ])
    enrollments.add_foreign_key("student_id", students, "id", on_delete="CASCADE")
    enrollments.add_foreign_key("course_id", courses, "id", on_delete="CASCADE")

    db_objs = {
        "countries": countries,
        "states": states,
        "cities": cities,
        "universities": universities,
        "students": students,
        "courses": courses,
        "enrollments": enrollments
    }

    print("\nInserting data (1 Country -> 2 States -> 4 Cities -> 4 Universities -> 8 Students -> 16 Enrollments)")
    
    countries.insert({"id": 1, "name": "India"})
    
    states.insert({"id": 1, "country_id": 1, "name": "Maharashtra"})
    states.insert({"id": 2, "country_id": 1, "name": "Karnataka"})
    
    cities.insert({"id": 1, "state_id": 1, "name": "Mumbai"})
    cities.insert({"id": 2, "state_id": 1, "name": "Pune"})
    cities.insert({"id": 3, "state_id": 2, "name": "Bangalore"})
    cities.insert({"id": 4, "state_id": 2, "name": "Mysore"})
    
    universities.insert({"id": 1, "city_id": 1, "name": "Mumbai Uni"})
    universities.insert({"id": 2, "city_id": 2, "name": "Pune Uni"})
    universities.insert({"id": 3, "city_id": 3, "name": "Bangalore Uni"})
    universities.insert({"id": 4, "city_id": 4, "name": "Mysore Uni"})

    for i in range(1, 9):
        students.insert({"id": i, "university_id": (i-1)//2 + 1, "name": f"Student {i}"})
        
    courses.insert({"id": 1, "name": "CS101"})
    courses.insert({"id": 2, "name": "CS102"})
    
    for i in range(1, 17):
        enrollments.insert({"id": i, "student_id": (i-1)//2 + 1, "course_id": 1 if i%2 != 0 else 2})

    print_all("INITIAL STATE", db_objs)
    
    print("\n[TEST 1] ON DELETE CASCADE: Delete City Pune (ID 2)")
    print("Expectation: Pune Uni (ID 2) deleted -> Students 3,4 university_id set to NULL -> Enrollments for students 3,4 remain intact.")
    cities.delete(2)
    
    assert universities.find(2) is None
    assert students.find(3)["university_id"] is None
    assert students.find(4)["university_id"] is None
    assert len(enrollments.all_rows()) == 16
    print("Success: Test 1 Passed.")
    
    print("\n[TEST 2] ON DELETE CASCADE: Delete State Karnataka (ID 2)")
    print("Expectation: Bangalore & Mysore deleted -> Bangalore Uni & Mysore Uni deleted -> Students 5,6,7,8 university_id set to NULL -> Enrollments remain intact.")
    states.delete(2)
    
    assert cities.find(3) is None
    assert cities.find(4) is None
    assert universities.find(3) is None
    assert universities.find(4) is None
    assert students.find(5)["university_id"] is None
    assert students.find(8)["university_id"] is None
    assert len(enrollments.all_rows()) == 16
    print("Success: Test 2 Passed.")
    
    print("\n[TEST 3] ON DELETE CASCADE: Delete Course CS101 (ID 1)")
    print("Expectation: All odd numbered enrollments deleted.")
    courses.delete(1)
    
    for i in range(1, 17):
        if i % 2 != 0:
            assert enrollments.find(i) is None
        else:
            assert enrollments.find(i) is not None
    print("Success: Test 3 Passed.")

    print("\n[TEST 4] ON DELETE CASCADE: Delete Country India (ID 1)")
    print("Expectation: State Maharashtra deleted -> City Mumbai deleted -> Mumbai Uni deleted -> Students 1,2 university_id set to NULL. States, Cities, Universities empty.")
    countries.delete(1)
    
    assert len(states.all_rows()) == 0
    assert len(cities.all_rows()) == 0
    assert len(universities.all_rows()) == 0
    assert students.find(1)["university_id"] is None
    print("Success: Test 4 Passed.")
    
    print("\n[TEST 5] ON DELETE CASCADE: Delete Students 1 and 3")
    print("Expectation: Enrollments associated with Student 1 and 3 deleted. (Only even enrollments exist, let's see which ones).")
    students.delete(1)
    students.delete(3)
    
    # enrollments for student 1 are 1, 2. But 1 is deleted (CS101). 2 (CS102) remains.
    # enrollments for student 3 are 5, 6. But 5 is deleted (CS101). 6 (CS102) remains.
    assert enrollments.find(2) is None
    assert enrollments.find(6) is None
    assert enrollments.find(4) is not None
    print("Success: Test 5 Passed.")
    
    print("\nAll CASCADE assertions passed successfully!\n")
    print_all("FINAL STATE", db_objs)

    cleanup()

if __name__ == "__main__":
    test_deep_cascading()
