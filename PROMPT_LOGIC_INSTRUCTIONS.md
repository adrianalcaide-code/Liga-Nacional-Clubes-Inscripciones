# PROMPT LOGIC & ARCHITECTURE DECISIONS

## 2026-01-12 - Enhancing Manual Player Addition
**Input:** User request to improve manual player addition (update existing instead of skip).
**Logic:**
1.  **Lookup Strategy:**
    *   Check if ID exists in `current_df`.
    *   **Case A (Exists):** UPDATE.
        *   Compare new `Equipo` vs old `Pruebas`.
        *   If different -> Update `Pruebas`, Append "Cambio manual equipo: OLD -> NEW" to `Notas_Revision`.
        *   Do NOT overwrite other fields (Nombre, Género) unless they are empty/null.
    *   **Case B (New):** INSERT.
        *   Fetch details from `LicenseValidator`.
        *   Create new row.
        *   Set `Notas_Revision` = "Añadido Manualmente".
2.  **Shadow Prompt:** `Refactor manual_add loop. Use df.loc[mask] to finding existing index. Update in place. Append new rows to list. Concat at end.`
