import sys
sys.path.append('.')
from modules.supabase_service import init_supabase

client = init_supabase()
if client:
    res = client.table('inscripciones').select('name, data, columns').eq('name', 'LNC_Enero_2026').execute()
    
    if res.data:
        row = res.data[0]
        print(f"Session: {row['name']}")
        print(f"Data type: {type(row['data'])}")
        
        data = row['data']
        if isinstance(data, list):
            print(f"Data is list with {len(data)} items")
            if data:
                print(f"First item keys: {list(data[0].keys())[:5]}")
        elif isinstance(data, str):
            print(f"Data is STRING (length {len(data)})")
            print(f"First 200 chars: {data[:200]}")
        else:
            print(f"Data is {type(data)}")
    else:
        print("Session not found")
else:
    print("Supabase client not initialized")
