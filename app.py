import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import holidays
import re

# --- 1. FUNKCJA PARSUJĄCA ZAKRESY ---
def parsuj_zakresy(tekst):
    wynik = []
    czesci = [c.strip().upper() for c in tekst.split(",") if c.strip()]
    for czesc in czesci:
        if "-" in czesc:
            try:
                start_str, koniec_str = czesc.split("-")
                start_m = re.match(r"(\d+)([DN]?)", start_str)
                koniec_m = re.match(r"(\d+)([DN]?)", koniec_str)
                if start_m and koniec_m:
                    s_num, s_suf = int(start_m.group(1)), start_m.group(2)
                    k_num, k_suf = int(koniec_m.group(1)), koniec_m.group(2)
                    for n in range(s_num, k_num + 1):
                        if n == s_num and s_suf: wynik.append(f"{n}{s_suf}")
                        elif n == k_num and k_suf: wynik.append(f"{n}{k_suf}")
                        else: wynik.append(str(n))
            except: continue
        else: wynik.append(czesc)
    return wynik

# --- 2. LOGIKA GENERUJĄCA GRAFIK ---
def generuj_grafik_macierz(rok, miesiac, pracownicy, awaryjny, limit_h, etat_h, dane_wejsciowe):
    if miesiac == 12:
        num_dni = (datetime(rok + 1, 1, 1) - datetime(rok, miesiac, 1)).days
    else:
        num_dni = (datetime(rok, miesiac + 1, 1) - datetime(rok, miesiac, 1)).days
    
    dni_daty = [datetime(rok, miesiac, d) for d in range(1, num_dni + 1)]
    dni_kolumny = [str(d) for d in range(1, num_dni + 1)]
    
    wiersze = ["Ania (Recepcja)"]
    for p in pracownicy + [awaryjny]:
        wiersze.append(f"{p} (D)"); wiersze.append(f"{p} (N)")
    
    grafik = pd.DataFrame("", index=wiersze, columns=dni_kolumny)
    godziny = {p: 0 for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]}
    historia_zmian = {p: {"D": 0, "N": 0, "R": 0} for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]}
    wczorajsza_zmiana = {p: None for p in pracownicy + [awaryjny]}
    pl_holidays = holidays.Poland(years=rok)
    
    procesowane_dane = {}
    for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]:
        procesowane_dane[p] = {
            "W": parsuj_zakresy(dane_wejsciowe[p]["W"]),
            "X": parsuj_zakresy(dane_wejsciowe[p]["X"]),
            "P_D": parsuj_zakresy(dane_wejsciowe[p]["P_D"]),
            "P_N": parsuj_zakresy(dane_wejsciowe[p]["P_N"])
        }

    ania_urlopy = procesowane_dane["Ania (Recepcja)"]["W"]
    ilona_zastepstwa = [str(d_idx + 1) for d_idx, data in enumerate(dni_daty) 
                        if str(d_idx + 1) in ania_urlopy and data.weekday() < 5 and data not in pl_holidays]

    def sprawdz_blokade(p, dz_str, typ):
        return dz_str in procesowane_dane[p]["W"] or dz_str in procesowane_dane[p]["X"] or \
               (dz_str + typ) in procesowane_dane[p]["X"] or (dz_str + typ) in procesowane_dane[p]["W"]

    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        jutro_str = str(d_idx + 2)
        dzisiejsza_zmiana = {p: None for p in pracownicy + [awaryjny]}

        # RECEPCJA
        if dz_str not in ania_urlopy and data.weekday() < 5 and data not in pl_holidays:
            grafik.at["Ania (Recepcja)", dz_str] = "R"; godziny["Ania (Recepcja)"] += 8
        elif dz_str in ilona_zastepstwa:
            if wczorajsza_zmiana["Ilona"] != "N" and not sprawdz_blokade("Ilona", dz_str, "D"):
                grafik.at["Ilona (D)", dz_str] = "R"; godziny["Ilona"] += 8
                dzisiejsza_zmiana["Ilona"] = "R"; historia_zmian["Ilona"]["R"] += 1

        # DNIÓWKA (D)
        kandydaci_d = [p for p in pracownicy + [awaryjny] if not sprawdz_blokade(p, dz_str, "D") and 
                       grafik.at[f"{p} (D)", dz_str] == "" and wczorajsza_zmiana[p] != "N"]
        
        # Filtr limitu godzin (Waldek ma 12h mniej)
        kandydaci_d = [p for p in kandydaci_d if (p == "Waldek" and godziny[p] < limit_h - 12) or (p != "Waldek" and godziny[p] < limit_h)]

        if dz_str in ilona_zastepstwa and "Ilona" in kandydaci_d: kandydaci_d.remove("Ilona")
        
        if kandydaci_d:
            def waga_d(p):
                # Bonus za życzenie, kara za Waldka (żeby dawać innym)
                score = godziny[p] - etat_h
                if p == "Waldek": score += 50  # Waldek zawsze na końcu przy równych godzinach
                if p == awaryjny: score = 0 if godziny[p] < 24 else 800
                if dz_str in procesowane_dane[p]["P_D"]: score -= 300
                return score
            
            kandydaci_d.sort(key=lambda p: waga_d(p))
            wybrany_d = kandydaci_d[0]
            grafik.at[f"{wybrany_d} (D)", dz_str] = "D"; godziny[wybrany_d] += 12
            dzisiejsza_zmiana[wybrany_d] = "D"; historia_zmian[wybrany_d]["D"] += 1

        # NOCKA (N)
        # 1. Sprawdź czy ktoś ma "zaklepaną" nockę przez 24h
        wybrany_n = None
        for p in pracownicy + [awaryjny]:
            if dzisiejsza_zmiana[p] == "D" and (dz_str in procesowane_dane[p]["P_D"]) and (dz_str in procesowane_dane[p]["P_N"]):
                if not sprawdz_blokade(p, dz_str, "N"):
                    wybrany_n = p
                    break
        
        # 2. Jeśli nikt nie zaklepał 24h, szukaj normalnie
        if not wybrany_n:
            kandydaci_n = [p for p in pracownicy + [awaryjny] if not sprawdz_blokade(p, dz_str, "N") and 
                           dzisiejsza_zmiana[p] not in ["D", "R", "W"] and grafik.at[f"{p} (N)", dz_str] == ""]
            
            kandydaci_n = [p for p in kandydaci_n if (p == "Waldek" and godziny[p] < limit_h - 12) or (p != "Waldek" and godziny[p] < limit_h)]

            if jutro_str in ilona_zastepstwa and "Ilona" in kandydaci_n: kandydaci_n.remove("Ilona")
            
            if kandydaci_n:
                def waga_n(p):
                    score = godziny[p] - etat_h
                    if p == "Waldek": score += 50
                    if p == awaryjny: score = 0 if godziny[p] < 24 else 800
                    if dz_str in procesowane_dane[p]["P_N"]: score -= 300
                    return score
                kandydaci_n.sort(key=lambda p: waga_n(p))
                wybrany_n = kandydaci_n[0]

        if wybrany_n:
            grafik.at[f"{wybrany_n} (N)", dz_str] = "N"; godziny[wybrany_n] += 12
            dzisiejsza_zmiana[wybrany_n] = "N"; historia_zmian[wybrany_n]["N"] += 1

        wczorajsza_zmiana = dzisiejsza_zmiana.copy()
    return grafik, godziny, dni_daty, pl_holidays, procesowane_dane

# --- 3. INTERFEJS ---
st.set_page_config(page_title="Zbalansowany Grafik v9", layout="wide")
pracownicy_lista = ["Ilona", "Waldek", "Krystian", "Kamil"]
awaryjny_pracownik = "Mateusz"

with st.sidebar:
    st.header("⚙️ Ustawienia")
    wybrany_rok = st.number_input("Rok", value=2024)
    wybrany_miesiac = st.selectbox("Miesiąc", list(range(1, 13)), index=datetime.now().month - 1)
    etat_h = st.number_input("Etat (h)", value=160)
    max_h = st.number_input("Maks. Limit (h)", value=192)

st.header("📋 Grafik v9 (Stabilny)")
st.info(f"💡 **Waldek**: System pilnuje, aby nie przekroczył {max_h - 12}h i daje mu zmiany w ostatniej kolejności.")

dane_wejsciowe = {}
cols = st.columns(3)
wszyscy = ["Ania (Recepcja)"] + pracownicy_lista + [awaryjny_pracownik]

for i, p in enumerate(wszyscy):
    with cols[i % 3]:
        st.subheader(p)
        w = st.text_input(f"Urlopy (W)", key=f"w_{p}")
        x = st.text_input(f"Blokady (X)", key=f"x_{p}")
        if p != "Ania (Recepcja)":
            p_d = st.text_input(f"💛 Pref. Dniówki", key=f"pd_{p}")
            p_n = st.text_input(f"🌙 Pref. Nocki", key=f"pn_{p}")
        else: p_d, p_n = "", ""
        dane_wejsciowe[p] = {"W": w, "X": x, "P_D": p_d, "P_N": p_n}

if st.button("🚀 Generuj Grafik"):
    df, sumy, daty, swieta, debug_dane = generuj_grafik_macierz(wybrany_rok, wybrany_miesiac, pracownicy_lista, awaryjny_pracownik, max_h, etat_h, dane_wejsciowe)
    st.dataframe(df, use_container_width=True, height=550)
    
    st.write("### ⚖️ Podsumowanie")
    c = st.columns(len(sumy))
    for i, (name, val) in enumerate(sumy.items()):
        delta = val - etat_h
        limit_info = f" (Limit: {max_h-12}h)" if name == "Waldek" else ""
        c[i].metric(f"{name}{limit_info}", f"{val}h", delta=f"{delta}h", delta_color="inverse")
