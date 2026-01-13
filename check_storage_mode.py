
import sys
import os
sys.path.append(os.getcwd())

from modules.state import DB_AVAILABLE, get_storage_mode

print(f"DB_AVAILABLE: {DB_AVAILABLE}")
print(f"Storage Mode: {get_storage_mode()}")

if DB_AVAILABLE:
    try:
        from modules.supabase_service import is_cloud_mode, list_sessions
        print(f"is_cloud_mode(): {is_cloud_mode()}")
        
        if is_cloud_mode():
            print("\n--- SUPABASE SESSIONS ---")
            sessions = list_sessions()
            for k in sessions.keys():
                print(f" - {k}")
    except Exception as e:
        print(f"Supabase error: {e}")
