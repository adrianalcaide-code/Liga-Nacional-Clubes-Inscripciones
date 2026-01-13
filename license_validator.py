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
                
                # Fix Datetime Offset Error
                now = datetime.now()
                if timestamp and timestamp.tzinfo:
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                
                age = now - timestamp if timestamp else timedelta(hours=999)
                return True, f"☁️ Cargados {len(self.licenses_db)} registros desde Supabase (Hace {age.seconds//3600}h {age.seconds%3600//60}m)"
        
        # 3. Try local cache
        if os.path.exists(CACHE_PATH) and not force_refresh:
            try:
                with open(CACHE_PATH, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    timestamp_str = cache_data.get('timestamp')
                    if timestamp_str:
                        last_update = datetime.fromisoformat(timestamp_str)
                        
                        # Fix Datetime Offset Error (Local Cache)
                        now = datetime.now()
                        if last_update.tzinfo:
                            from datetime import timezone
                            now = datetime.now(timezone.utc)
                            
                        age = now - last_update
                        
                        if age < timedelta(hours=CACHE_MAX_AGE_HOURS):
                            self.licenses_db = {int(k): v for k, v in cache_data.get('data', {}).items()}
                            self.last_update_timestamp = last_update
                            
                            # Sync to Firebase if available
                            if self._cloud_mode:
                                save_licenses_cache(self.licenses_db, self.last_update_timestamp)
                            
                            return True, f"💾 Cargados {len(self.licenses_db)} registros desde caché local"
            except Exception as e:
                logger.error(f"Error reading local cache: {e}")
        
        # 4. No cache found - try Selenium scraping (works locally with Chrome)
        # This will work regardless of cloud mode setting
        success, msg = self._try_selenium_scraping()
        
        # 5. If Selenium succeeded and we're in cloud mode, sync to Supabase
        if success and self._cloud_mode:
            save_licenses_cache(self.licenses_db, self.last_update_timestamp)
        
        return success, msg
    
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
            # chrome_options.add_argument("--headless")  # Comentado para ver el proceso (Petición usuario)
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
                
                # Extract Organization ID dynamically from URL
                # URL format: .../admin.aspx?id=ORGANIZATION_GUID&p=1
                current_url = driver.current_url
                parsed = urllib.parse.urlparse(current_url)
                params = urllib.parse.parse_qs(parsed.query)
                
                org_id = params.get('id', [None])[0]
                
                if not org_id:
                     # Fallback to default if not found
                     logger.warning("Could not extract Org ID from URL, using default")
                     org_id = "093CE26F-CD57-4A6E-9039-AD8A498DFAB4"
                else:
                    logger.info(f"Extracted Org ID: {org_id}")
                
                # Navigate to export
                # Note: We are already at admin.aspx, so we just construct the export URL
                export_url = f"https://www.badminton.es/organization/export/group_members_export.aspx?id={org_id}&ft=1"
                
                # Download with requests - SYNC HEADERS
                cookies = driver.get_cookies()
                user_agent = driver.execute_script("return navigator.userAgent;")
                admin_url = driver.current_url  # Use current URL as Referer
                
                session = requests.Session()
                session.headers.update({
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
                    'Referer': admin_url
                })
                
                for cookie in cookies:
                    session.cookies.set(cookie['name'], cookie['value'])
                
                logger.info(f"Downloading from: {export_url}")
                response = session.get(export_url)
                logger.info(f"Export response status: {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        csv_content = response.content.decode('utf-8')
                    except UnicodeDecodeError:
                        csv_content = response.content.decode('latin-1')
                    
                    # Check if we got HTML instead of CSV (login redirect)
                    if '<html' in csv_content.lower()[:500] or 'login' in csv_content.lower()[:500]:
                        logger.error("Got HTML instead of CSV - likely login redirect")
                        return False, "❌ Sesión expirada o credenciales incorrectas. Verifica usuario/contraseña."
                    
                    count = self._process_csv_content(csv_content)
                    logger.info(f"Processed {count} players from CSV")
                    
                    if count > 0:
                        self.last_update_timestamp = datetime.now()
                        self._save_to_local_cache()
                        
                        if self._cloud_mode:
                            save_licenses_cache(self.licenses_db, self.last_update_timestamp)
                        
                        return True, f"✅ Base actualizada: {count} jugadores procesados"
                    else:
                        logger.error(f"CSV processing returned 0 players. Content preview: {csv_content[:200]}")
                        return False, "❌ CSV descargado pero sin jugadores válidos. Formato puede haber cambiado."
                else:
                    logger.error(f"Export failed with status {response.status_code}: {response.text[:200]}")
                    return False, f"❌ Error descargando CSV (HTTP {response.status_code})"
                
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
                        'country': str(row.get('Nacionalidad', 'España')).strip() or 'España',
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
    
    def update_player_data_from_db(self, df):
        """
        Update player personal data (name, gender, dob, country, club) from license DB.
        Returns updated DataFrame and count of updated players.
        """
        if not self.licenses_db:
            return df, 0
        
        updated_count = 0
        
        for idx, row in df.iterrows():
            pid = row.get('Nº.ID')
            try:
                pid = int(pid)
                if pid in self.licenses_db:
                    info = self.licenses_db[pid]
                    
                    # Check if player needs update (has placeholder data like "Manual-" or "?")
                    jugador = str(row.get('Jugador', ''))
                    nombre = str(row.get('Nombre', ''))
                    
                    if 'Manual-' in jugador or nombre in ['?', ''] or 'NUEVO-' in jugador:
                        changes = []  # Track what changed
                        
                        # Extract name parts from DB
                        full_name = info.get('name', '')
                        parts = full_name.split()
                        
                        if len(parts) >= 3:
                            nombre_db = parts[0]
                            apellido1 = parts[1]
                            apellido2 = " ".join(parts[2:])
                        elif len(parts) == 2:
                            nombre_db = parts[0]
                            apellido1 = parts[1]
                            apellido2 = ""
                        else:
                            nombre_db = full_name
                            apellido1, apellido2 = "", ""
                        
                        # Track and update fields
                        old_nombre = row.get('Nombre', '')
                        if old_nombre != apellido1:
                            changes.append(f"Nombre: {old_nombre} → {apellido1}")
                        df.at[idx, 'Nombre'] = apellido1
                        df.at[idx, '2ºNombre'] = apellido2
                        df.at[idx, 'Nombre.1'] = nombre_db
                        
                        old_genero = row.get('Género', '')
                        new_genero = info.get('gender', old_genero)
                        if old_genero != new_genero and new_genero:
                            changes.append(f"Género: {old_genero} → {new_genero}")
                        df.at[idx, 'Género'] = new_genero
                        
                        old_fnac = row.get('F.Nac', '')
                        new_fnac = info.get('dob', old_fnac)
                        if old_fnac != new_fnac and new_fnac:
                            changes.append(f"F.Nac: {old_fnac} → {new_fnac}")
                        df.at[idx, 'F.Nac'] = new_fnac
                        
                        old_club = row.get('Club', '')
                        new_club = info.get('club', old_club)
                        if old_club != new_club and new_club:
                            changes.append(f"Club: {old_club} → {new_club}")
                        df.at[idx, 'Club'] = new_club
                        
                        old_pais = row.get('País', '')
                        new_pais = info.get('country', 'España')
                        if old_pais != new_pais and new_pais:
                            changes.append(f"País: {old_pais} → {new_pais}")
                        df.at[idx, 'País'] = new_pais
                        
                        # Rebuild Jugador field
                        df.at[idx, 'Jugador'] = f"{apellido1} {apellido2}, {nombre_db}".strip()
                        
                        # Add detailed note with changes
                        if changes:
                            current_notes = str(row.get('Notas_Revision', ''))
                            change_log = f"[FESBA] {'; '.join(changes)}"
                            if current_notes and current_notes != 'nan':
                                df.at[idx, 'Notas_Revision'] = f"{current_notes} | {change_log}"
                            else:
                                df.at[idx, 'Notas_Revision'] = change_log
                        
                        updated_count += 1
            except:
                continue
        
        return df, updated_count
    
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
