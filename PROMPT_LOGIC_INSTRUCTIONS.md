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

## 2026-01-12 - UI UX Cleanup
**Input:** Auto-clear manual input table after processing.
**Logic:**
1.  **Issue:** `st.data_editor` persists state in its key (`manual_editor`) even if source DF changes in session state.
2.  **Fix:** Explicitly `del st.session_state['manual_editor']` on success.

## 2026-01-12 - Debugging Missing ID 1010157
**Input:** User reports specific ID not found in FESBA DB.
**Hypothesis:**
1.  **Type Mismatch:** `licenses_db` keys might be strings, but lookup ID is int (or vice versa).
2.  **Stale Cache:** The local/cloud cache doesn't have this player yet.
3.  **Incomplete Download:** The Selenium download didn't get this member (e.g., deleted member?).
**Logic:**
1.  Create `debug_lookup.py` to load cache and inspect keys.
2.  Check for presence of `1010157` as `int` and `str`.

## 2026-01-12 - Editable Dashboard Columns
**Input:** User wants to choose which columns are visible in the dashboard.
**Logic:**
1.  **State:** Store `selected_columns` in `st.session_state`.
2.  **Default:** If empty, use the standard default list (`['_Estado_Fila', 'Nº.ID', ...]`).
3.  **UI:** Add `st.multiselect` in a settings expander or top bar.
4.  **Action:** Filter `cols_to_show` based on selection before rendering `data_editor`.

## 2026-01-12 - Dashboard Responsiveness & Auto-Recalc
**Input:** User reports missed inputs and lack of fluidity.
**Logic:**
1.  **Bug:** `editable_cols` missing 'Pruebas', 'Género', 'País'.
2.  **UX Issue:** Checking "Declaración Jurada" auto-saves but doesn't remove the "⚠️ Falta..." warning requiring a manual button press. This feels like "not working".
3.  **Fix:**
    *   Add columns to `editable_cols`.
    *   Trigger `process_dataframe` + `apply_comprehensive_check` on EVERY auto-save.
    *   Remove explicit "Actualizar Estado" button (or keep as force refresh) since it's now automatic.
