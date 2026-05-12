import streamlit as st
import pandas as pd
from datetime import datetime

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Generator Grafiku 12h", layout="wide")

st.title("📅 Generator Grafiku Pracy")

# --- PANEL BOCZNY (TWOJE WYTYCZNE) ---
st.sidebar.header("Ustawienia pracowników")

pracownicy_input = st.sidebar.text_input("Lista pracowników (oddziel przecinkiem)", 
                                        "Ilona, Waldek, Krystian, Kamil")
lista_p = [p.strip() for p in pracownicy_input.split(",")]

awaryjny = st.sidebar.text_input("Pracownik awaryjny", "Mateusz")

st.sidebar.header("Limity godzin")
min_h = st.sidebar.number_input("Minimum godzin", value=168)
max_h = st.sidebar.number_input("Maksimum godzin", value=192)

# --- LOGIKA GENEROWANIA ---
# Tutaj wstawiamy naszą funkcję generuj_grafik_macierz (z poprzedniej wiadomości)
# ... (logika pozostaje ta sama, tylko zmienne biorą dane z suwaków) ...

if st.button("Generuj nowy grafik"):
    df_grafik, suma_godzin = generuj_grafik_macierz(2024, 6, lista_p, awaryjny)
    
    # Wyświetlanie tabeli w aplikacji
    st.write("### Grafik na dany miesiąc")
    st.dataframe(df_grafik.style.highlight_max(axis=0, color='#f0f2f6')) 

    # Wyświetlanie statystyk
    st.write("### Podsumowanie godzin")
    col1, col2 = st.columns(2)
    for i, (p, h) in enumerate(suma_godzin.items()):
        target_col = col1 if i % 2 == 0 else col2
        target_col.metric(label=p, value=f"{h}h", delta=f"{h-min_h}h nad minimum")
