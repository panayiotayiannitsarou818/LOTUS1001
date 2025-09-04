# Exporter (copy–paste)

Αντέγραψε **ολόκληρο** το παρακάτω και σώσε το ως:
`export_step1_4_per_scenario.py` (στον ίδιο φάκελο με το app).

---

```python
# -*- coding: utf-8 -*-
"""
export_step1_4_per_scenario.py — MIN exporter (1→4 + ενσωματωμένο 5)

Εκθέτει ΣΙΓΟΥΡΑ τη συνάρτηση που ζητά ο wrapper:
    build_step1_4_per_scenario(input_excel, output_excel, pick_step4="best")
και alias για συμβατότητα:
    build_step1_5_per_scenario = build_step1_4_per_scenario

Τι κάνει:
- Παίρνει STEP1 Excel
- Τρέχει Βήματα 1→4 και εφαρμόζει Step 5 ώστε το output να είναι έτοιμο για Step 6
- Βγάζει MIN μορφή: βασικές στήλες + ΒΗΜΑ1..ΒΗΜΑ5, 1 φύλλο ανά σενάριο
- Αποφεύγει διπλές στήλες (dedup)
"""

from typing import Optional, List, Tuple
import importlib.util, sys, re, numpy as np, pandas as pd
from pathlib import Path

CORE_COLUMNS = [
    "ΟΝΟΜΑ","ΦΥΛΟ","ΖΩΗΡΟΣ","ΙΔΙΑΙΤΕΡΟΤΗΤΑ","ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ",
    "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","ΦΙΛΟΙ","ΣΥΓΚΡΟΥΣΗ"
]

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
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df

def build_step1_4_per_scenario(input_excel: str, output_excel: str, pick_step4: str = "best") -> None:
    root = Path(__file__).parent
    m_step1 = _import("step1_immutable_ALLINONE", root / "step1_immutable_ALLINONE.py")
    m_help2 = _import("step_2_helpers_FIXED", root / "step_2_helpers_FIXED.py")
    m_step2 = _import("step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED", root / "step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED.py")
    m_h3    = _import("step3_amivaia_filia_FIXED", root / "step3_amivaia_filia_FIXED.py")
    m_step4 = _import("step4_corrected", root / "step4_corrected.py")
    m_step5 = _import("step5_enhanced", root / "step5_enhanced.py")

    # Συμβατότητα υπογραφής στο Step4 (αν η υλοποίηση δέχεται extra args)
    if hasattr(m_step4, "count_groups_by_category_per_class_strict"):
        _orig = m_step4.count_groups_by_category_per_class_strict
        def _count_wrapper(df, assigned_column, classes, step1_results=None, detected_pairs=None):
            return _orig(df, assigned_column, classes, step1_results, detected_pairs)
        m_step4.count_groups_by_category_per_class_strict = _count_wrapper

    xls = pd.ExcelFile(input_excel)
    df0 = xls.parse(xls.sheet_names[0])

    # STEP 1
    df1, _ = m_step1.create_immutable_step1(df0, num_classes=None)

    # Κενά -> NaN
    for c in [c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")]:
        mask = df1[c].astype(str).str.strip() == ""
        df1.loc[mask, c] = np.nan

    step1_cols = sorted(
        [c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")],
        key=_sid
    )

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

            # Βάλε τη ΒΗΜΑ2 δίπλα στη ΒΗΜΑ1
            cols = base.columns.tolist()
            if s2col in cols: cols.remove(s2col)
            idx = cols.index(s1col) + 1 if s1col in cols else len(cols)
            cols = cols[:idx] + [s2col] + cols[idx:]
            base = base[cols]

            # STEP 3
            df3, _ = m_h3.apply_step3_on_sheet(base.copy(), scenario_col=s2col, num_classes=None)
            s3col = f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}"
            cands3 = [c for c in df3.columns if str(c).startswith("ΒΗΜΑ3_")]
            if cands3 and s3col not in cands3:
                df3 = df3.rename(columns={cands3[0]: s3col})
            elif s3col not in df3.columns:
                df3[s3col] = ""

            # Βάλε τη ΒΗΜΑ3 δίπλα στη ΒΗΜΑ2
            cols3 = df3.columns.tolist()
            if s3col in cols3: cols3.remove(s3col)
            idx2 = cols3.index(s2col) + 1 if s2col in cols3 else len(cols3)
            cols3 = cols3[:idx2] + [s3col] + cols3[idx2:]
            df3 = df3[cols3]

            # Προετοιμασία ΦΙΛΟΙ για Step4 (string -> λίστα)
            if "ΦΙΛΟΙ" in df3.columns:
                try:
                    df3["ΦΙΛΟΙ"] = df3["ΦΙΛΟΙ"].apply(m_help2.parse_friends_cell)
                except Exception:
                    pass

            # STEP 4
            res4 = m_step4.apply_step4_with_enhanced_strategy(
                df3.copy(), assigned_column=s3col, num_classes=None, max_results=5
            )
            s4final = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"
            if res4:
                df4_mat = m_step4.export_step4_scenarios(df3.copy(), res4, assigned_column=s3col)
                # διάλεξε "best" ή index
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
                cands4 = [c for c in df4_mat.columns if str(c).startswith("ΒΗΜΑ4_")]
                if src in df4_mat.columns:
                    df4 = df4_mat.rename(columns={src: s4final})
                elif cands4:
                    df4 = df4_mat.rename(columns={cands4[0]: s4final})
                else:
                    df4 = df3.copy(); df4[s4final] = ""
            else:
                df4 = df3.copy(); df4[s4final] = ""

            # Βάλε τη ΒΗΜΑ4 δίπλα στη ΒΗΜΑ3 + dedup
            cols4 = df4.columns.tolist()
            if s4final in cols4: cols4.remove(s4final)
            idx3 = cols4.index(s3col) + 1 if s3col in cols4 else len(cols4)
            cols4 = cols4[:idx3] + [s4final] + cols4[idx3:]
            df4 = df4[cols4]
            df4 = _dedup(df4)

            # STEP 5 (ώστε να είναι έτοιμο για Step 6)
            df5, _pen5 = m_step5.step5_place_remaining_students(df4.copy(), scenario_col=s4final, num_classes=None)
            s5col = f"ΒΗΜΑ5_ΣΕΝΑΡΙΟ_{sid}"
            df5[s5col] = df5[s4final]
            cols5 = df5.columns.tolist()
            if s5col in cols5: cols5.remove(s5col)
            idx4 = cols5.index(s4final) + 1 if s4final in cols5 else len(cols5)
            cols5 = cols5[:idx4] + [s5col] + cols5[idx4:]
            df5 = df5[cols5]

            # Κράτα MIN στήλες + dedup
            keep = [c for c in CORE_COLUMNS if c in df5.columns] + [s1col, s2col, s3col, s4final, s5col]
            out_df = _dedup(df5[keep].copy())

            sheet_name = f"ΣΕΝΑΡΙΟ_{sid}"
            out_df.to_excel(w, sheet_name=sheet_name[:31], index=False)

# alias για συμβατότητα
build_step1_5_per_scenario = build_step1_4_per_scenario
```
