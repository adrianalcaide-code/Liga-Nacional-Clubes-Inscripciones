# 🏸 Liga Nacional de Clubes - Sistema de Revisión de Inscripciones

Dashboard profesional para la validación de inscripciones de equipos en la Liga Nacional de Clubes de Bádminton (FESBA).

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Firebase](https://img.shields.io/badge/Firebase-FFCA28?style=for-the-badge&logo=firebase&logoColor=black)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

## 🎯 Funcionalidades

- **Validación de Inscripciones**: Verificación automática de jugadores contra la normativa FESBA
- **Auditoría por Equipos**: Control de cumplimiento de ratios (cedidos, género, totales)
- **Gestión de Categorías**: División de Honor, Primera Oro/Plata/Bronce, Segunda Oro
- **Base de Licencias**: Caché de licencias federativas para validación offline
- **Exportación**: Generación de CSVs y Excel con datos procesados

## 🚀 Despliegue en Streamlit Cloud

### 1. Clonar el Repositorio

```bash
git clone https://github.com/adrianalcaide-code/Liga-Nacional-Clubes-Inscripciones.git
cd Liga-Nacional-Clubes-Inscripciones
```

### 2. Configurar Firebase

1. Crear un proyecto en [Firebase Console](https://console.firebase.google.com/)
2. Habilitar Firestore Database
3. Crear una Service Account y descargar las credenciales JSON

### 3. Configurar Secretos en Streamlit Cloud

En Streamlit Cloud → Settings → Secrets, añadir:

```toml
[firebase]
type = "service_account"
project_id = "tu-proyecto-id"
private_key_id = "xxx"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "firebase-adminsdk-xxx@proyecto.iam.gserviceaccount.com"
client_id = "xxx"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
```

### 4. Deploy

Conectar el repositorio en [share.streamlit.io](https://share.streamlit.io) y desplegar.

## 💻 Desarrollo Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Crear archivo de secretos local
mkdir -p .streamlit
# Copiar credenciales Firebase a .streamlit/secrets.toml

# Ejecutar
streamlit run streamlit_app.py
```

## 📁 Estructura del Proyecto

```
├── streamlit_app.py        # Entry point
├── data_processing.py      # Lógica de procesamiento de datos
├── license_validator.py    # Validación de licencias federativas
├── rules_manager.py        # Gestión de reglas y configuración
├── utils.py                # Utilidades comunes
├── modules/
│   ├── firebase_service.py # Conexión Firebase
│   ├── state.py            # Gestión de estado (Firestore)
│   └── settings.py         # Configuración de la app
└── config/
    └── defaults.json       # Valores por defecto
```

## 🔧 Configuración

### Reglas por Categoría

Las reglas de validación (mínimos, máximos, ratios de cedidos) se configuran directamente en la aplicación desde la pestaña "Configuración Avanzada".

### Equivalencias de Clubes (Filiales)

Permite definir qué clubes son filiales para evitar que se marquen como "cedidos".

## 📝 Normativa de Referencia

- Normativa Reguladora Liga Nacional de Clubes 2025-2026
- Convocatoria Oficial LNC

## 📄 Licencia

© 2025 FESBA - Federación Española de Bádminton
