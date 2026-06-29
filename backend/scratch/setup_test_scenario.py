import sys
import sqlite3

def setup_db(scenario):
    conn = sqlite3.connect('healthify.db')
    cursor = conn.cursor()
    
    if scenario == 'capacity':
        # Put Bangalore Central PHC near Bangalore with 5 beds
        cursor.execute("""
            UPDATE facilities 
            SET lat = 12.9710, lng = 77.5940, available_beds = 5 
            WHERE name = 'Bangalore Central PHC'
        """)
        conn.commit()
        print("Scenario: Capacity set. Bangalore Central PHC is near Bangalore with 5 beds.")
        
    elif scenario == 'no_capacity':
        # Set all facilities' available beds to 0
        cursor.execute("UPDATE facilities SET available_beds = 0")
        conn.commit()
        print("Scenario: No Capacity. All facilities set to 0 available beds.")
        
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        setup_db(sys.argv[1])
    else:
        print("Provide scenario: capacity or no_capacity")
