import streamlit as st
import pandas as pd
import glob
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import reverse_geocoder as rg

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Middle East Aviation Exposure Dashboard", layout="wide")
st.title("Middle East Aviation Exposure Dashboard (29th June - 13th July)")
st.subheader("Powered by Insurwave data (Timestamps are in UTC)")

AIRPORT_LOOKUP = {
    "BAH": "Bahrain International Airport", "CAI": "Cairo International Airport",
    "HBE": "Borg El Arab Airport", "SSH": "Sharm El Sheikh International Airport",
    "IKA": "Imam Khomeini International Airport", "BGW": "Baghdad International Airport",
    "TLV": "Ben Gurion Airport", "AMM": "Queen Alia International Airport",
    "AQJ": "Aqaba International Airport", "KWI": "Kuwait International Airport",
    "BEY": "Beirut-Rafic Hariri International Airport", "MCT": "Muscat International Airport",
    "DOH": "Hamad International Airport", "JED": "King Abdulaziz International Airport",
    "RUH": "King Khalid International Airport", "DMM": "Dammam International Airport",
    "DAM": "Damascus International Airport", "IST": "Istanbul Airport",
    "ESB": "Ankara Esenboğa International Airport", "AYT": "Antalya Airport",
    "AUH": "Abu Dhabi International Airport", "DXB": "Dubai International Airport",
    "SHJ": "Sharjah International Airport", "DWC": "Al Maktoum International Airport",
    "AAN": "Al Ain International Airport", "FJR": "Fujairah International Airport",
    "ADE": "Aden International Airport", "ISL": "Istanbul Atatürk Airport",
    "SAW": "Sabiha Gökçen International Airport", "BJV": "Milas-Bodrum Airport"
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
    
    # Ensure coordinates are numeric for geocoding
    df_master['Lat'] = pd.to_numeric(df_master['Lat'], errors='coerce')
    df_master['Long'] = pd.to_numeric(df_master['Long'], errors='coerce')
    df_master = df_master.dropna(subset=['Lat', 'Long'])
    
    # Geocoding using reverse_geocoder
    coords = list(zip(df_master['Lat'], df_master['Long']))
    results = rg.search(coords)
    df_master['Country'] = [res['cc'] for res in results]
    
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

# Fix: Convert to string to ensure sorting doesn't crash on mixed types
unique_airports = [str(x) for x in df_filtered['Airport_Display'].unique() if x != 'In Flight']
all_airports = sorted(unique_airports)

selected_airports = st.sidebar.multiselect("Select Airports", options=all_airports)

# Policy Filter: Also convert to string to be safe
all_policies = sorted([str(x) for x in df_filtered['Policy Name'].fillna('None').unique()])
policies = st.sidebar.multiselect("Select Policy Name", options=all_policies)

if selected_airports:
    df_filtered = df_filtered[df_filtered['Airport_Display'].astype(str).isin(selected_airports)]
if policies:
    df_filtered = df_filtered[df_filtered['Policy Name'].astype(str).isin(policies)]

# --- 4. EXPOSURE TREND ---
st.subheader("Exposure Trend Over Time")
trend_data = df_filtered.groupby('Snapshot Time').agg(
    Exposure=('Exposure', 'sum'),
    Aircraft_Count=('Name/Registration', 'count')
).reset_index()

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Scatter(x=trend_data['Snapshot Time'], y=trend_data['Exposure'], name="Total Exposure", line=dict(color='blue')), secondary_y=False)
fig.add_trace(go.Scatter(x=trend_data['Snapshot Time'], y=trend_data['Aircraft_Count'], name="Aircraft Count", line=dict(color='red')), secondary_y=True)

fig.update_layout(title="Total Exposure (all selected airports)")
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

pivot_df = grounded_day_df.groupby(['Airport_Display', 'Time of Day']).agg(
    Aircraft_Count=('Name/Registration', 'count'), Total_Exposure=('Exposure', 'sum')
).reset_index()

all_times = ['04:00', '12:00', '20:00']
index = pd.MultiIndex.from_product([top_15, all_times], names=['Airport_Display', 'Time of Day'])
pivot_df_filled = pivot_df.set_index(['Airport_Display', 'Time of Day']).reindex(index, fill_value=0).reset_index()

fig = go.Figure()
colors = {'04:00': 'lightblue', '12:00': 'purple', '20:00': 'green'}
for time_val in all_times:
    subset = pivot_df_filled[pivot_df_filled['Time of Day'] == time_val]
    fig.add_trace(go.Bar(
        x=subset['Airport_Display'], y=subset['Aircraft_Count'], name=time_val, 
        marker_color=colors[time_val],
        customdata=subset[['Airport_Display', 'Time of Day']]
    ))
fig.update_layout(barmode='group', xaxis_title="Airport", yaxis_title="Aircraft Count")
event = st.plotly_chart(fig, on_select="rerun")

# --- 6. BREAKDOWN ---
st.subheader("Breakdown")
if event and event['selection']['points']:
    selected_point = event['selection']['points'][0]
    sel_airport = selected_point['customdata'][0]
    sel_time = selected_point['customdata'][1]
    
    drill_df = grounded_day_df[(grounded_day_df['Airport_Display'] == sel_airport) & (grounded_day_df['Time of Day'] == sel_time)]
    if not drill_df.empty:
        display_df = drill_df.copy()
        display_df['Value_USD_M'] = display_df['Total Insured Value'] / 1_000_000
        
        st.write(f"### Policy Breakdown for {sel_airport} at {sel_time} (UTC)")
        policy_df = display_df.groupby('Policy Name').agg(
            Aircraft_Count=('Name/Registration', 'count'),
            Total_Value_USD_M=('Value_USD_M', 'sum'),
            Policy_Order_Pct=('Line Share %', 'mean')
        ).reset_index()
        
        total_row = pd.DataFrame({
            'Policy Name': ['TOTAL'],
            'Aircraft_Count': [policy_df['Aircraft_Count'].sum()],
            'Total_Value_USD_M': [policy_df['Total_Value_USD_M'].sum()],
            'Policy_Order_Pct': [None]
        })
        policy_df = pd.concat([policy_df, total_row], ignore_index=True)
        policy_df['Total_Value_USD_M'] = policy_df['Total_Value_USD_M'].map('{:.1f}'.format)
        st.dataframe(policy_df)

        st.write("### Aircraft Details")
        display_df['Value_USD_M'] = display_df['Value_USD_M'].map('{:.1f}'.format)
        cols_to_show = ['Name/Registration', 'Value_USD_M', 'Policy Name', 'Model', 'FlightNumber', 'Departure IATA', 'Arrival IATA']
        st.dataframe(display_df[cols_to_show])
    else:
        st.info("No data available for the selected combination.")
else:
    st.write("Click on a bar in the chart above to populate the Breakdown details.")

# --- 7. MOST POPULAR ROUTES BY DATE ---
st.subheader("Most Popular Routes by Date")
route_data = df_filtered[df_filtered['Departure IATA'].notna() & df_filtered['Arrival IATA'].notna()]
route_date_counts = route_data.groupby(['Departure IATA', 'Arrival IATA', 'Date']).size().reset_index(name='Flight_Count')

# Pivot the table
route_pivot = route_date_counts.pivot_table(
    index=['Departure IATA', 'Arrival IATA'], 
    columns='Date', 
    values='Flight_Count', 
    fill_value=0
)

# Convert to integer to remove decimal points
route_pivot = route_pivot.astype(int)

# Add a 'Total' column
route_pivot['Total'] = route_pivot.sum(axis=1)

# Sort and take top 10
route_pivot = route_pivot.sort_values(by='Total', ascending=False).head(10)

# Display as table (Format ensures no decimals are shown)
st.table(route_pivot)