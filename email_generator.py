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
    
    # Check min/max inscription
    if result['total_players'] < min_total:
        result['inscripcion_status'] = 'PENDIENTE'
        result['inscripcion_message'] = f"Salvo error u omisión, no se cumple con la inscripción mínima exigida ({min_total} jugadores). Para subsanar esta cuestión, debéis comunicarnos qué jugador con Homologación Nacional activa, perteneciente a vuestro club, debemos incluir."
    elif result['total_players'] > max_total:
        result['inscripcion_status'] = 'PENDIENTE'
        result['inscripcion_message'] = f"Salvo error u omisión, se excede la inscripción máxima permitida ({max_total} jugadores). Indíquenos qué jugador(es) debemos eliminar de la inscripción."
    
    # Check gender minimums
    if result['total_male'] < min_gender:
        result['inscripcion_status'] = 'PENDIENTE'
        result['inscripcion_message'] += f" Faltan al menos {min_gender - result['total_male']} jugador(es) masculino(s)."
    if result['total_female'] < min_gender:
        result['inscripcion_status'] = 'PENDIENTE'
        result['inscripcion_message'] += f" Faltan al menos {min_gender - result['total_female']} jugadora(s) femenina(s)."
    
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
        names = [f"{r['Nombre']} {r.get('2ºNombre', '')} {r.get('Nombre.1', '')}".strip() for _, r in no_sel.iterrows()]
        result['no_seleccionables_sin_dj'] = names
        result['dj_message'] = f"Salvo error u omisión, no hemos recibido la declaración jurada de: {', '.join(names)}"
    
    # Check Cedidos without Documento Cesión
    ced_sin_doc = team_df[(team_df['Es_Cedido'] == True) & (team_df['Documento_Cesión'] == False)]
    if len(ced_sin_doc) > 0:
        result['cesion_status'] = 'PENDIENTE'
        names = [f"{r['Nombre']} {r.get('2ºNombre', '')} {r.get('Nombre.1', '')}".strip() for _, r in ced_sin_doc.iterrows()]
        result['cedidos_sin_doc'] = names
        result['cesion_message'] = f"Salvo error u omisión, no hemos recibido el documento de cesión de: {', '.join(names)}"
    
    return result


def _generate_status_cell(status, note_num):
    """Generate HTML for status cell (CORRECTO/PENDIENTE)."""
    if status == 'PENDIENTE':
        return f'<td style="border: 1px solid black; padding: 5px;"><b><i><span style="color: red;">PENDIENTE</span></i></b><sup>({note_num})</sup></td>'
    else:
        return f'<td style="border: 1px solid black; padding: 5px;"><b><i>CORRECTO</i></b><sup>({note_num})</sup></td>'


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
    
    # Format Names: Handle None/NaN
    for _, row in team_df.iterrows():
        suffix = _get_player_suffix(row)
        
        # Safe extraction of name parts
        n1 = str(row.get('Nombre', '')) if pd.notna(row.get('Nombre')) else ''
        n2 = str(row.get('2ºNombre', '')) if pd.notna(row.get('2ºNombre')) else ''
        n3 = str(row.get('Nombre.1', '')) if pd.notna(row.get('Nombre.1')) else ''
        
        # Clean up "None" or "nan" strings that might have slipped in
        if n1.lower() == 'none' or n1.lower() == 'nan': n1 = ''
        if n2.lower() == 'none' or n2.lower() == 'nan': n2 = ''
        if n3.lower() == 'none' or n3.lower() == 'nan': n3 = ''
        
        apellido = f"{n1} {n2}".strip()
        if suffix:
            apellido += f" {suffix}"
        
        nombre = n3
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

def generate_team_email(team_name: str, team_df: pd.DataFrame, category: str, rules_config: dict) -> str:
    """
    Generate HTML email content for a single team.
    """
    # Analyze compliance
    compliance = _analyze_team_compliance(team_df, rules_config, category)
    
    # Customize message for specific errors (e.g. Min Gender)
    # logic to insert specific Rinconada-style text if needed
    if "Faltan al menos" in compliance['inscripcion_message']:
        # Construct specific corrective message
        # "Como consecuencia de no cumplir con el requisito mínimo de X jugadoras..."
        # We need to detect if it's male or female missing
        missing_f = "jugadora(s) femenina(s)" in compliance['inscripcion_message']
        missing_m = "jugador(es) masculino(s)" in compliance['inscripcion_message']
        
        req_gender_count = rules_config.get(category, {}).get('min_gender', 5)
        
        if missing_f:
             compliance['inscripcion_message'] += f"<br><br>Salvo error u omisión, la inscripción mínima de jugadoras no se cumple. Como consecuencia de no cumplir con el requisito mínimo de {req_gender_count} jugadoras inscritas, es necesario que añadáis las jugadoras necesarias con licencia deportiva autonómica y habilitación nacional del ID, pertenecientes al club {team_name}, cuya tramitación debe haberse realizado antes del cierre del plazo de inscripción."
        if missing_m:
             compliance['inscripcion_message'] += f"<br><br>Salvo error u omisión, la inscripción mínima de jugadores no se cumple. Como consecuencia de no cumplir con el requisito mínimo de {req_gender_count} jugadores inscritos, es necesario que añadáis los jugadores necesarios con licencia deportiva autonómica y habilitación nacional del ID, pertenecientes al club {team_name}, cuya tramitación debe haberse realizado antes del cierre del plazo de inscripción."
    
    
    # Determine overall status
    has_issues = any([
        compliance['inscripcion_status'] == 'PENDIENTE',
        compliance['dj_status'] == 'PENDIENTE',
        compliance['cesion_status'] == 'PENDIENTE',
        compliance['proporcion_status'] == 'PENDIENTE'
    ])
    overall_status = "PENDIENTE" if has_issues else "ACEPTADA"
    overall_color = "red" if has_issues else "black"
    
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
                <td style="border: 1px solid black; padding: 5px;"><b><i>RECIBIDO</i></b><sup>(2)</sup></td>
            </tr>
            <tr>
                <td colspan="2" style="border: 1px solid black; padding: 5px; font-size: 10pt;"><sup>(2)</sup> Se indica el envío o no del impreso, pero no la correcta afiliación y titulación de las personas propuestas</td>
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
                <td style="border: 1px solid black; padding: 5px;">INSCRIPCIÓN MÍNIMA Y MÁXIMA. Todos los Equipos deberán inscribir un mínimo de 10 jugadores (5 chicos y 5 chicas) y un máximo de 20 jugadores.</td>
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


def generate_all_emails(df: pd.DataFrame, rules_config: dict, team_categories: dict, output_dir: str, category_filter: str = None) -> list:
    """
    Generate .eml files for all teams in the DataFrame.
    
    Args:
        df: Full DataFrame with all players
        rules_config: Rules configuration
        team_categories: Mapping of team names to categories
        output_dir: Directory to save .eml files
        category_filter: Optional category to filter by (if None or "Todas", generate all)
    
    Returns:
        List of generated file paths
    """
    generated_files = []
    
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
        html = generate_team_email(team_name, team_df, category, rules_config)
        
        # Generate .eml file
        filepath = generate_eml_file(team_name, html, output_dir)
        generated_files.append(filepath)
    
    logger.info(f"Generated {len(generated_files)} email files")
    return generated_files
