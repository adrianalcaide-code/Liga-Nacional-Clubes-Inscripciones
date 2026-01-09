"""
Rules Manager Module
Handles configuration persistence with Firebase (cloud) or JSON fallback (local).
"""
import json
import os
import logging

logger = logging.getLogger(__name__)

# Try to import Supabase service (preferred) or Firebase
try:
    from modules.supabase_service import (
        init_supabase as init_db, is_cloud_mode,
        save_config, load_config
    )
    DB_AVAILABLE = True
except ImportError:
    try:
        from modules.firebase_service import (
            init_firebase as init_db, is_cloud_mode,
            save_config, load_config
        )
        DB_AVAILABLE = True
    except ImportError:
        DB_AVAILABLE = False

# Local paths
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
RULES_FILE = os.path.join(CONFIG_DIR, "rules.json")
EQUIVALENCES_FILE = os.path.join(CONFIG_DIR, "equivalences.json")
CATEGORIES_FILE = os.path.join(CONFIG_DIR, "team_categories.json")

# --- DEFAULT VALUES (Table 9.1 from FESBA regulations) ---
DEFAULT_RATIO_TABLE = [
    {"total": 4, "max_cedidos": 1, "min_propios": 3},
    {"total": 5, "max_cedidos": 1, "min_propios": 4},
    {"total": 6, "max_cedidos": 2, "min_propios": 4},
    {"total": 7, "max_cedidos": 2, "min_propios": 5},
    {"total": 8, "max_cedidos": 2, "min_propios": 6},
    {"total": 9, "max_cedidos": 3, "min_propios": 6},
    {"total": 10, "max_cedidos": 3, "min_propios": 7},
]

DEFAULT_RULES_CONFIG = {
    "División de Honor": {
        "min_total": 10,
        "max_total": 20,
        "min_gender": 5,
        "ratio_table": DEFAULT_RATIO_TABLE,
        "require_loan_doc": True,
        "require_declaration": True,
        "allow_loaned_players": True,
        "allow_non_selectable": True,
        "non_selectable_minors_only": False
    },
    "Primera ORO": {
        "min_total": 10,
        "max_total": 20,
        "min_gender": 5,
        "ratio_table": DEFAULT_RATIO_TABLE,
        "require_loan_doc": True,
        "require_declaration": True,
        "allow_loaned_players": True,
        "allow_non_selectable": True,
        "non_selectable_minors_only": False
    },
    "Primera PLATA": {
        "min_total": 8,
        "max_total": 20,
        "min_gender": 4,
        "ratio_table": DEFAULT_RATIO_TABLE,
        "require_loan_doc": True,
        "require_declaration": True,
        "allow_loaned_players": True,
        "allow_non_selectable": True,
        "non_selectable_minors_only": False
    },
    "Primera BRONCE": {
        "min_total": 8,
        "max_total": 20,
        "min_gender": 4,
        "ratio_table": DEFAULT_RATIO_TABLE,
        "require_loan_doc": True,
        "require_declaration": True,
        "allow_loaned_players": True,
        "allow_non_selectable": True,
        "non_selectable_minors_only": False
    },
    "Segunda ORO": {
        "min_total": 6,
        "max_total": 20,
        "min_gender": 3,
        "ratio_table": DEFAULT_RATIO_TABLE,
        "require_loan_doc": True,
        "require_declaration": True,
        "allow_loaned_players": True,
        "allow_non_selectable": True,
        "non_selectable_minors_only": False
    }
}

DEFAULT_EQUIVALENCES = {
    "Club Bádminton Ravachol Pontevedra": ["Club Bádminton As Neves"],
    "Club Bádminton San Fernando Valencia": ["Club Bádminton Xàtiva"],
    "Club Bádminton Arjonilla": ["Club Bádminton Alhaurín de la Torre"],
    "Club Bádminton Alicante": ["Club Bádminton El Campello"],
    "Club Bádminton Oviedo": ["Club Bádminton Vegadeo"],
    "Club Bádminton Benalmádena": ["Club Bádminton Jorge Guillén"],
    "Club Bádminton Pitiús": ["Club Bádminton Ibiza"],
    "Club Bádminton Rinconada": ["Club Bádminton La Unión"]
}

# ==================== LOCAL FILE OPERATIONS ====================

def _safe_load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return default if default is not None else {}

def _safe_save_json(path, data):
    try:
        dir_name = os.path.dirname(path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")
        return False

# ==================== RULES MANAGER CLASS ====================

class RulesManager:
    def __init__(self):
        self._db_init = False
        self._ensure_config_exists()
    
    def _init_db_if_needed(self):
        if not self._db_init and DB_AVAILABLE:
            init_db()
            self._db_init = True
    
    def _ensure_config_exists(self):
        """Ensure local config files exist for fallback."""
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        
        if not os.path.exists(RULES_FILE):
            self.save_rules(DEFAULT_RULES_CONFIG)
            
        if not os.path.exists(EQUIVALENCES_FILE):
            self.save_equivalences(DEFAULT_EQUIVALENCES)
    
    # ==================== RULES ====================
    
    def load_rules(self) -> dict:
        self._init_db_if_needed()
        if DB_AVAILABLE and is_cloud_mode():
            data = load_config("rules", DEFAULT_RULES_CONFIG)
            if "rules" in data:
                return data["rules"]
            return data if data else DEFAULT_RULES_CONFIG
        return _safe_load_json(RULES_FILE, DEFAULT_RULES_CONFIG)
    
    def save_rules(self, rules: dict) -> bool:
        self._init_db_if_needed()
        if DB_AVAILABLE and is_cloud_mode():
            return save_config("rules", {"rules": rules})
        return _safe_save_json(RULES_FILE, rules)
    
    # ==================== EQUIVALENCES ====================
    
    def load_equivalences(self) -> dict:
        self._init_db_if_needed()
        if DB_AVAILABLE and is_cloud_mode():
            data = load_config("equivalences", DEFAULT_EQUIVALENCES)
            if "equivalences" in data:
                return data["equivalences"]
            return data if data else DEFAULT_EQUIVALENCES
        return _safe_load_json(EQUIVALENCES_FILE, DEFAULT_EQUIVALENCES)
    
    def save_equivalences(self, eq_data: dict) -> bool:
        self._init_db_if_needed()
        if DB_AVAILABLE and is_cloud_mode():
            return save_config("equivalences", {"equivalences": eq_data})
        return _safe_save_json(EQUIVALENCES_FILE, eq_data)
    
    # ==================== TEAM CATEGORIES ====================
    
    def load_team_categories(self) -> dict:
        self._init_db_if_needed()
        if DB_AVAILABLE and is_cloud_mode():
            data = load_config("team_categories", {})
            if "categories" in data:
                return data["categories"]
            return data if data else {}
        return _safe_load_json(CATEGORIES_FILE, {})
    
    def save_team_categories(self, categories: dict) -> bool:
        self._init_db_if_needed()
        if DB_AVAILABLE and is_cloud_mode():
            return save_config("team_categories", {"categories": categories})
        return _safe_save_json(CATEGORIES_FILE, categories)
    
    # ==================== UTILITIES ====================
    
    def get_categories_list(self) -> list:
        rules = self.load_rules()
        return list(rules.keys())
