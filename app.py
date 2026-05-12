import streamlit as st
import pandas as pd
from datetime import datetime

# --- 1. DEFINICJA FUNKCJI GENERUJĄCEJ (Logika) ---
def generuj_grafik_macierz(rok, miesiac, pracownicy, awaryjny, min_h, max_h):
    # Obliczanie liczby dni w miesiącu
    if miesiac == 12:
        num_dni = (datetime(rok + 1, 1, 1) - datetime(rok, miesiac, 1)).days
    else:
        num_dni = (datetime(rok, miesiac + 1, 1) - datetime(rok, miesiac, 1)).days
    
    dni_kolumny = [str(d) for d in range(1, num_dni + 1)]
    wszyscy = pracownicy + [awaryjny]
    grafik = pd.DataFrame("-", index=wszyscy, columns=dni_kolumny)
    
    godziny = {p: 0 for p in wszyscy}
    cykl_idx = {p: i % 4 for i, p in enumerate(pracownicy)}

    for d in range(1, num_dni + 1):
        dzien_str = str(d)
        obsada_dzien = None
        obsada_noc = None

        # Szukamy obsady na dzień
        for p in pracownicy:
            if cykl_idx[p] == 0 and godziny[p] < max_h:
                obsada_dzien = p
                break
        
        # Szukamy obsady na noc
        for p in pracownicy:
            if cykl_idx[p] == 1 and p != obsada_dzien and godziny[p] < max_h:
                obsada_noc = p
                break
        
        # Jeśli brakuje obsady, wchodzi awaryjny (max 48h / 4 zmiany)
        if not obsada_noc and godziny[awaryjny] < 48:
            obsada_noc = awaryjny

        # Zapis do tabeli
        if obsada_dzien:
            grafik.at[obsada_dzien, dzien_str] = "D"
            godziny[obsada_dzien] += 12
        if obsada_noc:
            grafik.at[obsada_noc, dzien_str] = "N"
            godziny[obsada_noc] += 12

        # Przesunięcie cyklu
        for p in pracownicy:
            cykl_idx[p] = (cykl_idx[p] + 1) % 4

    return grafik, godziny

# --- 2. KONFIGURACJA INTERFEJSU STREAMLIT ---
st.set_page_config(page_title="Generator Grafiku 12h", layout="wide")
st.title("📅 Generator Grafiku Pracy")

# Panel boczny
st.sidebar.header("Ustawienia")
wybrany_miesiac = st.sidebar.slider("Miesiąc", 1, 12, datetime.now().month)
wybrany_rok = st.sidebar.number_input("Rok", value=2024)

pracownicy_input = st.sidebar.text_input("Pracownicy etatowi (po przecinku)", 
                                        "Ilona, Waldek, Krystian, Kamil")
lista_p = [p.strip() for p in pracownicy_input.split(",")]

awaryjny_input = st.sidebar.text_input("Pracownik awaryjny", "Mateusz")

st.sidebar.header("Normy godzinowe")
min_h = st.sidebar.number_input("Minimum godzin", value=168)
max_h = st.sidebar.number_input("Maksimum godzin", value=192)

# Przycisk generowania
if st.button("Generuj grafik"):
    df, sumy = generuj_grafik_macierz(wybrany_rok, wybrany_miesiac, lista_p, awaryjny_input, min_h, max_h)
    
    st.write(f"### Grafik na {wybrany_miesiac}/{wybrany_rok}")
    st.dataframe(df, use_container_width=True)
    
    st.write("### Podsumowanie godzin")
    kolumny = st.columns(len(sumy))
    for i, (p, h) in enumerate(sumy.items()):
        kolumny[i].metric(label=p, value=f"{h}h", delta=f"{h-min_h}h")
