"""
Firebase Service Module
Handles all Firebase Firestore operations for cloud persistence.
"""
import streamlit as st
import json
from datetime import datetime
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Flag to track if running in cloud mode
_firebase_available = False
_db = None

def init_firebase():
    """
    Initialize Firebase connection using Streamlit secrets.
    Returns Firestore client or None if not available.
    """
    global _firebase_available, _db
    
    if _db is not None:
        return _db
    
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        if not firebase_admin._apps:
            # Load credentials from Streamlit secrets
            if "firebase" in st.secrets:
                cred_dict = dict(st.secrets["firebase"])
                # Fix private key newlines
                if "private_key" in cred_dict:
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                _db = firestore.client()
                _firebase_available = True
                logger.info("Firebase initialized successfully")
            else:
                logger.warning("Firebase secrets not found - running in local mode")
                _firebase_available = False
                return None
        else:
            _db = firestore.client()
            _firebase_available = True
            
        return _db
    except ImportError:
        logger.warning("firebase-admin not installed - running in local mode")
        _firebase_available = False
        return None
    except Exception as e:
        logger.error(f"Firebase initialization error: {e}")
        _firebase_available = False
        return None

def is_cloud_mode():
    """Check if running with Firebase cloud storage."""
    return _firebase_available

# ==================== INSCRIPCIONES (Sessions) ====================

def save_session(session_name: str, df: pd.DataFrame) -> bool:
    """Save an inscription session to Firestore."""
    db = init_firebase()
    if db is None:
        return False
    
    try:
        # Convert DataFrame to records
        df_save = df.copy()
        for col in df_save.select_dtypes(include=['datetime64[ns]']).columns:
            df_save[col] = df_save[col].dt.strftime('%Y-%m-%d')
        
        # Handle list columns
        for col in df_save.columns:
            df_save[col] = df_save[col].apply(
                lambda x: x if not isinstance(x, list) else json.dumps(x)
            )
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "data": df_save.to_dict(orient='records'),
            "columns": list(df_save.columns)
        }
        
        db.collection("inscripciones").document(session_name).set(data)
        logger.info(f"Session '{session_name}' saved to Firestore")
        return True
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        return False

def load_session(session_name: str) -> pd.DataFrame:
    """Load an inscription session from Firestore."""
    db = init_firebase()
    if db is None:
        return None
    
    try:
        doc = db.collection("inscripciones").document(session_name).get()
        if doc.exists:
            data = doc.to_dict()
            df = pd.DataFrame(data["data"])
            
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
    """List all available sessions from Firestore."""
    db = init_firebase()
    if db is None:
        return {}
    
    try:
        sessions = {}
        docs = db.collection("inscripciones").stream()
        for doc in docs:
            data = doc.to_dict()
            sessions[doc.id] = {
                "timestamp": data.get("timestamp", ""),
                "count": len(data.get("data", []))
            }
        return sessions
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return {}

def delete_session(session_name: str) -> bool:
    """Delete a session from Firestore."""
    db = init_firebase()
    if db is None:
        return False
    
    try:
        db.collection("inscripciones").document(session_name).delete()
        logger.info(f"Session '{session_name}' deleted")
        return True
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return False

def rename_session(old_name: str, new_name: str) -> bool:
    """Rename a session in Firestore."""
    db = init_firebase()
    if db is None:
        return False
    
    try:
        # Get old document
        old_doc = db.collection("inscripciones").document(old_name).get()
        if not old_doc.exists:
            return False
        
        # Create new document with same data
        db.collection("inscripciones").document(new_name).set(old_doc.to_dict())
        
        # Delete old document
        db.collection("inscripciones").document(old_name).delete()
        
        logger.info(f"Session renamed: '{old_name}' -> '{new_name}'")
        return True
    except Exception as e:
        logger.error(f"Error renaming session: {e}")
        return False

# ==================== CONFIG (Rules, Equivalences, Categories) ====================

def save_config(config_name: str, data: dict) -> tuple[bool, str]:
    """Save configuration to Firestore."""
    db = init_firebase()
    if db is None:
        return False, "Firebase not initialized"
    
    try:
        db.collection("config").document(config_name).set(data)
        logger.info(f"Config '{config_name}' saved")
        return True, "OK"
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False, str(e)

def load_config(config_name: str, default: dict = None) -> dict:
    """Load configuration from Firestore."""
    db = init_firebase()
    if db is None:
        return default or {}
    
    try:
        doc = db.collection("config").document(config_name).get()
        if doc.exists:
            return doc.to_dict()
        return default or {}
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return default or {}

# ==================== LICENCIAS CACHE ====================

def save_licenses_cache(licenses_db: dict, timestamp: datetime = None) -> bool:
    """Save licenses database to Firestore."""
    db = init_firebase()
    if db is None:
        return False
    
    try:
        # Firestore has 1MB document limit, so we batch if necessary
        # For now, save as single doc (typical cache is ~3MB, may need sharding)
        data = {
            "timestamp": (timestamp or datetime.now()).isoformat(),
            "count": len(licenses_db),
            # Store as JSON string to avoid nested object limits
            "data": json.dumps(licenses_db)
        }
        db.collection("licencias_cache").document("members").set(data)
        logger.info(f"Licenses cache saved: {len(licenses_db)} records")
        return True
    except Exception as e:
        logger.error(f"Error saving licenses cache: {e}")
        return False

def load_licenses_cache() -> tuple:
    """
    Load licenses cache from Firestore.
    Returns: (licenses_dict, timestamp) or (None, None) if not found.
    """
    db = init_firebase()
    if db is None:
        return None, None
    
    try:
        doc = db.collection("licencias_cache").document("members").get()
        if doc.exists:
            data = doc.to_dict()
            licenses = json.loads(data.get("data", "{}"))
            # Convert string keys back to int
            licenses = {int(k): v for k, v in licenses.items()}
            timestamp = datetime.fromisoformat(data.get("timestamp", ""))
            logger.info(f"Licenses cache loaded: {len(licenses)} records")
            return licenses, timestamp
        return None, None
    except Exception as e:
        logger.error(f"Error loading licenses cache: {e}")
        return None, None
