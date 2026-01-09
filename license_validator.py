"""
License Validator Module (Cloud-Compatible)
Handles license validation with Firebase cache or local fallback.
Selenium scraping is disabled in cloud mode - use manual CSV upload or local mode.
"""
import pandas as pd
import os
import json
from datetime import datetime, timedelta
import logging
import io
import streamlit as st

logger = logging.getLogger(__name__)

# Try to import Supabase service (preferred) or Firebase
try:
    from modules.supabase_service import (
        init_supabase as init_db, is_cloud_mode,
        load_licenses_cache, save_licenses_cache
    )
    DB_AVAILABLE = True
except ImportError:
    try:
        from modules.firebase_service import (
            init_firebase as init_db, is_cloud_mode,
            load_licenses_cache, save_licenses_cache
        )
        DB_AVAILABLE = True
    except ImportError:
        DB_AVAILABLE = False

# Local paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "fesba_cache.json")

FESBA_LOGIN_URL = "https://www.badminton.es/member/login.aspx"
CACHE_MAX_AGE_HOURS = 24  # Increased for cloud storage

class LicenseValidator:
    def __init__(self):
        self.licenses_db = {}
        self.last_update_timestamp = None
        self._cloud_mode = False
    
    def load_full_db(self, force_refresh=False):
        """
        Load the license database.
        Tries Firebase cache first, then local cache.
        force_refresh only works in local mode with Selenium available.
        """
        logger.info(f"load_full_db called with force_refresh={force_refresh}")
        
        # 1. Initialize Supabase if available
        if DB_AVAILABLE:
            init_db()
            self._cloud_mode = is_cloud_mode()
        
        # 2. Try Supabase cache first
        if self._cloud_mode and not force_refresh:
            licenses, timestamp = load_licenses_cache()
            if licenses:
                self.licenses_db = licenses
                self.last_update_timestamp = timestamp
                age = datetime.now() - timestamp if timestamp else timedelta(hours=999)
                return True, f"☁️ Cargados {len(self.licenses_db)} registros desde Supabase (Hace {age.seconds//3600}h {age.seconds%3600//60}m)"
        
        # 3. Try local cache
        if os.path.exists(CACHE_PATH) and not force_refresh:
            try:
                with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    timestamp_str = cache_data.get('timestamp')
                    if timestamp_str:
                        last_update = datetime.fromisoformat(timestamp_str)
                        age = datetime.now() - last_update
                        
                        if age < timedelta(hours=CACHE_MAX_AGE_HOURS):
                            self.licenses_db = {int(k): v for k, v in cache_data.get('data', {}).items()}
                            self.last_update_timestamp = last_update
                            
                            # Sync to Firebase if available
                            if self._cloud_mode:
                                save_licenses_cache(self.licenses_db, self.last_update_timestamp)
                            
                            return True, f"💾 Cargados {len(self.licenses_db)} registros desde caché local"
            except Exception as e:
                logger.error(f"Error reading local cache: {e}")
        
        # 4. If cloud mode and no cache, return instructions
        if self._cloud_mode:
            return False, "⚠️ No hay caché de licencias. Usa 'Importar CSV' para cargar datos desde la web FESBA."
        
        # 5. In local mode, try Selenium scraping
        return self._try_selenium_scraping()
    
    def _try_selenium_scraping(self):
        """Attempt Selenium scraping (only works locally with Chrome installed)."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
            import requests
            import urllib.parse
            
            logger.info("Selenium available, attempting web scraping...")
            
            # Initialize driver
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(60)
            
            try:
                # Login
                user, pwd = self._get_credentials()
                if not user or not pwd:
                    return False, "❌ Credenciales no encontradas. Configura el archivo de credenciales."
                
                driver.get(FESBA_LOGIN_URL)
                wait = WebDriverWait(driver, 20)
                
                user_field = wait.until(EC.presence_of_element_located(
                    (By.ID, "container_content_ctl00_cphPage_cphPage_pnlLogin_UserName")))
                user_field.send_keys(user)
                
                pass_field = driver.find_element(By.ID, "container_content_ctl00_cphPage_cphPage_pnlLogin_Password")
                pass_field.send_keys(pwd)
                
                submit_btn = driver.find_element(By.ID, "container_content_ctl00_cphPage_cphPage_pnlLogin_LoginButton")
                submit_btn.click()
                
                import time
                time.sleep(5)
                
                if "login.aspx" in driver.current_url:
                    return False, "❌ Login fallido - verifica credenciales"
                
                # Navigate to export
                DEFAULT_ORG_ID = "093CE26F-CD57-4A6E-9039-AD8A498DFAB4"
                admin_url = f"https://www.badminton.es/organization/admin.aspx?id={DEFAULT_ORG_ID}&p=1"
                driver.get(admin_url)
                time.sleep(3)
                
                export_url = f"https://www.badminton.es/organization/export/group_members_export.aspx?id={DEFAULT_ORG_ID}&ft=1"
                
                # Download with requests
                cookies = driver.get_cookies()
                session = requests.Session()
                for cookie in cookies:
                    session.cookies.set(cookie['name'], cookie['value'])
                
                response = session.get(export_url)
                
                if response.status_code == 200:
                    try:
                        csv_content = response.content.decode('utf-8')
                    except UnicodeDecodeError:
                        csv_content = response.content.decode('latin-1')
                    
                    count = self._process_csv_content(csv_content)
                    
                    if count > 0:
                        self.last_update_timestamp = datetime.now()
                        self._save_to_local_cache()
                        
                        if self._cloud_mode:
                            save_licenses_cache(self.licenses_db, self.last_update_timestamp)
                        
                        return True, f"✅ Base actualizada: {count} jugadores procesados"
                
                return False, "❌ Error descargando CSV de FESBA"
                
            finally:
                driver.quit()
                
        except ImportError:
            return False, "⚠️ Selenium no disponible. Usa 'Importar CSV' para cargar datos manualmente."
        except Exception as e:
            logger.error(f"Selenium scraping error: {e}")
            return False, f"❌ Error: {str(e)}"
    
    def import_from_csv(self, csv_file):
        """
        Import licenses from a manually uploaded CSV file.
        Works in both cloud and local mode.
        """
        try:
            if hasattr(csv_file, 'getvalue'):
                content = csv_file.getvalue().decode('utf-8')
            else:
                content = csv_file.read().decode('utf-8')
            
            count = self._process_csv_content(content)
            
            if count > 0:
                self.last_update_timestamp = datetime.now()
                
                # Save to both local and cloud
                self._save_to_local_cache()
                if self._cloud_mode:
                    save_licenses_cache(self.licenses_db, self.last_update_timestamp)
                
                return True, f"✅ Importados {count} jugadores desde CSV"
            
            return False, "❌ No se encontraron jugadores en el CSV"
            
        except Exception as e:
            logger.error(f"CSV import error: {e}")
            return False, f"❌ Error importando CSV: {str(e)}"
    
    def _process_csv_content(self, csv_content):
        """Process CSV content and update licenses_db."""
        try:
            df = pd.read_csv(io.StringIO(csv_content), sep=';', on_bad_lines='skip', dtype=str)
            df.columns = df.columns.str.strip()
            
            count = 0
            
            for _, row in df.iterrows():
                try:
                    # Filter by role
                    rol = str(row.get('Rol', '')).strip().lower()
                    if rol != 'jugador':
                        continue
                    
                    # Get license ID
                    raw_id = row.get('Nº de licencia')
                    if pd.isna(raw_id) or not raw_id:
                        continue
                    
                    pid_str = str(raw_id).replace('.', '').replace(',', '').strip()
                    if not pid_str.isdigit():
                        continue
                    player_id = int(pid_str)
                    
                    # Build name
                    nombre = str(row.get('Nombre', '')).strip()
                    apellido1 = str(row.get('Apellido 1', '')).strip()
                    apellido2 = str(row.get('Apellido 2', '')).strip()
                    if apellido2 in ['-', 'nan', 'None']:
                        apellido2 = ""
                    full_name = f"{nombre} {apellido1} {apellido2}".strip()
                    
                    # Extract license data
                    ambito = str(row.get('Ambito de la licencia', '')).strip()
                    categoria = str(row.get('Categoría', '')).strip()
                    fecha_fin_str = str(row.get('Fecha de finalización', '')).strip()
                    club = str(row.get('Grupo', '')).strip()
                    sexo = str(row.get('Sexo', '')).strip()
                    dob = str(row.get('Fecha de Nacimiento', '')).strip()
                    
                    # Validate expiry
                    is_valid = False
                    if fecha_fin_str and fecha_fin_str.lower() not in ['nan', 'none', '']:
                        try:
                            exp_date = datetime.strptime(fecha_fin_str, "%d/%m/%Y")
                            is_valid = exp_date >= datetime.now()
                        except:
                            is_valid = '2025' in fecha_fin_str or '2026' in fecha_fin_str
                    
                    tipo_licencia = f"{ambito} - {categoria}"
                    
                    # Update DB (prefer valid over invalid)
                    existing = self.licenses_db.get(player_id)
                    if existing and existing.get('valid') and not is_valid:
                        continue
                    
                    self.licenses_db[player_id] = {
                        'name': full_name,
                        'valid': is_valid,
                        'type': tipo_licencia,
                        'end_date': fecha_fin_str,
                        'club': club,
                        'gender': sexo,
                        'dob': dob,
                        'status': 'OK' if is_valid else 'Caducada'
                    }
                    count += 1
                    
                except Exception:
                    continue
            
            logger.info(f"Processed {count} valid players from CSV")
            return count
            
        except Exception as e:
            logger.error(f"Error processing CSV: {e}")
            return 0
    
    def validate_dataframe(self, df, search_mode=False):
        """Validate licenses in DataFrame against database."""
        results = []
        
        if not self.licenses_db:
            return ["⚠️ DB no cargada"] * len(df)
        
        for _, row in df.iterrows():
            pid = row.get('Nº.ID')
            try:
                pid = int(pid)
                if pid in self.licenses_db:
                    info = self.licenses_db[pid]
                    tipo = info.get('type', '')
                    activa = info.get('valid', False)
                    fecha_fin = info.get('end_date', '?')
                    club_licencia = info.get('club', 'Desconocido')
                    
                    if (("Nacional" in tipo) or ("Homologada" in tipo) or ("HN" in tipo)) and activa:
                        results.append(f"✅ {tipo} ({fecha_fin}) - {club_licencia}")
                    elif not activa:
                        results.append(f"❌ Caducada ({fecha_fin})")
                    else:
                        results.append(f"⚠️ {tipo} (No Nac.)")
                else:
                    results.append("❌ NO ENCONTRADO")
            except:
                results.append("⚠️ ID Inválido")
        
        return results
    
    def _save_to_local_cache(self):
        """Save to local JSON cache."""
        try:
            from utils import safe_save_json
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "data": self.licenses_db
            }
            safe_save_json(CACHE_PATH, cache_data)
        except Exception as e:
            logger.error(f"Error saving local cache: {e}")
    
    def _get_credentials(self):
        """Get credentials from Streamlit secrets or local file."""
        # Try Streamlit secrets first
        if "fesba" in st.secrets:
            return st.secrets["fesba"].get("username"), st.secrets["fesba"].get("password")
        
        # Fallback to local file
        ROOT_DIR = os.path.dirname(BASE_DIR)
        CREDENTIALS_PATH = os.path.join(ROOT_DIR, "Credenciales", "Credenciales")
        
        if not os.path.exists(CREDENTIALS_PATH):
            return None, None
        
        try:
            with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    return data.get("username"), data.get("password")
                except json.JSONDecodeError:
                    f.seek(0)
                    lines = f.readlines()
                    u, p = None, None
                    for l in lines:
                        if "usuario:" in l.lower():
                            u = l.split(":", 1)[1].strip()
                        if "contraseña:" in l.lower():
                            p = l.split(":", 1)[1].strip()
                    return u, p
        except Exception:
            return None, None
    
    def get_storage_mode(self):
        """Return current storage mode for display."""
        if self._cloud_mode:
            return "☁️ Firebase"
        return "💾 Local"


# Global validator instance
validator = LicenseValidator()
