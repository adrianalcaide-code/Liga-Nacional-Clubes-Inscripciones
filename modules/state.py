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
    """Save a session with its DataFrame. Returns (success, error_msg)."""
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return save_session(file_name, df)
    
    # Local fallback
    try:
        history = _load_history_local()
        df_save = df.copy()
        
        # CLEANUP: Replace NaN with None
        df_save = df_save.astype(object).where(pd.notnull(df_save), None)
        
        # Convert dates to string for JSON serialization
        for col in df_save.select_dtypes(include=['datetime64[ns]']).columns:
            df_save[col] = df_save[col].dt.strftime('%Y-%m-%d')
        
        # Handle list columns
        for col in df_save.columns:
            df_save[col] = df_save[col].apply(
                lambda x: x if not isinstance(x, list) else json.dumps(x)
            )
        
        data_records = df_save.to_dict(orient='records')
        history[file_name] = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data_records
        }
        if _save_history_local(history):
            return True, "OK"
        return False, "Error al escribir en disco local"
    except Exception as e:
        return False, str(e)

def load_session_data(file_name: str) -> pd.DataFrame:
    """Load a specific session's DataFrame."""
    if DB_AVAILABLE:
        init_db()
        if is_cloud_mode():
            return load_session(file_name)
    
    # Local fallback
    history = _load_history_local()
    if file_name in history:
        data = history[file_name].get("data", [])
        df = pd.DataFrame(data)
        # Restore list columns
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(
                    lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x
                )
        return df
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
