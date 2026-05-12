import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import holidays

# --- 1. LOGIKA GENERUJĄCA GRAFIK ---
def generuj_grafik_macierz(rok, miesiac, pracownicy, awaryjny, limit_h, etat_h, dane_wejsciowe):
    if miesiac == 12:
        num_dni = (datetime(rok + 1, 1, 1) - datetime(rok, miesiac, 1)).days
    else:
        num_dni = (datetime(rok, miesiac + 1, 1) - datetime(rok, miesiac, 1)).days
    
    dni_daty = [datetime(rok, miesiac, d) for d in range(1, num_dni + 1)]
    dni_kolumny = [str(d) for d in range(1, num_dni + 1)]
    
    wiersze = ["Ania (Recepcja)"]
    for p in pracownicy + [awaryjny]:
        wiersze.append(f"{p} (D)")
        wiersze.append(f"{p} (N)")
    
    grafik = pd.DataFrame("", index=wiersze, columns=dni_kolumny)
    godziny = {p: 0 for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]}
    
    # Dodano "R" do historii, aby traktować Recepcję jako zmianę dzienną do balansowania
    historia_zmian = {p: {"D": 0, "N": 0, "R": 0} for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]}
    wczorajsza_zmiana = {p: None for p in pracownicy + [awaryjny]}
    
    pl_holidays = holidays.Poland(years=rok)
    ania_urlopy = dane_wejsciowe["Ania (Recepcja)"]["W"]
    ilona_zastepstwa = [str(d_idx + 1) for d_idx, data in enumerate(dni_daty) 
                        if str(d_idx + 1) in ania_urlopy and data.weekday() < 5 and data not in pl_holidays]

    def sprawdz_blokade(p, dz_str, typ):
        x_list = dane_wejsciowe[p]["X"]
        w_list = dane_wejsciowe[p]["W"]
        return dz_str in w_list or dz_str in x_list or (dz_str + typ) in x_list

    # Wstępne przypisanie urlopów na karcie
    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]:
            if dz_str in dane_wejsciowe[p]["W"]:
                if p == "Ania (Recepcja)":
                    grafik.at[p, dz_str] = "W"; godziny[p] += 8
                else:
                    grafik.at[f"{p} (D)", dz_str] = "W"
                    grafik.at[f"{p} (N)", dz_str] = "W"; godziny[p] += 12

    # GŁÓWNA PĘTLA DNI
    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        jutro_str = str(d_idx + 2)
        
        dzisiejsza_zmiana = {p: None for p in pracownicy + [awaryjny]}
        
        for p in pracownicy + [awaryjny]:
            if dz_str in dane_wejsciowe[p]["W"]:
                dzisiejsza_zmiana[p] = "W"

        # --- RECEPCJA ---
        if dz_str not in ania_urlopy and data.weekday() < 5 and data not in pl_holidays:
            grafik.at["Ania (Recepcja)", dz_str] = "R"; godziny["Ania (Recepcja)"] += 8
            historia_zmian["Ania (Recepcja)"]["R"] += 1
        elif dz_str in ilona_zastepstwa:
            if wczorajsza_zmiana["Ilona"] != "N": # Twarda blokada: R po N
                grafik.at["Ilona (D)", dz_str] = "R"; godziny["Ilona"] += 8
                dzisiejsza_zmiana["Ilona"] = "R"
                historia_zmian["Ilona"]["R"] += 1

        # --- DNIÓWKA (D) ---
        kandydaci_d = [p for p in pracownicy if not sprawdz_blokade(p, dz_str, "D") and 
                       grafik.at[f"{p} (D)", dz_str] == "" and 
                       wczorajsza_zmiana[p] != "N" and  # Twarda blokada N -> D
                       godziny[p] < limit_h]
        
        if dz_str in ilona_zastepstwa and "Ilona" in kandydaci_d: 
            kandydaci_d.remove("Ilona")

        # TWARDA BLOKADA D -> D
        bezpieczni_d = [p for p in kandydaci_d if wczorajsza_zmiana[p] not in ["D", "R"]]
        if bezpieczni_d:
            kandydaci_d = bezpieczni_d

        if kandydaci_d:
            def waga_d(p):
                score = godziny[p] - etat_h
                if p == "Waldek": score += 10 # Odciążanie Waldka
                if p == "Ilona" and jutro_str in ilona_zastepstwa: 
                    score -= 500 # Super priorytet na D dzień przed Recepcją
                
                # MODUŁ RÓŻNORODNOŚCI ZMIAN
                dniowki = historia_zmian[p]["D"] + historia_zmian[p]["R"]
                nocki = historia_zmian[p]["N"]
                score += (dniowki - nocki) * 5 # Zbyt dużo dniówek odsuwa na koniec kolejki
                
                return score

            kandydaci_d.sort(key=lambda p: (waga_d(p), historia_zmian[p]["D"]))
            wybrany_d = kandydaci_d[0]
            grafik.at[f"{wybrany_d} (D)", dz_str] = "D"; godziny[wybrany_d] += 12
            historia_zmian[wybrany_d]["D"] += 1
            dzisiejsza_zmiana[wybrany_d] = "D"

        # --- NOCKA (N) ---
        dzisiejszy_d = [p for p, zmiana in dzisiejsza_zmiana.items() if zmiana in ["D", "R", "W"]]
        
        kandydaci_n = [p for p in pracownicy if not sprawdz_blokade(p, dz_str, "N") and 
                       p not in dzisiejszy_d and 
                       grafik.at[f"{p} (N)", dz_str] == "" and godziny[p] < limit_h]
        
        if jutro_str in ilona_zastepstwa and "Ilona" in kandydaci_n: 
            kandydaci_n.remove("Ilona") # Twarda blokada N przed Recepcją

        # BLOKADA N -> N
        bezpieczni_n = [p for p in kandydaci_n if wczorajsza_zmiana[p] != "N"]
        if bezpieczni_n:
            kandydaci_n = bezpieczni_n

        if kandydaci_n:
            def waga_n(p):
                score = godziny[p] - etat_h
                if p == "Waldek": score += 10
                
                # MODUŁ RÓŻNORODNOŚCI ZMIAN
                dniowki = historia_zmian[p]["D"] + historia_zmian[p]["R"]
                nocki = historia_zmian[p]["N"]
                score += (nocki - dniowki) * 5 # Zbyt dużo nocek odsuwa na koniec kolejki
                
                return score

            kandydaci_n.sort(key=lambda p: (waga_n(p), historia_zmian[p]["N"]))
            wybrany_n = kandydaci_n[0]
            grafik.at[f"{wybrany_n} (N)", dz_str] = "N"; godziny[wybrany_n] += 12
            historia_zmian[wybrany_n]["N"] += 1
            dzisiejsza_zmiana[wybrany_n] = "N"
        else:
            if not sprawdz_blokade(awaryjny, dz_str, "N") and dzisiejsza_zmiana[awaryjny] not in ["D", "R", "W"] and grafik.at[f"{awaryjny} (N)", dz_str] == "":
                grafik.at[f"{awaryjny} (N)", dz_str] = "N"; godziny[awaryjny] += 12
                dzisiejsza_zmiana[awaryjny] = "N"

        wczorajsza_zmiana = dzisiejsza_zmiana.copy()

    return grafik, godziny, dni_daty, pl_holidays

# --- 2. INTERFEJS ---
st.set_page_config(page_title="Zbalansowany Grafik v4", layout="wide")

pracownicy_lista = ["Ilona", "Waldek", "Krystian", "Kamil"]
awaryjny_pracownik = "Mateusz"

with st.sidebar:
    st.header("⚙️ Ustawienia")
    wybrany_rok = st.number_input("Rok", value=2024)
    wybrany_miesiac = st.selectbox("Miesiąc", list(range(1, 13)), index=datetime.now().month - 1)
    etat_h = st.number_input("Ile godzin ma etat w tym miesiącu?", value=160)
    max_h = st.number_input("Maksymalny limit (blokada)", value=192)

st.header("📋 Dyspozycje")
dane_wejsciowe = {}
cols = st.columns(3)
wszyscy = ["Ania (Recepcja)"] + pracownicy_lista + [awaryjny_pracownik]

for i, p in enumerate(wszyscy):
    with cols[i % 3]:
        st.subheader(p)
        w = st.text_input(f"Urlopy (W) - {p}", key=f"w_{p}")
        x = st.text_input(f"Blokady (X/XD/XN) - {p}", key=f"x_{p}")
        dane_wejsciowe[p] = {
            "W": [d.strip() for d in w.split(",") if d.strip()],
            "X": [d.strip().upper() for d in x.split(",") if d.strip()]
        }

if st.button("🚀 Generuj Bezpieczny Grafik"):
    df, sumy, daty, swieta = generuj_grafik_macierz(wybrany_rok, wybrany_miesiac, pracownicy_lista, awaryjny_pracownik, max_h, etat_h, dane_wejsciowe)
    
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

            if dz_str in dane_wejsciowe[p_name]["W"]:
                style = "background-color: #d1c4e9; color: #4527a0; font-weight: bold;"
            elif dz_str in dane_wejsciowe[p_name]["X"] or (dz_str + typ_zmiany) in dane_wejsciowe[p_name]["X"]:
                style = "background-color: #d1c4e9; color: #d1c4e9;"
            
            styles.append(style)
        return styles

    st.dataframe(df.style.apply(style_grafik, axis=0), use_container_width=True, height=550)
    
    st.write(f"### ⚖️ Podsumowanie (Etat: {etat_h}h)")
    c = st.columns(len(sumy))
    for i, (name, val) in enumerate(sumy.items()):
        delta = val - etat_h
        c[i].metric(name, f"{val}h", delta=f"{delta}h", delta_color="inverse")
