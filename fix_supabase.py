
import sys
import os
sys.path.append(os.getcwd())

from modules.supabase_service import init_supabase, is_cloud_mode, rename_session, delete_session, list_sessions

def fix_supabase():
    print("--- FIXING SUPABASE DATA ---")
    
    init_supabase()
    
    if not is_cloud_mode():
        print("❌ Not in cloud mode")
        return
    
    sessions = list_sessions()
    print(f"Found {len(sessions)} sessions")
    
    # Find the bad key
    bad_key = None
    for k in sessions.keys():
        print(f" - {k}")
        if "Inscripciones Liga Nacional" in k or "edición" in k.lower():
            bad_key = k
            
    if bad_key:
        print(f"\n🔍 Found bad key: {bad_key}")
        
        # Try to rename it first
        new_name = "Jugadores LNC 25-26 (Enero)"
        print(f"🛠️ Renaming to: {new_name}")
        
        success = rename_session(bad_key, new_name)
        if success:
            print("✅ Renamed successfully!")
        else:
            print("⚠️ Rename failed, trying delete...")
            # If rename fails, delete it
            delete_success = delete_session(bad_key)
            if delete_success:
                print("✅ Deleted successfully!")
            else:
                print("❌ Delete also failed")
    else:
        print("✅ No bad keys found")

if __name__ == "__main__":
    fix_supabase()
