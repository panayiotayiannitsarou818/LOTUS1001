# -*- coding: utf-8 -*-
"""
export_step1_4_per_scenario.py  (FIXED, MIN layout)

- Παράγει 1 φύλλο ανά σενάριο του Βήματος 1.
- Κρατά μόνο τις βασικές στήλες + ΒΗΜΑ1, ΒΗΜΑ2, ΒΗΜΑ3, ΒΗΜΑ4.
- Τοποθετεί κάθε νέα στήλη ακριβώς δεξιά από την προηγούμενη.
- Αποφεύγει διπλοεγγραφές στηλών (dedup πριν τη γραφή).

Συνάρτηση:
    build_step1_4_per_scenario(input_excel, output_excel, pick_step4="best")
"""
from typing import Optional, List, Tuple
import importlib.util, sys, re, numpy as np, pandas as pd
from pathlib import Path
from step_2_helpers_FIXED import parse_friends_cell

CORE_COLUMNS = ["ΟΝΟΜΑ","ΦΥΛΟ","ΖΩΗΡΟΣ","ΙΔΙΑΙΤΕΡΟΤΗΤΑ","ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ",
                "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","ΦΙΛΟΙ","ΣΥΓΚΡΟΥΣΗ"]

def _import(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod

def _sid(col: str) -> int:
    m = re.search(r"ΣΕΝΑΡΙΟ[_\s]*(\d+)", str(col))
    return int(m.group(1)) if m else 1

def _dedup(df: pd.DataFrame) -> pd.DataFrame:
    # Drop duplicated column names, keeping the first occurrence
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df

def build_step1_4_per_scenario(input_excel: str, output_excel: str, pick_step4: str = "best") -> None:
    root = Path(__file__).parent
    m_step1 = _import("step1_immutable_ALLINONE", root / "step1_immutable_ALLINONE.py")
    m_step2 = _import("step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED", root / "step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED.py")
    m_h3    = _import("step3_amivaia_filia_FIXED", root / "step3_amivaia_filia_FIXED.py")
    m_step4 = _import("step4_corrected", root / "step4_corrected.py")
    # Monkeypatch wrapper for newer Step 4 signature (adds step1_results arg)
    if hasattr(m_step4, "count_groups_by_category_per_class_strict"):
        _orig = m_step4.count_groups_by_category_per_class_strict
        def _count_wrapper(df, assigned_column, classes, step1_results=None, detected_pairs=None):
            return _orig(df, assigned_column, classes, step1_results, detected_pairs)
        m_step4.count_groups_by_category_per_class_strict = _count_wrapper


    xls = pd.ExcelFile(input_excel)
    df0 = xls.parse(xls.sheet_names[0])

    # STEP 1
    df1, _ = m_step1.create_immutable_step1(df0, num_classes=None)

    # Ensure blank assignments in Step1 are NaN
    for c in [c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")]:
        mask = df1[c].astype(str).str.strip() == ""
        df1.loc[mask, c] = np.nan

    step1_cols = sorted([c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")], key=_sid)

    with pd.ExcelWriter(output_excel, engine="xlsxwriter") as w:
        for s1col in step1_cols:
            sid = _sid(s1col)

            # STEP 2
            options2 = m_step2.step2_apply_FIXED_v3(df1.copy(), step1_col_name=s1col, seed=42, max_results=5)
            if options2:
                df2 = options2[0][1]
                s2col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}"
                if s2col not in df2.columns:
                    cands = [c for c in df2.columns if str(c).startswith("ΒΗΜΑ2_")]
                    s2col = cands[0] if cands else s2col
                    if s2col not in df2.columns:
                        df2[s2col] = ""
            else:
                df2 = df1.copy(); s2col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}"; df2[s2col] = ""

            base = df1.copy()
            base = base.merge(df2[["ΟΝΟΜΑ", s2col]], on="ΟΝΟΜΑ", how="left")
            # Place s2 next to s1
            cols = base.columns.tolist()
            if s2col in cols: cols.remove(s2col)
            idx = cols.index(s1col) + 1 if s1col in cols else len(cols)
            cols = cols[:idx] + [s2col] + cols[idx:]
            base = base[cols]

            # STEP 3
            df3, meta3 = m_h3.apply_step3_on_sheet(base.copy(), scenario_col=s2col, num_classes=None)
            s3col = f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}"
            cands3 = [c for c in df3.columns if str(c).startswith("ΒΗΜΑ3_")]
            if cands3 and s3col not in cands3:
                df3 = df3.rename(columns={cands3[0]: s3col})
            elif s3col not in df3.columns:
                df3[s3col] = ""

            # Place s3 next to s2
            cols3 = df3.columns.tolist()
            if s3col in cols3: cols3.remove(s3col)
            idx2 = cols3.index(s2col) + 1 if s2col in cols3 else len(cols3)
            cols3 = cols3[:idx2] + [s3col] + cols3[idx2:]
            df3 = df3[cols3]

            # Prepare ΦΙΛΟΙ as list for Step 4
            if "ΦΙΛΟΙ" in df3.columns:
                try:
                    df3["ΦΙΛΟΙ"] = df3["ΦΙΛΟΙ"].apply(parse_friends_cell)
                except Exception:
                    pass

            # STEP 4
            res4 = m_step4.apply_step4_with_enhanced_strategy(df3.copy(), assigned_column=s3col, num_classes=None, max_results=5)
            s4final = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"
            if res4:
                df4_mat = m_step4.export_step4_scenarios(df3.copy(), res4, assigned_column=s3col)
                # pick best
                if str(pick_step4).lower() == "best":
                    penalties = [p for (_, p) in res4]
                    best_idx = int(min(range(len(penalties)), key=lambda i: penalties[i]))
                    src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{best_idx+1}"
                else:
                    try:
                        idx_pick = max(1, min(int(pick_step4), len(res4)))
                    except Exception:
                        idx_pick = 1
                    src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{idx_pick}"
                candidates = [c for c in df4_mat.columns if str(c).startswith("ΒΗΜΑ4_")]
                if src in df4_mat.columns:
                    df4 = df4_mat.rename(columns={src: s4final})
                elif candidates:
                    # fall back to first available ΒΗΜΑ4_* column
                    df4 = df4_mat.rename(columns={candidates[0]: s4final})
                else:
                    df4 = df3.copy(); df4[s4final] = ""
            else:
                df4 = df3.copy(); df4[s4final] = ""

            # Place s4 next to s3
            cols4 = df4.columns.tolist()
            if s4final in cols4: cols4.remove(s4final)
            idx3 = cols4.index(s3col) + 1 if s3col in cols4 else len(cols4)
            cols4 = cols4[:idx3] + [s4final] + cols4[idx3:]
            df4 = df4[cols4]

            # Keep MIN columns only + dedup
            keep = [c for c in CORE_COLUMNS if c in df4.columns] + [s1col, s2col, s3col, s4final]
            out_df = _dedup(df4[keep].copy())

            sheet_name = f"ΣΕΝΑΡΙΟ_{sid}"
            out_df.to_excel(w, sheet_name=sheet_name[:31], index=False)
