# -*- coding: utf-8 -*-
# app_wrapper_two_buttons.py (v4 - guided flow)
# Κουμπί 1: Εκτέλεση Βήματα 1–6  → αποθηκεύει στη μνήμη (session) το αρχείο Step6
# Κουμπί 2: Τελική κατανομή (Βήματα 7–8) → ΧΡΗΣΙΜΟΠΟΙΕΙ ΜΟΝΟ το Step6 από τη μνήμη
#  - Το Κουμπί 2 είναι απενεργοποιημένο μέχρι να ολοκληρωθεί το Κουμπί 1.

import streamlit as st
import tempfile, os, importlib.util, sys
from pathlib import Path

st.set_page_config(page_title="Wrapper 1–6 & 7–8 (guided)", layout="centered")

# ---------------- Sidebar stepper ----------------
st.sidebar.title("Οδηγός")
if "step6_bytes" not in st.session_state:
    st.session_state["step6_bytes"] = None
if "step6_name" not in st.session_state:
    st.session_state["step6_name"] = "STEP1_to_6_PER_SCENARIO_MIN.xlsx"

step6_ready = bool(st.session_state.get("step6_bytes"))

st.sidebar.markdown("**1️⃣ Βήματα 1–6**  \n— Ανέβασε STEP1 και πάτα το κουμπί.")
st.sidebar.markdown(("✅ Ολοκληρώθηκε" if step6_ready else "⛔ Εκκρεμεί"))
st.sidebar.markdown("---")
st.sidebar.markdown("**2️⃣ Βήματα 7–8**  \n— Πατάς ΜΟΝΟ αφού ολοκληρωθεί το 1–6.")
st.sidebar.markdown(("🔓 Διαθέσιμο" if step6_ready else "🔒 Κλειδωμένο"))

st.title("Wrapper 1–6 και 7–8 (MIN)")
st.caption("**Ροή:** Πρώτα 1️⃣ (παράγει Step6), μετά 2️⃣ (χρησιμοποιεί αυτόματα το Step6).")

WORKDIR = Path(__file__).parent

def _import_by_path(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod

def _first_existing(*names: str) -> Path | None:
    for n in names:
        p = WORKDIR / n
        if p.exists():
            return p
    return None

# -------------------- Κουμπί 1 — Εκτέλεση Βήματα 1–6 --------------------
st.header("1️⃣ Πρώτα: Εκτέλεση Βήματα 1–6")
st.info("Ανέβασε το Excel του Βήματος 1. Θα παραχθεί **STEP1_to_6_PER_SCENARIO_MIN.xlsx** και θα μείνει στη μνήμη για το Κουμπί 2.")
uploaded_step1 = st.file_uploader("Ανέβασε STEP1_IMMUTABLE_*.xlsx", type=["xlsx"], key="up1")
run_1_6 = st.button("▶️ Εκτέλεση Βήματα 1–6", help="Παράγει το αρχείο του Βήματος 6 και το κρατά στη μνήμη.")

if run_1_6:
    if not uploaded_step1:
        st.error("Πρώτα ανέβασε αρχείο Βήματος 1.")
        st.stop()

    exporter_path = _first_existing("export_step1__per_scenario.py", "export_step1_4_per_scenario.py")
    if exporter_path is None:
        st.error("Δεν βρέθηκε exporter (export_step1__per_scenario.py ή export_step1_4_per_scenario.py).")
        st.stop()

    step6_path = _first_existing("step6_compliant.py", "step6.py")
    if step6_path is None:
        st.error("Δεν βρέθηκε step6_compliant.py.")
        st.stop()

    with st.spinner("Τρέχουν τα Βήματα 1→6 ..."):
        with tempfile.TemporaryDirectory() as tmpd:
            tmpd = Path(tmpd)
            in_path = tmpd / "STEP1_input.xlsx"
            out_1_5 = tmpd / "STEP1_to_5_PER_SCENARIO_MIN.xlsx"
            out_1_6 = tmpd / "STEP1_to_6_PER_SCENARIO_MIN.xlsx"  # consistent filename

            with open(in_path, "wb") as f:
                f.write(uploaded_step1.read())

            # 1→5
            exp = _import_by_path("exporter_min", exporter_path)
            if hasattr(exp, "build_step1_4_per_scenario"):
                exp.build_step1_4_per_scenario(str(in_path), str(out_1_5), pick_step4="best")
            elif hasattr(exp, "build_step1_5_per_scenario"):
                exp.build_step1_5_per_scenario(str(in_path), str(out_1_5), pick_step4="best")
            else:
                st.error("Δεν βρέθηκε συνάρτηση build_step1_4_per_scenario στο exporter.")
                st.stop()

            # 6
            m6 = _import_by_path("step6_mod", step6_path)
            if hasattr(m6, "export_single_noaudit"):
                m6.export_single_noaudit(str(out_1_5), str(out_1_6))
            else:
                st.error("Στο step6_compliant.py δεν βρέθηκε export_single_noaudit(...).")
                st.stop()

            # Store to session
            step6_bytes = open(out_1_6, "rb").read()
            st.session_state["step6_bytes"] = step6_bytes
            st.session_state["step6_name"] = out_1_6.name

            st.success("✅ Ολοκλήρωση Βήματος 1–6! Το αποτέλεσμα αποθηκεύτηκε για χρήση στο Κουμπί 2.")
            st.download_button(
                "⬇️ Κατέβασε STEP1_to_6_PER_SCENARIO_MIN.xlsx",
                data=step6_bytes,
                file_name="STEP1_to_6_PER_SCENARIO_MIN.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.toast("Το Κουμπί 2 ξεκλειδώθηκε.", icon="✅")

# Update lock indicator
step6_ready = bool(st.session_state.get("step6_bytes"))

st.divider()

# -------------------- Κουμπί 2 — Τελική κατανομή (Βήματα 7–8) --------------------
st.header("2️⃣ Μετά: Τελική κατανομή (Βήματα 7–8)")
st.warning("Για να πάρεις την **τελική κατανομή**, πρέπει πρώτα να εκτελέσεις το **Κουμπί 1** και μετά να πατήσεις **αυτό το κουμπί**.", icon="⚠️")
seed_val = st.number_input("Seed για tie-break (προαιρετικό)", value=42, step=1)
run_7_8 = st.button(
    "🏁 Τελική κατανομή — Εκτέλεση Βήματα 7–8 (auto)",
    help="Χρησιμοποιεί αυτόματα το αρχείο του Βήματος 6 από το Κουμπί 1.",
    disabled=not step6_ready
)

if run_7_8:
    step7_path = _first_existing("step7_fixed_final.py")
    step8_path = _first_existing("step8.py")
    if step7_path is None or step8_path is None:
        st.error("Χρειάζονται στον ίδιο φάκελο τα αρχεία: step7_fixed_final.py και step8.py.")
        st.stop()

    with st.spinner("Τρέχουν τα Βήματα 7→8 ..."):
        with tempfile.TemporaryDirectory() as tmpd:
            tmpd = Path(tmpd)
            in_path = tmpd / st.session_state.get("step6_name", "STEP1_to_6_PER_SCENARIO_MIN.xlsx")
            out_best = tmpd / "BEST_ONLY_EXPORT.xlsx"

            with open(in_path, "wb") as f:
                f.write(st.session_state["step6_bytes"])

            step8 = _import_by_path("step8_mod", step8_path)
            if hasattr(step8, "build_best_only_workbook"):
                step8.build_best_only_workbook(str(in_path), str(step7_path), str(out_best), seed=int(seed_val) if seed_val else None)
            else:
                st.error("Στο step8.py δεν βρέθηκε build_best_only_workbook(...).")
                st.stop()

            best_bytes = open(out_best, "rb").read()
            st.success("🎉 Έτοιμο το τελικό (Βήματα 7–8)!")
            st.download_button(
                "⬇️ Κατέβασε BEST_ONLY_EXPORT.xlsx",
                data=best_bytes,
                file_name="BEST_ONLY_EXPORT.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
