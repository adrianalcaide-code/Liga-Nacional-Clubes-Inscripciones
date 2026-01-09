"""
Modules package for LNC Dashboard
"""
from .state import (
    load_history,
    save_history, 
    save_current_session,
    load_session_data,
    delete_session,
    rename_session,
    get_storage_mode
)

from .settings import SettingsManager

try:
    from .firebase_service import init_firebase, is_cloud_mode
except ImportError:
    def init_firebase():
        return None
    def is_cloud_mode():
        return False
