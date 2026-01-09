import os
import json
import streamlit as st

# Define path relative to project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "fuzzy_threshold": 0.80,
    "theme": "light",
    "last_viewed_file": None
}

class SettingsManager:
    def __init__(self):
        self.settings = self.load_settings()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return DEFAULT_SETTINGS.copy()
        return DEFAULT_SETTINGS.copy()

    def save_settings(self, new_settings):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_settings, f, indent=4)
            self.settings = new_settings
            return True
        except Exception as e:
            st.error(f"Error guardando configuración: {e}")
            return False

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings(self.settings)
