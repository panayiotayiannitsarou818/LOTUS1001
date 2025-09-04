
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Export: ONE sheet per scenario with columns:
A–H:  Α/Α, ΟΝΟΜΑ, ΦΥΛΟ, ΖΩΗΡΟΣ, ΙΔΙΑΙΤΕΡΟΤΗΤΑ, ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ, ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ, ΦΙΛΟΙ
I:    ΒΗΜΑ1_ΣΕΝΑΡΙΟ_N
J:    ΒΗΜΑ2_ΣΕΝΑΡΙΟ_N
K:    ΒΗΜΑ3_ΣΕΝΑΡΙΟ_N
L:    ΒΗΜΑ4_ΣΕΝΑΡΙΟ_N (best or picked index)
"""

import re
import sys
import numpy as np
import pandas as pd
import importlib.util
from pathlib import Path
from typing import List, Tuple, Optional

# ---------- Helpers for dynamic imports ----------
def _import_by_path(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod

# ---------- Core builder ----------
def build_step1_4_per_scenario(
    input_excel: str,
    output_excel: str,
    pick_step4: str = "best",   # "best" or explicit index "1","2","3","4","5"
    max_step2: int = 5,
    max_step4: int = 5,
    sheet_name: Optional[str] = None
) -> None:
    base_path = Path(input_excel)
    assert base_path.exists(), f"Δεν βρέθηκε το αρχείο εισόδου: {input_excel}"

    # Import required modules (paths assume they are alongside or already provided)
    root = Path(__file__).parent if "__file__" in globals() else Path(".")
    m_step1 = _import_by_path("step1_immutable_ALLINONE", root / "step1_immutable_ALLINONE.py")
    m_h2    = _import_by_path("step_2_helpers_FIXED",     root / "step_2_helpers_FIXED.py")
    m_step2 = _import_by_path("step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED", root / "step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED.py")
    m_h3    = _import_by_path("step3_amivaia_filia_FIXED", root / "step3_amivaia_filia_FIXED.py")
    m_step4 = _import_by_path("step4_corrected",          root / "step4_corrected.py")

    # Monkeypatch Step 4 strict counter missing default for step1_results
    if hasattr(m_step4, "count_groups_by_category_per_class_strict"):
        _orig = m_step4.count_groups_by_category_per_class_strict
        def _count_wrapper(df, assigned_column, classes, step1_results=None, detected_pairs=None):
            return _orig(df, assigned_column, classes, step1_results, detected_pairs)
        m_step4.count_groups_by_category_per_class_strict = _count_wrapper

    step2_apply_FIXED_v3 = getattr(m_step2, "step2_apply_FIXED_v3")
    apply_step3_on_sheet = getattr(m_h3, "apply_step3_on_sheet")
    apply_step4          = getattr(m_step4, "apply_step4_with_enhanced_strategy")
    export_step4         = getattr(m_step4, "export_step4_scenarios")

    # Load dataset (first sheet unless specified)
    xls = pd.ExcelFile(base_path)
    target_sheet = sheet_name or xls.sheet_names[0]
    df0 = xls.parse(target_sheet)

    # Run Step 1 to get ΒΗΜΑ1_ΣΕΝΑΡΙΟ_* columns
    df1, _res1 = m_step1.create_immutable_step1(df0, num_classes=None)

    # Treat empty strings in step1 assignments as NaN (unplaced)
    s1_cols = [c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")]
    for c in s1_cols:
        mask = df1[c].astype(str).str.strip() == ""
        df1.loc[mask, c] = np.nan

    # Ensure base columns exist
    BASE = ["Α/Α","ΟΝΟΜΑ","ΦΥΛΟ","ΖΩΗΡΟΣ","ΙΔΙΑΙΤΕΡΟΤΗΤΑ","ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ","ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","ΦΙΛΟΙ"]
    def _ensure_base(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for col in BASE:
            if col not in out.columns:
                if col == "Α/Α":
                    out[col] = range(1, len(out)+1)
                else:
                    out[col] = ""
        return out

    df1 = _ensure_base(df1)

    # Scenario columns sorted by index N
    def _idx(col: str) -> int:
        m = re.search(r"ΣΕΝΑΡΙΟ[_\s]*(\d+)", str(col))
        return int(m.group(1)) if m else 9999
    step1_cols: List[str] = sorted([c for c in s1_cols], key=_idx)

    # Prepare writer
    out_path = Path(output_excel)
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        for s1col in step1_cols:
            N = _idx(s1col)
            # ---------- STEP 2 ----------
            scenarios2: List[Tuple[str, pd.DataFrame, dict]] = step2_apply_FIXED_v3(df1.copy(), step1_col_name=s1col, max_results=max_step2)
            if scenarios2:
                # try to pick scenario matching N; else first
                chosen_name, chosen_df2, metrics2 = None, None, None
                for (nm, df2, met) in scenarios2:
                    if re.search(rf"ΣΕΝΑΡΙΟ[_\s]*{N}\b", str(nm)): chosen_name, chosen_df2, metrics2 = nm, df2, met; break
                if chosen_df2 is None:
                    chosen_name, chosen_df2, metrics2 = scenarios2[0]
                # find/add ΒΗΜΑ2_ΣΕΝΑΡΙΟ_N
                step2_cols = [c for c in chosen_df2.columns if str(c).startswith("ΒΗΜΑ2_")]
                if step2_cols:
                    s2col = step2_cols[0]
                else:
                    s2col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{N}"; chosen_df2 = chosen_df2.copy(); chosen_df2[s2col] = ""
            else:
                chosen_df2 = df1.copy()
                s2col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{N}"; chosen_df2[s2col] = ""

            # ---------- Merge Step1 + Step2 into base ----------
            base = df1[BASE + [s1col]].copy()
            base = base.merge(chosen_df2[["ΟΝΟΜΑ", s2col]], on="ΟΝΟΜΑ", how="left")
            # ---------- STEP 3 ----------
            df3, meta3 = apply_step3_on_sheet(base.copy(), scenario_col=s2col, num_classes=None)
            s3col = f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{N}"
            # ensure we have the desired s3col name
            cands3 = [c for c in df3.columns if str(c).startswith("ΒΗΜΑ3_")]
            if cands3 and s3col not in cands3:
                df3 = df3.rename(columns={cands3[0]: s3col})
            elif s3col not in df3.columns:
                df3[s3col] = np.nan

            # Prepare ΦΙΛΟΙ as list for Step 4
            if "ΦΙΛΟΙ" in df3.columns and hasattr(m_h2, "parse_friends_cell"):
                df3["ΦΙΛΟΙ"] = df3["ΦΙΛΟΙ"].apply(m_h2.parse_friends_cell)

            # ---------- STEP 4 ----------
            res4 = apply_step4(df3.copy(), assigned_column=s3col, num_classes=None, max_results=max_step4)
            step4_final_col = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{N}"
            if res4:
                # Materialize many ΒΗΜΑ4_* columns
                df4_mat = export_step4(df3.copy(), res4, assigned_column=s3col)
                # Decide which to keep
                if str(pick_step4).lower() == "best":
                    penalties = [p for (_, p) in res4]
                    idx_min = int(min(range(len(penalties)), key=lambda i: penalties[i]))
                    src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{idx_min+1}"
                else:
                    # explicit index (1-based)
                    try:
                        idx_pick = max(1, min(int(pick_step4), len(res4)))
                    except Exception:
                        idx_pick = 1
                    src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{idx_pick}"
                # fallback if src not found
                if src not in df4_mat.columns:
                    cands = [c for c in df4_mat.columns if c.startswith("ΒΗΜΑ4_")]
                    src = cands[0] if cands else None
                if src is not None:
                    df4 = df4_mat.rename(columns={src: step4_final_col})
                else:
                    df4 = df3.copy(); df4[step4_final_col] = ""
            else:
                df4 = df3.copy(); df4[step4_final_col] = ""

            # ---------- ORDER & EXPORT ----------
            ordered = BASE + [f"ΒΗΜΑ1_ΣΕΝΑΡΙΟ_{N}", f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{N}", f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{N}", step4_final_col]
            for c in ordered:
                if c not in df4.columns: df4[c] = np.nan
            out_df = df4[ordered].copy()

            sheet_title = f"ΣΕΝΑΡΙΟ_{N}"
            out_df.to_excel(writer, sheet_name=sheet_title, index=False)
            ws = writer.sheets[sheet_title]
            for idx, _c in enumerate(out_df.columns):
                ws.set_column(idx, idx, 22)

    print(f"✅ Αρχείο δημιουργήθηκε: {out_path}")

# ---------- CLI ----------
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Χρήση: python export_step1_4_per_scenario.py <input_excel> <output_excel> [best|1|2|3|4|5]")
        sys.exit(1)
    input_excel = sys.argv[1]
    output_excel = sys.argv[2]
    pick = sys.argv[3] if len(sys.argv) >= 4 else "best"
    build_step1_4_per_scenario(input_excel, output_excel, pick_step4=pick)
