"""
Email Generator Module
Generates HTML emails for each club with compliance status and player lists.
"""
import os
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging

logger = logging.getLogger(__name__)

# ==================== CONSTANTS ====================
FESBA_SIGNATURE = """
<p style="font-family: Cambria, serif; font-size: 12pt; color: #222;">
<b>Inscripciones</b><br>
Federación Española de Bádminton<br>
Spanish Badminton Federation<br>
C/ Ferraz 16, 5ºizqda. 28008 Madrid<br>
Tfn.: 91 542 83 84<br>
<a href="mailto:inscripciones@badminton.es">inscripciones@badminton.es</a><br>
<a href="http://www.badminton.es">www.badminton.es</a>
</p>
"""

# ==================== HELPER FUNCTIONS ====================

def _get_player_suffix(row):
    """Generate suffix codes for player based on status."""
    suffixes = []
    
    # (C) = Cedido
    if row.get('Es_Cedido', False):
        suffixes.append("(C)")
    
    # (HN-p) = Homologación Nacional pendiente (license not valid)
    validacion = str(row.get('Validacion_FESBA', ''))
    if '❌' in validacion or 'NO ENCONTRADO' in validacion.upper() or 'CANCELADA' in validacion.upper():
        suffixes.append("(HN-p)")
    
    # (DJ-p) = Declaración Jurada pendiente (for No_Seleccionable without DJ)
    if row.get('No_Seleccionable', False) and not row.get('Declaración_Jurada', False):
        suffixes.append("(DJ-p)")
    
    # (DC-p) = Documento Cesión pendiente (for Cedidos without doc)
    if row.get('Es_Cedido', False) and not row.get('Documento_Cesión', False):
        suffixes.append("(DC-p)")
    
    return " ".join(suffixes)


def _analyze_team_compliance(team_df, rules_config, category):
    """Analyze team compliance and return status dict."""
    result = {
        'total_players': len(team_df),
        'total_male': len(team_df[team_df['Género'].str.upper().isin(['M', 'MASCULINO'])]),
        'total_female': len(team_df[team_df['Género'].str.upper().isin(['F', 'FEMENINO'])]),
        'cedidos': team_df[team_df['Es_Cedido'] == True],
        'cedidos_count': len(team_df[team_df['Es_Cedido'] == True]),
        'no_seleccionables_sin_dj': [],
        'cedidos_sin_doc': [],
        'inscripcion_status': 'CORRECTO',
        'inscripcion_message': '',
        'dj_status': 'CORRECTO',
        'dj_message': '',
        'cesion_status': 'CORRECTO',
        'cesion_message': '',
        'proporcion_status': 'CORRECTO',
        'proporcion_message': '',
        'cedidos_a_eliminar': 0
    }
    
    # Get rules for category
    rules = rules_config.get(category, {})
    min_total = rules.get('min_total', 10)
    max_total = rules.get('max_total', 20)
    min_gender = rules.get('min_gender', 5)
    ratio_table = rules.get('ratio_table', [])
    
    # --- LOGIC SEQUENCE: GENDER FIRST, THEN TOTAL ---
    
    # 1. Check gender minimums
    gender_missing = False
    missing_m = result['total_male'] < min_gender
    missing_f = result['total_female'] < min_gender
    
    if missing_m and missing_f:
        gender_missing = True
        result['inscripcion_status'] = 'PENDIENTE'
        # Unified text for BOTH
        result['inscripcion_message'] = f"Salvo error u omisión, no se cumple con la inscripción mínima exigida de jugadores y jugadoras ({min_gender} chicos y {min_gender} chicas). Para subsanar esta situación, os rogamos que nos indiquéis qué deportistas con Homologación Nacional activa antes del cierre del plazo de inscripción, pertenecientes a vuestro club, deben ser incluidos."
    
    elif missing_m:
        gender_missing = True
        result['inscripcion_status'] = 'PENDIENTE'
        # Specific MALE text
        diff = min_gender - result['total_male']
        noun = "jugador" if diff == 1 else "jugadores"
        result['inscripcion_message'] = f"Salvo error u omisión, la inscripción mínima de jugadores no se cumple. Como consecuencia de no cumplir con el requisito mínimo de {min_gender} jugadores inscritos, es necesario que añadáis {diff} {noun} con licencia deportiva autonómica y habilitación nacional del ID, pertenecientes al club {team_df.iloc[0]['Pruebas'] if not team_df.empty else 'vuestro club'}, cuya tramitación debe haberse realizado antes del cierre del plazo de inscripción."
        
    elif missing_f:
        gender_missing = True
        result['inscripcion_status'] = 'PENDIENTE'
        # Specific FEMALE text
        diff = min_gender - result['total_female']
        noun = "jugadora" if diff == 1 else "jugadoras"
        result['inscripcion_message'] = f"Salvo error u omisión, la inscripción mínima de jugadoras no se cumple. Como consecuencia de no cumplir con el requisito mínimo de {min_gender} jugadoras inscritas, es necesario que añadáis {diff} {noun} con licencia deportiva autonómica y habilitación nacional del ID, pertenecientes al club {team_df.iloc[0]['Pruebas'] if not team_df.empty else 'vuestro club'}, cuya tramitación debe haberse realizado antes del cierre del plazo de inscripción."

    # 2. Check min/max inscription (ONLY if gender min is met)
    if result['total_players'] < min_total and not gender_missing:
        # Only show generic min error if no gender specific error occurred
        result['inscripcion_status'] = 'PENDIENTE'
        result['inscripcion_message'] = f"Salvo error u omisión, no se cumple con la inscripción mínima exigida ({min_total} jugadores). Para subsanar esta cuestión, debéis comunicarnos qué jugador con Homologación Nacional activa, perteneciente a vuestro club, debemos incluir."
        
    elif result['total_players'] > max_total:
        # Max limit is independent of gender minimums usually
        result['inscripcion_status'] = 'PENDIENTE'
        if result['inscripcion_message']: result['inscripcion_message'] += "<br>"
        result['inscripcion_message'] += f"Salvo error u omisión, se excede la inscripción máxima permitida ({max_total} jugadores). Indíquenos qué jugador(es) debemos eliminar de la inscripción."
    
    
    # Check cedidos proportion
    if ratio_table and result['total_players'] > 0:
        for ratio in ratio_table:
            if result['total_players'] == ratio['total']:
                max_cedidos = ratio['max_cedidos']
                if result['cedidos_count'] > max_cedidos:
                    result['proporcion_status'] = 'PENDIENTE'
                    result['cedidos_a_eliminar'] = result['cedidos_count'] - max_cedidos
                    result['proporcion_message'] = f"Se excede la proporción máxima de cedidos ({max_cedidos} para {result['total_players']} jugadores). Deben eliminarse {result['cedidos_a_eliminar']} cedido(s). Indíquenos cuál(es)."
                break
    
    # Check No Seleccionables without Declaración Jurada
    no_sel = team_df[(team_df['No_Seleccionable'] == True) & (team_df['Declaración_Jurada'] == False)]
    if len(no_sel) > 0:
        result['dj_status'] = 'PENDIENTE'
        names = [_format_name(r) for _, r in no_sel.iterrows()]
        result['no_seleccionables_sin_dj'] = names
        result['dj_message'] = f"Salvo error u omisión, no hemos recibido la declaración jurada de: {', '.join(names)}"
    
    # Check Cedidos without Documento Cesión
    ced_sin_doc = team_df[(team_df['Es_Cedido'] == True) & (team_df['Documento_Cesión'] == False)]
    if len(ced_sin_doc) > 0:
        result['cesion_status'] = 'PENDIENTE'
        names = [_format_name(r) for _, r in ced_sin_doc.iterrows()]
        result['cedidos_sin_doc'] = names
        result['cesion_message'] = f"Salvo error u omisión, no hemos recibido el documento de cesión de: {', '.join(names)}"
    
    return result


def _format_name(row):
    """Safely format full name from row data, ignoring None/NaN."""
    parts = []
    # 1. First Name (Nombre.1) - Wait, usually 'Nombre' is surname?
    # Based on input structure:
    # 'Nombre' = Surname 1
    # '2ºNombre' = Surname 2
    # 'Nombre.1' = First Name
    
    # Actually, let's look at table headers: "Apellido", "Nombre".
    # In table generation:
    # apellido = n1 + n2
    # nombre = n3
    # So we probably want "Surname1 Surname2 Name" or "Name Surname1 Surname2"?
    # The user example "Prykhodko None Polina" suggests "Surname1 Surname2 Name".
    
    components = [
        str(row.get('Nombre', '')),    # Surname 1
        str(row.get('2ºNombre', '')),  # Surname 2
        str(row.get('Nombre.1', ''))   # Name
    ]
    
    clean_parts = []
    for c in components:
        if pd.isna(c) or c.lower() in ['nan', 'none', '']:
            continue
        clean_parts.append(c.strip())
        
    return " ".join(clean_parts)


def _generate_status_cell(status, note_num):
    """Generate HTML for status cell (CORRECTO/PENDIENTE)."""
    if status == 'PENDIENTE':
        return f'<td style="border: 1px solid black; padding: 5px;"><b><i><span style="color: red;">PENDIENTE</span></i></b><sup>({note_num})</sup></td>'
    else:
        return f'<td style="border: 1px solid black; padding: 5px;"><b><i>CORRECTO</i></b></td>'


def _generate_player_table(team_df):
    """Generate HTML table of players with nomenclature."""
    html = """
    <table style="border-collapse: collapse; width: 100%; font-family: Cambria, serif; font-size: 12pt;">
    <tr style="background: #f0f0f0;">
        <th style="border: 1px solid black; padding: 5px;">Apellido</th>
        <th style="border: 1px solid black; padding: 5px;">Nombre</th>
        <th style="border: 1px solid black; padding: 5px;">País</th>
        <th style="border: 1px solid black; padding: 5px;">F. Nac</th>
        <th style="border: 1px solid black; padding: 5px;">Género</th>
        <th style="border: 1px solid black; padding: 5px;">NºID</th>
        <th style="border: 1px solid black; padding: 5px;">Equipo</th>
    </tr>
    """
    
    # Sort by Gender and Surname (safe sort)
    try:
        # Create a copy to avoid SettingWithCopy warnings if team_df is a slice
        team_df = team_df.copy()
        # Ensure strings for sorting
        team_df['Género'] = team_df['Género'].fillna('').astype(str)
        team_df['Nombre'] = team_df['Nombre'].fillna('').astype(str)
        # Sort: Gender (F < M ideally), then Name
        team_df = team_df.sort_values(by=['Género', 'Nombre'])
    except Exception as e:
        # Fallback if sort fails (e.g. missing columns), just continue
        pass

    # Format Names: Handle None/NaN
    for _, row in team_df.iterrows():
        suffix = _get_player_suffix(row)
        
        # Safe extraction for specific columns
        def clean(val):
            s = str(val)
            if pd.isna(val) or s.lower() in ['nan', 'none', '']:
                return ""
            return s.strip()

        # Build Surnames
        n1 = clean(row.get('Nombre', '')) 
        n2 = clean(row.get('2ºNombre', ''))
        apellido = f"{n1} {n2}".strip()
        
        if suffix:
            apellido += f" {suffix}"
        
        # Build Name
        nombre = clean(row.get('Nombre.1', ''))
        
        pais = row.get('País', 'Spain')
        
        # Format Date
        fnac_raw = str(row.get('F.Nac', ''))
        fnac = ""
        if fnac_raw and fnac_raw.lower() != 'nat' and fnac_raw != 'nan':
            try:
                # Try parsing ISO/Timestamp
                if "T" in fnac_raw:
                    dt = datetime.fromisoformat(fnac_raw.replace('Z', ''))
                    fnac = dt.strftime("%d/%m/%Y")
                else:
                    # Maybe it's already a date object or other string
                    dt = pd.to_datetime(fnac_raw)
                    fnac = dt.strftime("%d/%m/%Y")
            except:
                # Fallback
                fnac = fnac_raw[:10]
        
        genero = row.get('Género', '')
        nid = row.get('Nº.ID', '')
        equipo = row.get('Pruebas', '') # Equipo column
        
        html += f"""
        <tr>
            <td style="border: 1px solid black; padding: 5px;">{apellido}</td>
            <td style="border: 1px solid black; padding: 5px;">{nombre}</td>
            <td style="border: 1px solid black; padding: 5px;">{pais}</td>
            <td style="border: 1px solid black; padding: 5px;">{fnac}</td>
            <td style="border: 1px solid black; padding: 5px;">{genero}</td>
            <td style="border: 1px solid black; padding: 5px;">{nid}</td>
            <td style="border: 1px solid black; padding: 5px;">{equipo}</td>
        </tr>
        """
    
    html += "</table>"
    return html


# ==================== MAIN FUNCTIONS ====================

def generate_team_email(team_name: str, team_df: pd.DataFrame, category: str, rules_config: dict, tech_status_map: dict = None) -> str:
    """
    Generate HTML email content for a single team.
    """
    # Analyze compliance
    compliance = _analyze_team_compliance(team_df, rules_config, category)
    
    # Determine overall status
    # Check Tech Status also
    tech_status_map = tech_status_map or {}
    is_tech_delivered = tech_status_map.get(team_name, False)
    
    has_issues = any([
        compliance['inscripcion_status'] == 'PENDIENTE',
        compliance['dj_status'] == 'PENDIENTE',
        compliance['cesion_status'] == 'PENDIENTE',
        compliance['proporcion_status'] == 'PENDIENTE',
        not is_tech_delivered # Tech status logic
    ])
    overall_status = "PENDIENTE" if has_issues else "ACEPTADA"
    overall_color = "red" if has_issues else "black"
    
    # HTML components for Tech Status
    if is_tech_delivered:
        tech_cell = '<td style="border: 1px solid black; padding: 5px;"><b><i>RECIBIDO</i></b><sup>(2)</sup></td>'
        tech_msg = "Comentario no necesario"
    else:
        tech_cell = '<td style="border: 1px solid black; padding: 5px;"><b><i><span style="color: red;">PENDIENTE</span></i></b><sup>(2)</sup></td>'
        tech_msg = "Salvo error u omisión, no hemos recibido el impreso de relación de técnicos y delegados."

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Cambria, serif; font-size: 14pt; color: #222; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid black; padding: 8px; text-align: left; }}
            .header {{ font-size: 16pt; font-weight: bold; }}
            .section {{ margin: 20px 0; }}
            .pending {{ color: red; font-weight: bold; }}
            .correct {{ color: black; font-weight: bold; }}
            sup {{ font-size: 10pt; }}
        </style>
    </head>
    <body>
        <p class="header">{team_name.upper()}</p>
        <p class="header">Equipo {category}</p>
        
        <p>Estimado/a amigo/a, sirva la presente comunicación para adjuntarte, salvo error u omisión por nuestra parte, el estado actual de la inscripción de tu club, a la Liga Nacional de Clubes Edición 2025-2026.</p>
        
        <p>De acuerdo a la información recogida en este informe, y si por parte de FESBA se consignara algún tipo de incidencia, deberá subsanarse en el plazo máximo de <b>2 días naturales</b> a contar a partir del envío de la presente comunicación, (salvo que expresamente se indique otro plazo distinto en el presente comunicado).</p>
        
        <p>Las subsanaciones se circunscriben, de producirse, única y exclusivamente a los aspectos que se indiquen por parte de FESBA en el presente informe.</p>
        
        <p>Lo que traslado para tu conocimiento a los efectos oportunos.</p>
        
        <p>Atentamente, recibe un cordial saludo</p>
        
        <div class="section">
        <table>
            <tr style="background: #e0e0e0;">
                <td colspan="2" style="border: 1px solid black; padding: 10px;"><b>5.2. SEGUNDA FASE DE INSCRIPCIÓN: de los JUGADORES</b></td>
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px;"><b>i) Documentación y procedimiento:</b> La documentación necesaria para la inscripción de los jugadores en la Liga Nacional de Clubes será la siguiente:</td>
            </tr>
            
            <!-- a) Inscripción online -->
            <tr>
                <td style="border: 1px solid black; padding: 5px;">a) Inscripción de los deportistas a través de la plataforma de inscripciones online.</td>
                <td style="border: 1px solid black; padding: 5px;"><b><i>CORRECTO</i></b><sup>(1)</sup></td>
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(1)</sup> Comentario no necesario</td>
            </tr>
            
            <!-- b) Técnicos y delegados -->
            <tr>
                <td style="border: 1px solid black; padding: 5px;">b) Impreso de relación de técnicos y delegados cumplimentado en todos sus apartados según ANEXO II.</td>
                {tech_cell}
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(2)</sup> {tech_msg}</td>
            </tr>
            
            <!-- c) No seleccionables / Declaración Jurada -->
            <tr>
                <td style="border: 1px solid black; padding: 5px;">c) En el caso de inscribir a jugadores que no sean seleccionables, deberán incluir la documentación que expresamente se solicite en la Normativa Reguladora de esta competición.</td>
                {_generate_status_cell(compliance['dj_status'], 3)}
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(3)</sup> {compliance['dj_message'] if compliance['dj_message'] else 'Comentario no necesario'}</td>
            </tr>
            
            <!-- d) Documento Cesión -->
            <tr>
                <td style="border: 1px solid black; padding: 5px;">d) En el caso de inscribir a jugadores cedidos, el club de origen debe inscribir al deportista en tiempo y forma en la plataforma de inscripciones online en el apartado del club de destino. Además, el equipo de destino deberá remitir el documento-acuerdo oficialmente establecido por FESBA.</td>
                {_generate_status_cell(compliance['cesion_status'], 4)}
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(4)</sup> {compliance['cesion_message'] if compliance['cesion_message'] else 'Comentario no necesario'}</td>
            </tr>
            
            <!-- Inscripción mínima/máxima -->
            <tr>
                <td style="border: 1px solid black; padding: 5px;">INSCRIPCIÓN MÍNIMA Y MÁXIMA. Todos los Equipos deberán inscribir un mínimo de 10 jugadores (5 chicos y 5 chicas) y un máximo de 20 jugadores (10 chicos y 10 chicas) entre los dos plazos. En el caso de cubrir el máximo de jugadores inscritos en el primer plazo, quedará anulada la posibilidad de ampliar el número de inscritos en el segundo plazo.</td>
                {_generate_status_cell(compliance['inscripcion_status'], 5)}
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(5)</sup> {compliance['inscripcion_message'] if compliance['inscripcion_message'] else ''} {compliance['proporcion_message']}</td>
            </tr>
            
            <!-- Estado actual -->
            <tr>
                <td style="border: 1px solid black; padding: 10px;"><b>Estado actual de su inscripción</b></td>
                <td style="border: 1px solid black; padding: 10px;"><b><i><span style="color: {overall_color};">{overall_status}</span></i></b><sup>(6)</sup></td>
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(6)</sup> El estado actual de su inscripción puede variar, estando supeditada al cumplimiento de todos los criterios.</td>
            </tr>
        </table>
        </div>
        
        <div class="section">
        <p><i>Nótense los siguientes códigos:</i></p>
        <p><i>(C): Deportista cedido</i></p>
        <p><i>(HN-p): Pendiente homologación nacional del ID.</i></p>
        <p><i>(DJ-p): Pendiente Declaración Jurada.</i></p>
        <p><i>(DC-p): Pendiente Documento de Cesión.</i></p>
        </div>
        
        <div class="section">
        {_generate_player_table(team_df)}
        </div>
        
        {FESBA_SIGNATURE}
    </body>
    </html>
    """
    
    return html


def generate_eml_file(team_name: str, html_content: str, output_dir: str, team_email: str = "") -> str:
    """
    Generate .eml file for a team.
    
    Args:
        team_name: Name of the team
        html_content: HTML email body
        output_dir: Directory to save .eml files
        team_email: Optional recipient email
    
    Returns:
        Path to generated .eml file
    """
    # Create MIME message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"{team_name} | Liga Nacional de Clubes - Estado de Inscripción"
    msg['From'] = "inscripciones@badminton.es"
    msg['To'] = team_email if team_email else "destinatario@club.com"
    msg['Cc'] = "eventos@badminton.es"
    msg['Date'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0100")
    
    # Attach HTML content
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)
    
    # Save to file
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Clean filename
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in team_name)
    filename = os.path.join(output_dir, f"{safe_name}.eml")
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(msg.as_string())
    
    logger.info(f"Generated email: {filename}")
    return filename


def load_contacts_from_csv(csv_path: str) -> dict:
    """
    Load team emails from a CSV file.
    Expected format: Team Name, Email1; Email2...
    No header expected, but robust to it.
    """
    contacts = {}
    if not os.path.exists(csv_path):
        logger.warning(f"Contacts file not found: {csv_path}")
        return contacts
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                parts = line.split(',')
                if len(parts) >= 2:
                    team = parts[0].strip()
                    emails = parts[1].strip()
                    contacts[team] = emails
                    
        logger.info(f"Loaded {len(contacts)} team contacts")
    except Exception as e:
        logger.error(f"Error loading contacts: {e}")
        
    return contacts


def save_contacts_to_csv(contacts_map: dict, csv_path: str) -> bool:
    """Save contacts dictionary to CSV."""
    try:
        # Sort by team name
        sorted_items = sorted(contacts_map.items())
        
        with open(csv_path, 'w', encoding='utf-8') as f:
            for team, emails in sorted_items:
                f.write(f"{team},{emails}\n")
        logger.info("Contacts saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving contacts: {e}")
        return False


def generate_all_emails(df: pd.DataFrame, rules_config: dict, team_categories: dict, output_dir: str, category_filter: str = None, contacts_map: dict = None, tech_status_map: dict = None) -> list:
    """
    Generate .eml files for all teams in the DataFrame.
    
    Args:
        df: Full DataFrame with all players
        rules_config: Rules configuration
        team_categories: Mapping of team names to categories
        output_dir: Directory to save .eml files
        category_filter: Optional category to filter by (if None or "Todas", generate all)
        contacts_map: Dictionary mapping 'Team Name' -> 'email@address.com'
        tech_status_map: Dictionary mapping 'Team Name' -> bool (delivered status)
    
    Returns:
        List of generated file paths
    """
    generated_files = []
    contacts_map = contacts_map or {}
    tech_status_map = tech_status_map or {}
    
    # Group by team (Pruebas column)
    teams = df.groupby('Pruebas')
    
    for team_name, team_df in teams:
        if not team_name or team_name == 'Sin Asignar':
            continue
        
        # Get category for team
        category = team_categories.get(team_name, "Sin Asignar")
        
        # Apply filter
        if category_filter and category_filter != "Todas" and category != category_filter:
            continue
        
        # Generate HTML
        html = generate_team_email(team_name, team_df, category, rules_config, tech_status_map=tech_status_map)
        
        # Get Email Address
        email_addr = contacts_map.get(team_name, "")
        
        # Generate .eml file
        filepath = generate_eml_file(team_name, html, output_dir, team_email=email_addr)
        generated_files.append(filepath)
    
    logger.info(f"Generated {len(generated_files)} email files")
    return generated_files
