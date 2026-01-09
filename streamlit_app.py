"""
Liga Nacional de Clubes - Sistema de Revisión de Inscripciones
Entry point for Streamlit Cloud deployment.

This wrapper ensures proper module imports and Firebase initialization
before launching the main application.
"""
import streamlit as st
import sys
import os

# Ensure the current directory is in the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize Firebase early (before other imports that might need it)
from modules.firebase_service import init_firebase
init_firebase()

# Now run the main application
# We use exec to run main.py in this context
exec(open(os.path.join(os.path.dirname(__file__), "main.py"), encoding="utf-8").read())
