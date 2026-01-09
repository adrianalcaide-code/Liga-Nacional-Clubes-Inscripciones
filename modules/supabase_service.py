"""
Supabase Service Module
Handles all Supabase operations for cloud persistence.
Supabase provides PostgreSQL database with REST API.
"""
import streamlit as st
import json
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Flag to track if running in cloud mode
_supabase_available = False
_client = None

def init_supabase():
    """
    Initialize Supabase connection using Streamlit secrets.
    Returns Supabase client or None if not available.
    """
    global _supabase_available, _client
    
    if _client is not None:
        return _client
    
    try:
        from supabase import create_client, Client
        
        # Load from Streamlit secrets
        if "supabase" in st.secrets:
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
            _client = create_client(url, key)
            _supabase_available = True
            logger.info("Supabase initialized successfully")
            return _client
        else:
            logger.warning("Supabase secrets not found - running in local mode")
            _supabase_available = False
            return None
            
    except ImportError:
        logger.warning("supabase-py not installed - running in local mode")
        _supabase_available = False
        return None
    except Exception as e:
        logger.error(f"Supabase initialization error: {e}")
        _supabase_available = False
        return None

def is_cloud_mode():
    """Check if running with Supabase cloud storage."""
    return _supabase_available

# ==================== INSCRIPCIONES (Sessions) ====================

def save_session(session_name: str, df: pd.DataFrame) -> tuple[bool, str]:
    """Save an inscription session to Supabase. Returns (success, error_msg)."""
    client = init_supabase()
    if client is None:
        return False, "Cliente Supabase no inicializado"
    
    try:
        # Convert DataFrame to JSON-safe format
        df_save = df.copy()
        
        # CLEANUP: Replace NaN with None (JSON null) to avoid "Out of range float values" error
        # Cast to object first so None isn't forced back to NaN in float columns
        df_save = df_save.astype(object).where(pd.notnull(df_save), None)
        
        for col in df_save.select_dtypes(include=['datetime64[ns]']).columns:
            df_save[col] = df_save[col].dt.strftime('%Y-%m-%d')
        
        # Handle list columns
        for col in df_save.columns:
            df_save[col] = df_save[col].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else x
            )
        
        data = {
            "name": session_name,
            "timestamp": datetime.now().isoformat(),
            "data": df_save.to_dict(orient='records'),
            "columns": list(df_save.columns)
        }
        
        # Upsert (insert or update)
        client.table("inscripciones").upsert(data, on_conflict="name").execute()
        logger.info(f"Session '{session_name}' saved to Supabase")
        return True, "OK"
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        return False, str(e)

def load_session(session_name: str) -> pd.DataFrame:
    """Load an inscription session from Supabase."""
    client = init_supabase()
    if client is None:
        return None
    
    try:
        result = client.table("inscripciones").select("*").eq("name", session_name).execute()
        if result.data:
            record = result.data[0]
            df = pd.DataFrame(record["data"])
            
            # Restore list columns
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].apply(
                        lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else x
                    )
            return df
        return None
    except Exception as e:
        logger.error(f"Error loading session: {e}")
        return None

def list_sessions() -> dict:
    """List all available sessions from Supabase."""
    client = init_supabase()
    if client is None:
        return {}
    
    try:
        result = client.table("inscripciones").select("name, timestamp, data").execute()
        sessions = {}
        for record in result.data:
            sessions[record["name"]] = {
                "timestamp": record.get("timestamp", ""),
                "count": len(record.get("data", []))
            }
        return sessions
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return {}

def delete_session(session_name: str) -> bool:
    """Delete a session from Supabase."""
    client = init_supabase()
    if client is None:
        return False
    
    try:
        client.table("inscripciones").delete().eq("name", session_name).execute()
        logger.info(f"Session '{session_name}' deleted")
        return True
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return False

def rename_session(old_name: str, new_name: str) -> bool:
    """Rename a session in Supabase."""
    client = init_supabase()
    if client is None:
        return False
    
    try:
        client.table("inscripciones").update({"name": new_name}).eq("name", old_name).execute()
        logger.info(f"Session renamed: '{old_name}' -> '{new_name}'")
        return True
    except Exception as e:
        logger.error(f"Error renaming session: {e}")
        return False

# ==================== CONFIG (Rules, Equivalences, Categories) ====================

def save_config(config_name: str, data: dict) -> bool:
    """Save configuration to Supabase."""
    client = init_supabase()
    if client is None:
        return False
    
    try:
        record = {
            "name": config_name,
            "data": data,
            "updated_at": datetime.now().isoformat()
        }
        client.table("config").upsert(record, on_conflict="name").execute()
        logger.info(f"Config '{config_name}' saved")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

def load_config(config_name: str, default: dict = None) -> dict:
    """Load configuration from Supabase."""
    client = init_supabase()
    if client is None:
        return default or {}
    
    try:
        result = client.table("config").select("data").eq("name", config_name).execute()
        if result.data:
            return result.data[0].get("data", default or {})
        return default or {}
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return default or {}

# ==================== LICENCIAS CACHE ====================

def save_licenses_cache(licenses_db: dict, timestamp: datetime = None) -> bool:
    """Save licenses database to Supabase."""
    client = init_supabase()
    if client is None:
        return False
    
    try:
        record = {
            "name": "members",
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "count": len(licenses_db),
            "data": licenses_db  # Supabase handles JSON natively
        }
        client.table("licencias_cache").upsert(record, on_conflict="name").execute()
        logger.info(f"Licenses cache saved: {len(licenses_db)} records")
        return True
    except Exception as e:
        logger.error(f"Error saving licenses cache: {e}")
        return False

def load_licenses_cache() -> tuple:
    """
    Load licenses cache from Supabase.
    Returns: (licenses_dict, timestamp) or (None, None) if not found.
    """
    client = init_supabase()
    if client is None:
        return None, None
    
    try:
        result = client.table("licencias_cache").select("*").eq("name", "members").execute()
        if result.data:
            record = result.data[0]
            licenses = record.get("data", {})
            # Convert string keys back to int
            licenses = {int(k): v for k, v in licenses.items()}
            timestamp = datetime.fromisoformat(record.get("timestamp", "")) if record.get("timestamp") else None
            logger.info(f"Licenses cache loaded: {len(licenses)} records")
            return licenses, timestamp
        return None, None
    except Exception as e:
        logger.error(f"Error loading licenses cache: {e}")
        return None, None
