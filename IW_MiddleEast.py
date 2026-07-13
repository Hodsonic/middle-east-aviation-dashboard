import streamlit as st
import pandas as pd
import glob
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Middle East Aviation Exposure Dashboard", layout="wide")
st.title("Middle East Aviation Exposure Dashboard (29th June - 13th July)")
st.subheader("Powered by Insurwave data (Timestamps are in UTC)")

# Airport Mapping for stable country lookups
AIRPORT_TO_COUNTRY = {
    "BAH": "BH", "CAI": "EG", "HBE": "EG", "SSH": "EG", "IKA": "IR", 
    "BGW": "IQ", "TLV": "IL", "AMM": "JO", "AQJ": "JO", "KWI": "KW", 
    "BEY": "LB", "MCT": "OM", "DOH": "QA", "JED": "SA", "RUH": "SA", 
    "DMM": "SA", "DAM": "SY", "IST": "TR", "ESB": "TR", "AYT": "TR", 
    "AUH": "AE", "DXB": "AE", "SHJ": "AE", "DWC": "AE", "AAN": "AE", 
    "FJR": "AE", "ADE": "YE", "ISL": "TR", "SAW": "TR", "BJV": "TR"
}

AIRPORT_LOOKUP = {
    "BAH": "Bahrain Intl", "CAI": "Cairo Intl", "HBE": "Borg El Arab", "SSH": "Sharm El Sheikh",
    "IKA": "Imam Khomeini", "BGW": "Baghdad Intl", "TLV": "Ben Gurion", "AMM": "Queen Alia",
    "AQJ": "Aqaba Intl", "KWI": "Kuwait Intl", "BEY": "Beirut-Rafic Hariri", "MCT": "Muscat Intl",
    "DOH": "Hamad Intl", "JED": "King Abdulaziz", "RUH": "King Khalid", "DMM": "Dammam Intl",
    "DAM": "Damascus Intl", "IST": "Istanbul Airport", "ESB": "Ankara Esenboğa", "AYT": "Antalya",
    "AUH": "Abu Dhabi Intl", "DXB": "Dubai Intl", "SHJ": "Sharjah Intl", "DWC": "Al Maktoum",
    "AAN": "Al Ain Intl", "FJR": "Fujairah Intl", "ADE": "Aden Intl", "ISL": "Istanbul Atatürk",
    "SAW": "Sabiha Gökçen", "BJV": "Milas-Bodrum"
}

# --- 2. DATA LOADING ---
@st.cache_data
def load_data():
    file_pattern = "Middle-East - Historic Exposure Report - *.xlsx"
    files = glob.glob(file_pattern)
    all_data = []
    for f in files:
        df = pd.read_excel(f, sheet_name='Asset Exposure')
        time_str = f.split('-')[-1].strip().replace('.xlsx', '')
        dt_obj = pd.to_datetime(time_str, format="%d_%m_%Y(%H_%M)")
        df['Snapshot Time'] = dt_obj
        df['Date'] = dt_obj.date()
        df['Time of Day'] = dt_obj.strftime("%H:%M")
        df['Exposure'] = df['Total Insured Value'] * df['Line Share %']
        all_data.append(df)
        
    if not all_data: return pd.DataFrame()
    df_master = pd.concat(all_data, ignore_index=True)
    
    # Map country using IATA code
    df_master['Country'] = df_master['Arrival IATA'].map(AIRPORT_TO_COUNTRY).fillna("Unknown")
    
    df_master['Airport_Code'] = df_master.apply(
        lambda x: x['Arrival IATA'] if x['Is on Ground'] == 'Yes' else 'In Flight', axis=1
    )
    def format_airport(code):
        if code == 'In Flight': return 'In Flight'
        name = AIRPORT_LOOKUP.get(code)
        return f"{code} - {name}" if name else code
    df_master['Airport_Display'] = df_master['Airport_Code'].apply(format_airport)
    return df_master

df_master = load_data()

# --- 3. FILTERS ---
st.sidebar.header("Dashboard Filters")
df_filtered = df_master.copy()

unique_airports = [str(x) for x in df_filtered['Airport_Display'].unique() if x != 'In Flight']
selected_airports = st.sidebar.multiselect("Select Airports", options=sorted(unique_airports))
policies = st.sidebar.multiselect("Select Policy Name", options=sorted([str(x) for x in df_filtered['Policy Name'].fillna('None').unique()]))

if selected_airports:
    df_filtered = df_filtered[df_filtered['Airport_Display'].astype(str).isin(selected_airports)]
if policies:
    df_filtered = df_filtered[df_filtered['Policy Name'].astype(str).isin(policies)]

# --- 4. EXPOSURE TREND ---
st.subheader("Exposure Trend Over Time")
trend_data = df_filtered.groupby('Snapshot Time').agg(Exposure=('Exposure', 'sum'), Aircraft_Count=('Name/Registration', 'count')).reset_index()
fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Scatter(x=trend_data['Snapshot Time'], y=trend_data['Exposure'], name="Total Exposure"), secondary_y=False)
fig.add_trace(go.Scatter(x=trend_data['Snapshot Time'], y=trend_data['Aircraft_Count'], name="Aircraft Count"), secondary_y=True)
fig.update_yaxes(title_text="Total Insured Value * Line Share %", secondary_y=False)
fig.update_yaxes(title_text="Aircraft Count", secondary_y=True)
st.plotly_chart(fig, use_container_width=True)

# --- 5. AIRPORT ON THE GROUND EXPOSURES ---
st.subheader("Airport on the Ground Exposures")
available_days = sorted(df_filtered['Date'].unique())
selected_day = st.selectbox("Select a Day:", options=available_days)
grounded_day_df = df_filtered[(df_filtered['Date'] == selected_day) & (df_filtered['Is on Ground'] == 'Yes')]
top_15 = grounded_day_df.groupby('Airport_Display')['Name/Registration'].count().nlargest(15).index
grounded_day_df = grounded_day_df[grounded_day_df['Airport_Display'].isin(top_15)]

pivot_df = grounded_day_df.groupby(['Airport_Display', 'Time of Day']).agg(Aircraft_Count=('Name/Registration', 'count')).reset_index()
fig = go.Figure()
for time_val in ['04:00', '12:00', '20:00']:
    subset = pivot_df[pivot_df['Time of Day'] == time_val]
    fig.add_trace(go.Bar(x=subset['Airport_Display'], y=subset['Aircraft_Count'], name=time_val))
fig.update_layout(barmode='group')
event = st.plotly_chart(fig, on_select="rerun")

# --- 6. MOST POPULAR ROUTES BY DATE ---
st.subheader("Most Popular Routes by Date")
route_data = df_filtered[df_filtered['Departure IATA'].notna() & df_filtered['Arrival IATA'].notna()]
route_pivot = route_data.pivot_table(index=['Departure IATA', 'Arrival IATA'], columns='Date', aggfunc='size', fill_value=0).astype(int)
route_pivot['Total'] = route_pivot.sum(axis=1)
st.table(route_pivot.sort_values(by='Total', ascending=False).head(10))