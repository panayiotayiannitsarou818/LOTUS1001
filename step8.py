
# export_best_only.py
# -------------------------------------------------------------
# Επιλέγει ΜΟΝΟ σενάρια Βήματος 6, βαθμολογεί με step7_fixed_final.py,
# κάνει τυχαίο tie-break σε ισοβαθμία συνολικού score και
# δημιουργεί ένα Excel με:
#   • BEST_SCENARIO (ολόκληρος ο πίνακας του νικητή + ΤΕΛΙΚΟ_ΤΜΗΜΑ)
#   • SUMMARY (πηγή & συνολικό σκορ)
#   • Ένα sheet ανά τμήμα: μόνο τα ΟΝΟΜΑΤΑ (NAMES_<ΤΜΗΜΑ>)
#
# Χρήση (CLI):
#   python export_best_only.py --step6 STEP6.xlsx --step7 step7_fixed_final.py --out BEST_ONLY_EXPORT.xlsx [--seed 123]
#
# Μπορείς επίσης να εισάγεις και να καλέσεις build_best_only_workbook(...) από άλλο script.
# -------------------------------------------------------------

import argparse
import importlib.util
import io
import re
import random
from collections import defaultdict

import pandas as pd


STEP6_SCEN_RE = r"^ΒΗΜΑ6_ΣΕΝΑΡΙΟ_\d+$"
NAME_CANDIDATES = [
    "ΟΝΟΜΑΤΕΠΩΝΥΜΟ", "ΜΑΘΗΤΗΣ", "ΜΑΘΗΤΡΙΑ",
    "ΟΝΟΜΑ", "ΟΝΟΜΑ_ΕΠΩΝΥΜΟ", "FULL_NAME", "NAME"
]


def _load_step7(step7_path: str):
    """Φόρτωση του step7_fixed_final.py ως module."""
    spec = importlib.util.spec_from_file_location("step7", step7_path)
    step7 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(step7)
    return step7


def _detect_step6_scenarios(df: pd.DataFrame) -> list[str]:
    """Επιστρέφει λίστα στηλών σεναρίων ΜΟΝΟ του Βήματος 6."""
    scen_cols = [c for c in df.columns if re.match(STEP6_SCEN_RE, str(c))]
    if not scen_cols:
        # Fallback σε “μοναδική” στήλη Β6 αν δεν υπάρχουν ΒΗΜΑ6_ΣΕΝΑΡΙΟ_N
        for cand in ("ΒΗΜΑ6_ΤΜΗΜΑ", "ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6"):
            if cand in df.columns:
                scen_cols = [cand]
                break
    return scen_cols


def _score_step6(df: pd.DataFrame, scen_cols: list[str], step7_mod) -> list[dict]:
    """Τρέχει score_one_scenario για κάθε σενάριο Β6 και επιστρέφει λίστα dicts."""
    rows = []
    for col in scen_cols:
        try:
            s = step7_mod.score_one_scenario(df.copy(), col)
            rows.append({"scenario": col, **s})
        except Exception as e:
            rows.append({"scenario": col, "error": str(e)})
    return rows


def _pick_best(scores: list[dict], seed: int | None = None) -> dict | None:
    """
    Επιλέγει το σενάριο με το μικρότερο total_score.
    Αν υπάρχει ισοβαθμία → τυχαία επιλογή ανάμεσα στους ισόβαθμους (αναπαραγώγιμη με seed).
    """
    valid = [s for s in scores if s.get("total_score") is not None]
    if not valid:
        return None
    min_score = min(s["total_score"] for s in valid)
    tied = [s for s in valid if s["total_score"] == min_score]
    if seed is not None:
        random.seed(seed)
    return random.choice(tied) if len(tied) > 1 else tied[0]


def _detect_name_column(df: pd.DataFrame) -> str | None:
    """Προσπαθεί να βρει στήλη ονόματος. Αν δεν βρει, επιστρέφει None (θα χρησιμοποιηθεί ID)."""
    upper = {str(c).upper(): str(c) for c in df.columns}
    for cand in NAME_CANDIDATES:
        if cand.upper() in upper:
            return upper[cand.upper()]

    # Εναλλακτικά: ΟΝΟΜΑ + ΕΠΩΝΥΜΟ
    first = None
    last = None
    for c in df.columns:
        cu = str(c).upper()
        if cu in ("ΟΝΟΜΑ", "FIRST_NAME", "ONOMA"):
            first = c
        if cu in ("ΕΠΩΝΥΜΟ", "LAST_NAME", "EPONYMO"):
            last = c
    if first and last:
        tmp = "__TMP_FULLNAME__"
        df[tmp] = df[first].astype(str).str.strip() + " " + df[last].astype(str).str.strip()
        return tmp

    return None


def _group_names_by_class(df: pd.DataFrame, class_col: str, name_col: str | None) -> dict[str, list[str]]:
    """Ομαδοποιεί ονόματα ανά τμήμα. Αν δεν υπάρχει name_col, χρησιμοποιεί ID ή placeholder."""
    out = defaultdict(list)
    for _, row in df.iterrows():
        klass = str(row[class_col])
        if name_col:
            nm = str(row[name_col])
        else:
            if "ID" in df.columns:
                nm = str(row["ID"])
            else:
                nm = "(χωρίς όνομα)"
        out[klass].append(nm)
    # Optional: αλφαβητική ταξινόμηση
    for k in list(out.keys()):
        out[k] = sorted(out[k], key=lambda s: s.lower())
    return out


def build_best_only_workbook(step6_xlsx_path: str, step7_py_path: str, out_xlsx_path: str, seed: int | None = None) -> None:
    """
    Φτιάχνει Excel ΜΟΝΟ με τον νικητή (σε όλα τα φύλλα του Step6 εισόδου),
    επιλέγοντας ανάμεσα σε σενάρια Βήματος 6 και με τυχαίο tie-break.
    """
    step7 = _load_step7(step7_py_path)
    xls6 = pd.ExcelFile(step6_xlsx_path)

    # Συλλογή όλων των υποψηφίων για συνολική επιλογή best
    candidates = []
    per_sheet_data = {}

    for sh in xls6.sheet_names:
        if str(sh).upper().startswith("SUMMARY"):
            continue
        df = pd.read_excel(xls6, sh)
        df.columns = [str(c) for c in df.columns]

        scen_cols = _detect_step6_scenarios(df)
        if not scen_cols:
            continue
        scores = _score_step6(df, scen_cols, step7)
        per_sheet_data[sh] = {"df": df, "scores": scores}

        for s in scores:
            if "total_score" in s and s.get("total_score") is not None:
                s["__SHEET__"] = sh
                candidates.append(s)

    if not candidates:
        raise RuntimeError("Δεν βρέθηκαν έγκυρα σενάρια Βήματος 6 για αξιολόγηση.")

    # Επιλογή συνολικού best (το μικρότερο total_score, tie-break τυχαία)
    best = _pick_best(candidates, seed=seed)
    best_sheet = best["__SHEET__"]
    best_col = best["scenario"]
    best_score = best["total_score"]

    # Κατασκευή αποτελέσματος
    df_best = per_sheet_data[best_sheet]["df"].copy()

    # Εισαγωγή ΤΕΛΙΚΟ_ΤΜΗΜΑ αμέσως μετά τη στήλη best_col
    if "ΤΕΛΙΚΟ_ΤΜΗΜΑ" in df_best.columns:
        df_best = df_best.drop(columns=["ΤΕΛΙΚΟ_ΤΜΗΜΑ"])
    cols = list(df_best.columns)
    ins_idx = cols.index(best_col) + 1 if best_col in cols else len(cols)
    df_best.insert(ins_idx, "ΤΕΛΙΚΟ_ΤΜΗΜΑ", df_best[best_col].values)
    df_best.insert(ins_idx + 1, "ΤΕΛΙΚΟ_ΣΕΝΑΡΙΟ", f"BEST_FROM: {best_col} ({best_sheet})")

    # Ονόματα ανά τμήμα
    name_col = _detect_name_column(df_best)
    class_col = "ΤΕΛΙΚΟ_ΤΜΗΜΑ" if "ΤΕΛΙΚΟ_ΤΜΗΜΑ" in df_best.columns else best_col
    class_to_names = _group_names_by_class(df_best, class_col=class_col, name_col=name_col)

    # Γράψιμο Excel
    with pd.ExcelWriter(out_xlsx_path, engine="xlsxwriter") as writer:
        # 1) BEST_SCENARIO (full table)
        df_best.to_excel(writer, index=False, sheet_name="BEST_SCENARIO")

        # 2) SUMMARY
        pd.DataFrame([{
            "SourceSheet": best_sheet,
            "ScenarioCol": best_col,
            "TotalScore": best_score
        }]).to_excel(writer, index=False, sheet_name="SUMMARY")

        # 3) Ένα sheet ανά τμήμα μόνο με τα ΟΝΟΜΑΤΑ
        for klass, names in sorted(class_to_names.items(), key=lambda kv: kv[0]):
            df_names = pd.DataFrame({"ΟΝΟΜΑ": names})
            safe_name = f"NAMES_{klass}"[:31]
            df_names.to_excel(writer, index=False, sheet_name=safe_name)


def _parse_args():
    ap = argparse.ArgumentParser(description="Εξαγωγή ενός Excel με μόνο το ΒΗΜΑ6 σενάριο με το μικρότερο score και ξεχωριστά sheets με τα ονόματα ανά τμήμα.")
    ap.add_argument("--step6", required=True, help="Μονοπάτι για το αρχείο Excel του Βήματος 6.")
    ap.add_argument("--step7", required=True, help="Μονοπάτι για το step7_fixed_final.py.")
    ap.add_argument("--out", required=True, help="Μονοπάτι εξόδου για το Excel (π.χ. BEST_ONLY_EXPORT.xlsx).")
    ap.add_argument("--seed", type=int, default=None, help="Random seed για αναπαραγωγιμότητα tie-break (προαιρετικό).")
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    build_best_only_workbook(args.step6, args.step7, args.out, seed=args.seed)
