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
                        if n == s_num and s_suf:
                            wynik.append(f"{n}{s_suf}")
                        elif n == k_num and k_suf:
                            wynik.append(f"{n}{k_suf}")
                        else:
                            wynik.append(str(n))
            except:
                continue
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
        x_list = procesowane_dane[p]["X"]
        w_list = procesowane_dane[p]["W"]
        return dz_str in w_list or dz_str in x_list or (dz_str + typ) in x_list or (dz_str + typ) in w_list

    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        for p in ["Ania (Recepcja)"] + pracownicy + [awaryjny]:
            if dz_str in procesowane_dane[p]["W"]:
                if p == "Ania (Recepcja)":
                    grafik.at[p, dz_str] = "W"; godziny[p] += 8
                else:
                    grafik.at[f"{p} (D)", dz_str] = "W"
                    grafik.at[f"{p} (N)", dz_str] = "W"; godziny[p] += 12

    for d_idx, data in enumerate(dni_daty):
        dz_str = str(d_idx + 1)
        jutro_str = str(d_idx + 2)
        dzisiejsza_zmiana = {p: None for p in pracownicy + [awaryjny]}
        
        for p in pracownicy + [awaryjny]:
            if dz_str in procesowane_dane[p]["W"]: dzisiejsza_zmiana[p] = "W"

        # --- RECEPCJA ---
        if dz_str not in ania_urlopy and data.weekday() < 5 and data not in pl_holidays:
            grafik.at["Ania (Recepcja)", dz_str] = "R"; godziny["Ania (Recepcja)"] += 8
        elif dz_str in ilona_zastepstwa:
            if wczorajsza_zmiana["Ilona"] != "N" and not sprawdz_blokade("Ilona", dz_str, "D"):
                grafik.at["Ilona (D)", dz_str] = "R"; godziny["Ilona"] += 8
                dzisiejsza_zmiana["Ilona"] = "R"; historia_zmian["Ilona"]["R"] += 1

        # --- DNIÓWKA (D) ---
        kandydaci_d = [p for p in pracownicy + [awaryjny] if not sprawdz_blokade(p, dz_str, "D") and 
                       grafik.at[f"{p} (D)", dz_str] == "" and wczorajsza_zmiana[p] != "N"]
        
        kandydaci_d = [p for p in kandydaci_d if (p == "Waldek" and godziny[p] < limit_h - 12) or (p != "Waldek" and godziny[p] < limit_h)]

        if dz_str in ilona_zastepstwa and "Ilona" in kandydaci_d: kandydaci_d.remove("Ilona")
        
        bezpieczni_d = [p for p in kandydaci_d if wczorajsza_zmiana[p] not in ["D", "R"]]
        if bezpieczni_d: kandydaci_d = bezpieczni_d

        if kandydaci_d:
            def waga_d(p):
                score = godziny[p] - etat_h
                
                # Baza dla awaryjnego i nadgodzin Waldka
                if p == awaryjny:
                    score += 2000 if godziny[p] < 24 else 5000
                elif p == "Waldek" and godziny[p] >= etat_h:
                    score += 500
                    
                score += (historia_zmian[p]["D"] + historia_zmian[p]["R"] - historia_zmian[p]["N"]) * 5
                
                # ŻELAZNE PREFERENCJE
                chce_d = dz_str in procesowane_dane[p]["P_D"]
                chce_n = dz_str in procesowane_dane[p]["P_N"]
                
                if chce_d and chce_n:
                    score -= 50000  # Absolutny priorytet, wygrywa Dniówkę z każdym!
                elif chce_d:
                    score -= 10000  # Gwarancja zwykłej zmiany D
                    
                return score
                
            kandydaci_d.sort(key=lambda p: (waga_d(p), historia_zmian[p]["D"]))
            wybrany_d = kandydaci_d[0]
            grafik.at[f"{wybrany_d} (D)", dz_str] = "D"; godziny[wybrany_d] += 12
            historia_zmian[wybrany_d]["D"] += 1; dzisiejsza_zmiana[wybrany_d] = "D"

        # --- NOCKA (N) ---
        wybrany_n = None
        
        # 1. Zabezpieczenie nierozerwalności 24h (Z Urzędu)
        osoba_na_d = [p for p, zmiana in dzisiejsza_zmiana.items() if zmiana == "D"]
        if osoba_na_d:
            p_d = osoba_na_d[0]
            # Sprawdzamy czy ta osoba prosiła o Nockę tego samego dnia (czyli prosiła o 24h)
            if dz_str in procesowane_dane[p_d]["P_N"] and dz_str in procesowane_dane[p_d]["P_D"]:
                if not sprawdz_blokade(p_d, dz_str, "N"):
                    wybrany_n = p_d
        
        # 2. Szukanie standardowe (jeśli nikt nie wymusił 24h)
        if not wybrany_n:
            kandydaci_n = [p for p in pracownicy + [awaryjny] if not sprawdz_blokade(p, dz_str, "N") and 
                           dzisiejsza_zmiana[p] not in ["D", "R", "W"] and grafik.at[f"{p} (N)", dz_str] == ""]
            
            kandydaci_n = [p for p in kandydaci_n if (p == "Waldek" and godziny[p] < limit_h - 12) or (p != "Waldek" and godziny[p] < limit_h)]

            if jutro_str in ilona_zastepstwa and "Ilona" in kandydaci_n: kandydaci_n.remove("Ilona")
            
            bezpieczni_n = [p for p in kandydaci_n if wczorajsza_zmiana[p] != "N"]
            if bezpieczni_n: kandydaci_n = bezpieczni_n

            if kandydaci_n:
                def waga_n(p):
                    score = godziny[p] - etat_h
                    
                    if p == awaryjny:
                        score += 2000 if godziny[p] < 24 else 5000
                    elif p == "Waldek" and godziny[p] >= etat_h:
                        score += 500 
                    
                    score += (historia_zmian[p]["N"] - (historia_zmian[p]["D"] + historia_zmian[p]["R"])) * 5
                    
                    # ŻELAZNE PREFERENCJE
                    if dz_str in procesowane_dane[p]["P_N"]:
                        score -= 10000  # Gwarancja zwykłej zmiany N
                        
                    return score
                    
                kandydaci_n.sort(key=lambda p: (waga_n(p), historia_zmian[p]["N"]))
                wybrany_n = kandydaci_n[0]

        if wybrany_n:
            grafik.at[f"{wybrany_n} (N)", dz_str] = "N"; godziny[wybrany_n] += 12
            historia_zmian[wybrany_n]["N"] += 1
            dzisiejsza_zmiana[wybrany_n] = "N" 

        wczorajsza_zmiana = dzisiejsza_zmiana.copy()
    return grafik, godziny, dni_daty, pl_holidays, procesowane_dane

# --- 3. INTERFEJS ---
st.set_page_config(page_title="Zbalansowany Grafik v12", layout="wide")

pracownicy_lista = ["Ilona", "Waldek", "Krystian", "Kamil"]
awaryjny_pracownik = "Mateusz"

with st.sidebar:
    st.header("⚙️ Ustawienia")
    wybrany_rok = st.number_input("Rok", value=2024)
    wybrany_miesiac = st.selectbox("Miesiąc", list(range(1, 13)), index=datetime.now().month - 1)
    etat_h = st.number_input("Etat w tym miesiącu (h)", value=160)
    max_h = st.number_input("Maksymalny limit (h)", value=192)

st.header("📋 Grafik v12 (Żelazne Preferencje i Bloki 24h)")
st.info("💡 **Twarde zasady**: Jeśli wpiszesz komuś ten sam dzień w D i N, nie ma siły, która to rozerwie. Zwykłe preferencje też wchodzą praktycznie ze 100% pewnością.")

dane_wejsciowe = {}
cols = st.columns(3)
wszyscy = ["Ania (Recepcja)"] + pracownicy_lista + [awaryjny_pracownik]

for i, p in enumerate(wszyscy):
    with cols[i % 3]:
        st.subheader(p)
        w = st.text_input(f"Urlopy (W)", key=f"w_{p}", placeholder="np. 1, 5-8")
        x = st.text_input(f"Blokady (X)", key=f"x_{p}", placeholder="np. 10N-12D")
        
        if p == "Ania (Recepcja)":
            p_d = ""
            p_n = ""
        else:
            p_d = st.text_input(f"💛 Pref. Dniówki", key=f"pd_{p}", placeholder="np. 12, 14")
            p_n = st.text_input(f"🌙 Pref. Nocki", key=f"pn_{p}", placeholder="np. 12, 18")
            
        dane_wejsciowe[p] = {"W": w, "X": x, "P_D": p_d, "P_N": p_n}

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
            
            # Kolory weekendów
            if data.weekday() == 5: style = "background-color: #9ff572; color: black;"
            elif data.weekday() == 6 or data in swieta: style = "background-color: #f5dc72; color: black;"
            
            # Zastępstwa
            if row_label == "Ilona (D)" and val == "R":
                style = "background-color: #ffff00; color: black; font-weight: bold; border: 2px solid black;"

            # Kolory Blokad / Urlopów
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
        limit_info = f" (Limit: {max_h-12}h)" if name == "Waldek" else ""
        
        if name == awaryjny_pracownik:
            delta = val - 24
            c[i].metric(f"🛠️ {name}", f"{val}h", delta=f"{delta}h (od 24h)", delta_color="inverse")
        else:
            c[i].metric(f"{name}{limit_info}", f"{val}h", delta=f"{delta}h", delta_color="inverse")
            
