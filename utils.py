import json
import os
import shutil
import tempfile
import logging

logger = logging.getLogger(__name__)

def safe_save_json(path, data):
    """
    Saves a dictionary to a JSON file atomically.
    Writes to a temp file first, then renames it to the target path.
    This prevents data corruption if the process crashes or network fails during write.
    """
    dir_name = os.path.dirname(path)
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name)
        
    try:
        # Create a temp file in the same directory to ensure atomic move works (same filesystem)
        fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        # Atomic replacement
        shutil.move(temp_path, path)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON to {path}: {e}")
        # Clean up temp file if it exists
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except: pass
        return False

def safe_load_json(path, default=None):
    """
    Safely loads a JSON file. Returns default if file doesn't exist or is corrupt.
    """
    if not os.path.exists(path):
        return default if default is not None else {}
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Corrupt JSON file found at {path}. Returning default.")
        return default if default is not None else {}
    except Exception as e:
        logger.error(f"Error loading JSON from {path}: {e}")
        return default if default is not None else {}
