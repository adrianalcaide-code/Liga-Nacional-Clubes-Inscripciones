"""
State Management Module
Handles session persistence with Firebase (cloud) or JSON fallback (local).
"""
import os
import json
import pandas as pd
import streamlit as st
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to import Supabase service (preferred) or Firebase
try:
    from modules.supabase_service import (
        init_supabase as init_db, is_cloud_mode,
        save_session, load_session, list_sessions,
        delete_session as db_delete_session,
        rename_session as db_rename_session
    )
    DB_AVAILABLE = True
except ImportError:
    try:
        from modules.firebase_service import (
            init_firebase as init_db, is_cloud_mode,
            save_session, load_session, list_sessions,
            delete_session as db_delete_session,
            rename_session as db_rename_session
        )
        DB_AVAILABLE = True
    except ImportError:
        DB_AVAILABLE = False

# Local fallback paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSISTENCE_FILE = os.path.join(BASE_DIR, "historial_inscripciones.json")

# Custom JSON Encoder for DateTime
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime)):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if pd.isna(obj):
            return None
        return super().default(obj)

# ==================== LOCAL FALLBACK FUNCTIONS ====================

def _load_history_local():
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def _save_history_local(history_dict):
    try:
        with open(PERSISTENCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(history_dict, f, indent=4, ensure_ascii=False, cls=DateTimeEncoder)
        return True
    except Exception as e:
        logger.error(f"Error saving local history: {e}")
        return False

# ==================== PUBLIC API (Auto-selects Cloud or Local) ====================

def load_history() -> dict:
    """
    Load all session metadata.
    Returns dict of {session_name: {timestamp, count}}
    """
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return list_sessions()
    
    # Local fallback
    local_data = _load_history_local()
    return {
        name: {"timestamp": data.get("timestamp", ""), "count": len(data.get("data", []))}
        for name, data in local_data.items()
    }

def save_history(history_dict: dict) -> bool:
    """Save history dict (local mode only, cloud saves per-session)."""
    return _save_history_local(history_dict)

def save_current_session(file_name: str, df: pd.DataFrame) -> tuple[bool, str]:
    """
    Save a session with its DataFrame.
    Hybrid Strategy (Dual-Write):
    1. ALWAYS save to local JSON (as a mirror/backup).
    2. IF Cloud is available, save to Supabase.
    
    Returns (success, error_msg) based on the primary storage (Cloud if active, else Local).
    """
    # --- 1. LOCAL MIRROR SAVE ---
    local_success = False
    local_msg = ""
    try:
        history = _load_history_local()
        
        # PANDAS TO JSON
        json_str = df.to_json(orient='records', date_format='iso')
        data_records = json.loads(json_str)

        history[file_name] = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data_records,
            "mode": "mirror_backup" # Flag to indicate this is a mirror
        }
        if _save_history_local(history):
            local_success = True
            local_msg = "Saved to local mirror"
        else:
             local_msg = "Error writing local disk"
    except Exception as e:
        logger.error(f"Local mirror save failed: {e}")
        local_msg = str(e)

    # --- 2. CLOUD SAVE ---
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            # If in Cloud Mode, Cloud is the Source of Truth
            cloud_success, cloud_msg = save_session(file_name, df)
            
            if cloud_success:
                return True, "OK (Cloud + Local Mirror)"
            else:
                return False, f"Cloud Error: {cloud_msg} (Local: {local_msg})"
    
    # --- 3. LOCAL FALLBACK RESULT ---
    # If not in cloud mode, verify local success
    if local_success:
        return True, "OK (Local)"
    else:
        return False, local_msg

import unicodedata # Added for robust string matching

# ... (existing imports)

# ...

def load_session_data(file_name: str) -> pd.DataFrame:
    """Load a specific session's DataFrame."""
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return load_session(file_name)
    
    # Local fallback
    history = _load_history_local()
    
    # 1. Exact Match
    if file_name in history:
        target_key = file_name
    else:
        # 2. Robust/Fuzzy Match (Fallback)
        print(f"DEBUG: Exact match failed for '{file_name}'. Trying robust lookup...")
        target_key = None
        
        def norm(s): return unicodedata.normalize('NFC', str(s)).strip().lower()
        
        target_norm = norm(file_name)
        
        for k in history.keys():
            if norm(k) == target_norm:
                target_key = k
                break
            
    if target_key:
        print(f"DEBUG: Found target key '{target_key}' in history.")
        data = history[target_key].get("data", [])
        print(f"DEBUG: Data records count: {len(data)}")
        
        if not data:
            print("DEBUG: Data list is empty.")
            return pd.DataFrame() 
            
        df = pd.DataFrame(data)
        print(f"DEBUG: Initial DF Shape: {df.shape}")
        
        # Restore list columns with safety
        for col in df.columns:
            if df[col].dtype == object:
                def safe_json_load(x):
                    try:
                         if isinstance(x, str) and x.startswith('['):
                             return json.loads(x)
                    except:
                        pass
                    return x
                
                df[col] = df[col].apply(safe_json_load)
        
        print(f"DEBUG: Final DF Shape: {df.shape}")
        return df
    
    print(f"DEBUG: '{file_name}' NOT found in history keys: {list(history.keys())}")
    return None

def delete_session(file_name: str) -> bool:
    """Delete a session."""
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return db_delete_session(file_name)
    
    # Local fallback
    history = _load_history_local()
    if file_name in history:
        del history[file_name]
        return _save_history_local(history)
    return False

def rename_session(old_name: str, new_name: str) -> bool:
    """Rename a session."""
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return db_rename_session(old_name, new_name)
    
    # Local fallback
    history = _load_history_local()
    if old_name in history and new_name not in history:
        history[new_name] = history.pop(old_name)
        return _save_history_local(history)
    return False

def get_storage_mode() -> str:
    """Return current storage mode for UI display."""
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return "☁️ Supabase Cloud"
    return "💾 Local Storage"
