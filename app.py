import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import holidays
import re

# --- 1. FUNKCJA PARSUJĄCA ZAKRESY ---
def parsuj_zakresy(tekst):
    """Zamienia '17-20, 16N-18D' na listę ['17', '18', '19', '20', '16N', '17', '18D']"""
    wynik = []
    czesci = [c.strip().upper() for c in tekst.split(",") if c.strip()]
    
    for czesc in czesci:
        if "-" in czesc:
            try:
                start_str, koniec_str = czesc.split("-")
                # Wyciągamy same liczby i ewentualne litery (D/N)
                start_m = re.match(r"(\d+)([DN]?)", start_str)
                koniec_m = re.match(r"(\d+)([DN]?)", koniec_str)
                
                if start_m and koniec_m:
                    s_num, s_suf = int(start_m.group(1)), start_m.group(2)
                    k_num, k_suf = int(koniec_m.group(1)), koniec_m.group(2)
                    
                    for n in range(s_num, k_num + 1):
                        if n == s_num and s_suf: # Pierwszy dzień zakresu
                            wynik.append(f"{n}{s_suf}")
                        elif n == k_num and k_suf: # Ostatni dzień zakresu
                            wynik.append(f"{n}{k_suf}")
                        else: # Dni w środku zakresu - pełna niedostępność
                            wynik.append(str(n))
            except:
                continue # Jeśli ktoś wpisze głupoty, pomijamy
        else:
            wynik.append(czesc)
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
    
    # Procesowanie urlopów i blokad (używamy parsera!)
    procesowane_dane = {}
    for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]:
        procesowane_dane[p] = {
            "W": parsuj_zakresy(dane_wejsciowe[p]["W"]),
            "X": parsuj_zakresy(dane_wejsciowe[p]["X"])
        }

    ania_urlopy = procesowane_dane["Ania (Recepcja)"]["W"]
    ilona_zastepstwa = [str(d_idx + 1) for d_idx, data in enumerate(dni_daty) 
                        if str(d_idx + 1) in ania_urlopy and data.weekday() < 5 and data not in pl_holidays]

    def sprawdz_blokade(p, dz_str, typ):
        x_list = procesowane_dane[p]["X"]
        w_list = procesowane_dane[p]["W"]
        # Blokada jeśli: dzień jest na liście (cały dzień) LUB dzień+typ (np. 16N)
        return dz_str in w_list or dz_str in x_list or (dz_str + typ) in x_list or (dz_str + typ) in w_list

    # Wstępne urlopy
    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]:
            if dz_str in procesowane_dane[p]["W"]:
                if p == "Ania (Recepcja)":
                    grafik.at[p, dz_str] = "W"; godziny[p] += 8
                else:
                    grafik.at[f"{p} (D)", dz_str] = "W"
                    grafik.at[f"{p} (N)", dz_str] = "W"; godziny[p] += 12

    # Pętla generowania
    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        jutro_str = str(d_idx + 2)
        dzisiejsza_zmiana = {p: None for p in pracownicy + [awaryjny]}
        
        for p in pracownicy + [awaryjny]:
            if dz_str in procesowane_dane[p]["W"]: dzisiejsza_zmiana[p] = "W"

        # RECEPCJA
        if dz_str not in ania_urlopy and data.weekday() < 5 and data not in pl_holidays:
            grafik.at["Ania (Recepcja)", dz_str] = "R"; godziny["Ania (Recepcja)"] += 8
        elif dz_str in ilona_zastepstwa:
            if wczorajsza_zmiana["Ilona"] != "N" and not sprawdz_blokade("Ilona", dz_str, "D"):
                grafik.at["Ilona (D)", dz_str] = "R"; godziny["Ilona"] += 8
                dzisiejsza_zmiana["Ilona"] = "R"; historia_zmian["Ilona"]["R"] += 1

        # DNIÓWKA (D)
        kandydaci_d = [p for p in pracownicy if not sprawdz_blokade(p, dz_str, "D") and 
                       grafik.at[f"{p} (D)", dz_str] == "" and wczorajsza_zmiana[p] != "N" and godziny[p] < limit_h]
        if dz_str in ilona_zastepstwa and "Ilona" in kandydaci_d: kandydaci_d.remove("Ilona")
        
        bezpieczni_d = [p for p in kandydaci_d if wczorajsza_zmiana[p] not in ["D", "R"]]
        if bezpieczni_d: kandydaci_d = bezpieczni_d

        if kandydaci_d:
            def waga_d(p):
                score = godziny[p] - etat_h
                if p == "Waldek": score += 10
                if p == "Ilona" and jutro_str in ilona_zastepstwa: score -= 500
                score += (historia_zmian[p]["D"] + historia_zmian[p]["R"] - historia_zmian[p]["N"]) * 5
                return score
            kandydaci_d.sort(key=lambda p: (waga_d(p), historia_zmian[p]["D"]))
            wybrany_d = kandydaci_d[0]
            grafik.at[f"{wybrany_d} (D)", dz_str] = "D"; godziny[wybrany_d] += 12
            historia_zmian[wybrany_d]["D"] += 1; dzisiejsza_zmiana[wybrany_d] = "D"

        # NOCKA (N)
        dzisiejszy_d = [p for p, zmiana in dzisiejsza_zmiana.items() if zmiana in ["D", "R", "W"]]
        kandydaci_n = [p for p in pracownicy if not sprawdz_blokade(p, dz_str, "N") and 
                       p not in dzisiejszy_d and grafik.at[f"{p} (N)", dz_str] == "" and godziny[p] < limit_h]
        if jutro_str in ilona_zastepstwa and "Ilona" in kandydaci_n: kandydaci_n.remove("Ilona")
        
        bezpieczni_n = [p for p in kandydaci_n if wczorajsza_zmiana[p] != "N"]
        if bezpieczni_n: kandydaci_n = bezpieczni_n

        if kandydaci_n:
            def waga_n(p):
                score = godziny[p] - etat_h
                if p == "Waldek": score += 10
                score += (historia_zmian[p]["N"] - (historia_zmian[p]["D"] + historia_zmian[p]["R"])) * 5
                return score
            kandydaci_n.sort(key=lambda p: (waga_n(p), historia_zmian[p]["N"]))
            wybrany_n = kandydaci_n[0]
            grafik.at[f"{wybrany_n} (N)", dz_str] = "N"; godziny[wybrany_n] += 12
            historia_zmian[wybrany_n]["N"] += 1; dzisiejsza_zmiana[wybrany_n] = "N"
        else:
            if not sprawdz_blokade(awaryjny, dz_str, "N") and dzisiejsza_zmiana[awaryjny] not in ["D", "R", "W"]:
                grafik.at[f"{awaryjny} (N)", dz_str] = "N"; godziny[awaryjny] += 12; dzisiejsza_zmiana[awaryjny] = "N"

        wczorajsza_zmiana = dzisiejsza_zmiana.copy()
    return grafik, godziny, dni_daty, pl_holidays, procesowane_dane

# --- 3. INTERFEJS ---
st.set_page_config(page_title="Zbalansowany Grafik v5", layout="wide")

pracownicy_lista = ["Ilona", "Waldek", "Krystian", "Kamil"]
awaryjny_pracownik = "Mateusz"

with st.sidebar:
    st.header("⚙️ Ustawienia")
    wybrany_rok = st.number_input("Rok", value=2024)
    wybrany_miesiac = st.selectbox("Miesiąc", list(range(1, 13)), index=datetime.now().month - 1)
    etat_h = st.number_input("Etat w tym miesiącu (h)", value=160)
    max_h = st.number_input("Maksymalny limit (h)", value=192)

st.header("📋 Dyspozycje")
st.info("💡 Możesz wpisywać zakresy, np.: **10-15** (całe dni), **16N-18D** (od nocki 16-go do dniówki 18-go).")

dane_wejsciowe = {}
cols = st.columns(3)
wszyscy = ["Ania (Recepcja)"] + pracownicy_lista + [awaryjny_pracownik]

for i, p in enumerate(wszyscy):
    with cols[i % 3]:
        st.subheader(p)
        w = st.text_input(f"Urlopy (W) - {p}", key=f"w_{p}", placeholder="np. 1, 5-8")
        x = st.text_input(f"Blokady (X) - {p}", key=f"x_{p}", placeholder="np. 10N-12D")
        dane_wejsciowe[p] = {"W": w, "X": x}

if st.button("🚀 Generuj Grafik"):
    df, sumy, daty, swieta, debug_dane = generuj_grafik_macierz(wybrany_rok, wybrany_miesiac, pracownicy_lista, awaryjny_pracownik, max_h, etat_h, dane_wejsciowe)
    
    def style_grafik(col):
        d_idx = int(col.name) - 1
        data = daty[d_idx]
        styles = []
        for row_label, val in col.items():
            style = ""
            dz_str = col.name
            p_name = "Ania (Recepcja)" if row_label == "Ania (Recepcja)" else row_label.split(" (")[0]
            typ_zmiany = "D" if "(D)" in row_label else ("N" if "(N)" in row_label else "R")
            
            if data.weekday() == 5: style = "background-color: #9ff572; color: black;"
            elif data.weekday() == 6 or data in swieta: style = "background-color: #f5dc72; color: black;"
            
            if row_label == "Ilona (D)" and val == "R":
                style = "background-color: #ffff00; color: black; font-weight: bold; border: 2px solid black;"

            # Kolorowanie urlopów/blokad z debug_dane (używając sparsowanych list)
            if dz_str in debug_dane[p_name]["W"] or (dz_str + typ_zmiany) in debug_dane[p_name]["W"]:
                style = "background-color: #d1c4e9; color: #4527a0; font-weight: bold;"
            elif dz_str in debug_dane[p_name]["X"] or (dz_str + typ_zmiany) in debug_dane[p_name]["X"]:
                style = "background-color: #d1c4e9; color: #d1c4e9;"
            
            styles.append(style)
        return styles

    st.dataframe(df.style.apply(style_grafik, axis=0), use_container_width=True, height=550)
    
    st.write(f"### ⚖️ Podsumowanie (Etat: {etat_h}h)")
    c = st.columns(len(sumy))
    for i, (name, val) in enumerate(sumy.items()):
        delta = val - etat_h
        c[i].metric(name, f"{val}h", delta=f"{delta}h", delta_color="inverse")
