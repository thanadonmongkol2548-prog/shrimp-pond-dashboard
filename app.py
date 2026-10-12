import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, timedelta

# --- 1. ตั้งค่าหน้าเว็บ & Custom CSS สไตล์ Copernicus Dark Navy Theme ---
st.set_page_config(
    page_title="ShrimpSmart Browser - ระบบวิเคราะห์คุณภาพน้ำบ่อกุ้ง",
    page_icon="🦐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS ตกแต่งให้คล้าย Copernicus Browser (Sidebar น้ำเงินเข้ม #182b49)
st.markdown("""
    <style>
    /* ซ่อน Header และ Footer เปล่าของ Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* พื้นหลังส่วนหลัก */
    .stApp {
        background-color: #f4f6f9;
    }
    
    /* ตกแต่ง Sidebar สไตล์ Copernicus (Dark Navy Blue) */
    [data-testid="stSidebar"] {
        background-color: #182b49 !important;
    }
    
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    
    /* ปรับแต่งปุ่มกดหลัก */
    .stButton>button {
        background-color: #7da100 !important; /* สีเขียวสไตล์ Copernicus button */
        color: #ffffff !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border-radius: 4px !important;
        border: none !important;
        padding: 12px 20px !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2) !important;
        transition: all 0.2s !important;
    }
    
    .stButton>button:hover {
        background-color: #8cb500 !important;
        transform: translateY(-1px);
    }
    
    /* ตกแต่งกล่อง Metric สรุปผล */
    [data-testid="stMetricValue"] {
        font-size: 24px !important;
        font-weight: bold !important;
        color: #182b49 !important;
    }
    
    /* ปรับปรุงหัวข้อ */
    .copernicus-header {
        background-color: #182b49;
        color: white;
        padding: 15px 25px;
        border-radius: 6px;
        margin-bottom: 20px;
        box-shadow: 0 3px 6px rgba(0,0,0,0.1);
    }
    .copernicus-header h2 {
        margin: 0;
        color: #ffffff;
        font-weight: 600;
    }
    .copernicus-header p {
        margin: 5px 0 0 0;
        color: #b0c4de;
        font-size: 14px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. ยืนยันตัวตน GEE ---
@st.cache_resource
def init_gee():
    try:
        service_account_info = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
        project_id = service_account_info.get("project_id", "shrimp-water-quality")
        key_json_str = json.dumps(service_account_info)
        
        credentials = ee.ServiceAccountCredentials(
            service_account_info["client_email"],
            key_data=key_json_str
        )
        ee.Initialize(credentials, project=project_id, opt_url='https://earthengine.googleapis.com')
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ GEE: {e}")

init_gee()

# --- Top Banner Header ---
st.markdown("""
    <div class="copernicus-header">
        <h2>🦐 ShrimpSmart Browser | ระบบวิเคราะห์คุณภาพน้ำบ่อกุ้งจากดาวเทียม</h2>
        <p>เครื่องมือตรวจเช็คดัชนี NDCI, NDTI, CDOM, NDWI รายบ่อ พร้อมตารางแผนการจัดการฟาร์มประจำวัน</p>
    </div>
""", unsafe_allow_html=True)

# --- Sidebar Controls (Copernicus Style) ---
st.sidebar.markdown("### ⚙️ ค้นหาพิกัด & ตัวเลือกบ่อ")

PRESET_PONDS = {
    "กำหนดเอง (พิมพ์พิกัด)": [13.5821, 100.9543],
    "บ่อที่ 1 (อ.บางปะกง)": [13.5821, 100.9543],
    "บ่อที่ 2 (อ.บางปะกง)": [13.5850, 100.9580],
    "บ่อที่ 3 (อ.บางปะกง)": [13.5790, 100.9510],
    "บ่อที่ 4 (อ.บ้านโพธิ์)": [13.6120, 101.0210],
    "บ่อที่ 5 (อ.บ้านโพธิ์)": [13.6150, 101.0250],
}

selected_preset = st.sidebar.selectbox("🏢 พิกัดเริ่มต้นประจำบ่อ", list(PRESET_PONDS.keys()))
default_lat, default_lon = PRESET_PONDS[selected_preset]

st.sidebar.markdown("---")
st.sidebar.markdown("### 📍 ค้นหาตำแหน่งระบุพิกัด")
col_lat, col_lon = st.sidebar.columns(2)
lat_input = col_lat.number_input("ละติจูด (Lat)", value=default_lat, format="%.6f")
lon_input = col_lon.number_input("ลองจิจูด (Lon)", value=default_lon, format="%.6f")
zoom_input = st.sidebar.slider("ระดับ Zoom แผนที่", 12, 18, 16)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 ช่วงเวลาข้อมูลดาวเทียม")
end_date = st.sidebar.date_input("วันที่สิ้นสุด", datetime.now())
start_date = st.sidebar.date_input("วันที่เริ่มต้น (ดูแนวโน้ม)", end_date - timedelta(days=60))

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛰️ ชุดข้อมูลดาวเทียม")
st.sidebar.info("• Satellite: Sentinel-2 L2A\n• Resolution: 10m\n• Refresh Rate: 3-5 วัน")

# --- Main Layout ---
col_map, col_info = st.columns([7, 5])

with col_map:
    st.subheader("🗺️ แผนที่สำรวจผิวน้ำ (วาดโพลีกอนหลายบ่อได้ที่นี่)")
    m = folium.Map(location=[lat_input, lon_input], zoom_start=zoom_input)
    folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google Satellite', name='Google Satellite').add_to(m)
    folium.TileLayer('openstreetmap', name='OpenStreetMap').add_to(m)
    folium.LayerControl().add_to(m)
    
    # หมุดชี้ตำแหน่งพิกัดค้นหา
    folium.Marker([lat_input, lon_input], popup="ตำแหน่งพิกัดค้นหา", icon=folium.Icon(color="red", icon="info-sign")).add_to(m)

    from folium.plugins import Draw
    Draw(
        export=True,
        filename='my_shrimp_ponds.geojson',
        position='topleft',
        draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False}
    ).add_to(m)
    
    map_data = st_folium(m, width=720, height=480, key="shrimp_map")

with col_info:
    st.subheader("📌 คำแนะนำการใช้งานระบบ")
    st.info("""
    1. **ค้นหาตำแหน่ง:** ใส่พิกัด ละติจูด/ลองจิจูด ในเมนูด้านซ้าย เพื่อซูมไปยังฟาร์ม
    2. **วาดรูปทรงบ่อ:** ใช้เครื่องมือวาดสี่เหลี่ยม/โพลีกอน **วาดล้อมรอบบ่อกุ้งกี่บ่อก็ได้พร้อมกัน** (บ่อ 1, บ่อ 2, บ่อ 3 ฯลฯ)
    3. **ประมวลผล:** กดปุ่ม **'วิเคราะห์คุณภาพน้ำทุกบ่อ'** ด้านล่าง
    """)
    
    btn_analyze = st.button("🚀 วิเคราะห์คุณภาพน้ำทุกบ่อพร้อมกัน", use_container_width=True)

# --- Function สำหรับคำนวณค่าน้ำ 4 ดัชนี ---
def add_indices(img):
    ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')
    ndci = img.normalizedDifference(['B5', 'B4']).rename('NDCI')
    ndti = img.normalizedDifference(['B4', 'B3']).rename('NDTI')
    cdom = img.select('B3').divide(img.select('B1')).rename('CDOM')
    return img.addBands([ndwi, ndci, ndti, cdom])

# --- ฟังก์ชันสร้าง Action Plan คำแนะนำรายบ่อ ---
def generate_action_plan(ndci, ndti, cdom, ndwi):
    if ndci < 0.10 and ndti > 0.15:
        risk = "🔴 วิกฤต (แพลงก์ตอนดรอป/น้ำล้ม)"
        detail = "ความหนาแน่นแพลงก์ตอนต่ำ ตะกอนสูง น้ำเสี่ยงขาดออกซิเจน"
        aeration = "เปิดใบพัดตีน้ำเต็มกำลัง 24 ชม."
        feed = "ลดอาหารลง 30 - 50% ทันที"
        treatment = "สาดปูนขาว (CaCO3) 10-15 กก./ไร่ และเร่งทำสีน้ำ"
    elif ndci > 0.40:
        risk = "🟡 เฝ้าระวัง (แพลงก์ตอนบลูม/น้ำเข้มจัด)"
        detail = "แพลงก์ตอนพืชหนาแน่นเกินไป เสี่ยง pH แกว่งสูงช่วงบ่าย"
        aeration = "เปิดตีน้ำเพิ่มช่วงเวลา 22.00 - 06.00 น."
        feed = "ลดอาหารลง 10 - 20%"
        treatment = "ดักถ่ายน้ำชั้นบนออก หรือสาดจุลินทรีย์คุมแพลงก์ตอน"
    elif cdom > 1.35:
        risk = "🟡 เฝ้าระวัง (สารอินทรีย์สะสมสูง)"
        detail = "มีเศษอาหาร/เลนกลางบ่อสะสมสูง เสี่ยงก๊าซพิษแอมโมเนีย"
        aeration = "เปิดตีน้ำหมุนเวียนน้ำตลอดวัน"
        feed = "ควบคุมปริมาณอาหาร ห้ามให้อาหารเหลือ"
        treatment = "เร่งดูดเลนกลางบ่อ และสาดจุลินทรีย์ย่อยสลายเลน"
    elif ndti < -0.10 and ndci < 0.15:
        risk = "🟡 เฝ้าระวัง (น้ำใสเกินไป)"
        detail = "น้ำใส แสงแดดส่องถึงพื้นบ่อ เสี่ยงตะไคร่น้ำขึ้นพื้นบ่อ"
        aeration = "เปิดตีน้ำตามรอบปกติ"
        feed = "ให้อาหารตามปกติ"
        treatment = "เติมสีน้ำหรือจุลินทรีย์สังเคราะห์แสง"
    else:
        risk = "🟢 ปกติ (สภาพน้ำสมดุลดี)"
        detail = "ค่าน้ำอยู่ในเกณฑ์เหมาะสม ทั้งระดับแพลงก์ตอนและความขุ่น"
        aeration = "เปิดตีน้ำตามรอบเวลาปกติ"
        feed = "ให้อาหารตามตารางปกติ 100%"
        treatment = "รักษาสภาพน้ำ สาดจุลินทรีย์โปรไบโอติกตามรอบ"

    return {
        'Risk': risk,
        'Detail': detail,
        'Aeration': aeration,
        'Feed': feed,
        'Treatment': treatment
    }

# --- Processing Zone ---
if btn_analyze:
    ponds_to_process = []

    if map_data and map_data.get("all_drawings"):
        drawings = map_data["all_drawings"]
        for idx, draw in enumerate(drawings):
            coords = draw["geometry"]["coordinates"]
            geom = ee.Geometry.Polygon(coords)
            ponds_to_process.append({'name': f'บ่อที่วาด {idx + 1}', 'geometry': geom})
    else:
        geom = ee.Geometry.Point([lon_input, lat_input]).buffer(30)
        ponds_to_process.append({'name': 'บ่อตามพิกัดค้นหา', 'geometry': geom})
        st.warning("⚠️ ไม่พบรูปทรงที่วาดบนแผนที่ ระบบจะวัดพื้นที่รัศมี 30 เมตรรอบจุดพิกัดค้นหาแทน")

    if ponds_to_process:
        with st.spinner(f"🔄 กำลังประมวลผลดาวเทียม Sentinel-2 สำหรับทั้งหมด {len(ponds_to_process)} บ่อ..."):
            summary_results = []
            action_plan_list = []
            time_series_all = []

            for pond in ponds_to_process:
                pond_name = pond['name']
                ee_pond = pond['geometry']

                s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(ee_pond)
                      .filterDate(start_date.strftime('%Y-%m-%d'), (end_date + timedelta(days=1)).strftime('%Y-%m-%d'))
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                      .sort('system:time_start', False))

                if s2.size().getInfo() > 0:
                    latest_img = s2.first()
                    date_str = ee.Date(latest_img.get('system:time_start')).format('YYYY-MM-dd').getInfo()
                    latest_calc = add_indices(latest_img)
                    
                    stats = latest_calc.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=ee_pond,
                        scale=10
                    ).getInfo()

                    ndci_val = round(stats.get('NDCI', 0), 3) if stats.get('NDCI') else 0
                    ndti_val = round(stats.get('NDTI', 0), 3) if stats.get('NDTI') else 0
                    cdom_val = round(stats.get('CDOM', 0), 3) if stats.get('CDOM') else 0
                    ndwi_val = round(stats.get('NDWI', 0), 3) if stats.get('NDWI') else 0

                    plan = generate_action_plan(ndci_val, ndti_val, cdom_val, ndwi_val)

                    summary_results.append({
                        'ชื่อบ่อ': pond_name,
                        'วันที่ภาพถ่าย': date_str,
                        'NDCI (คลอโรฟิลล์)': ndci_val,
                        'NDTI (ความขุ่น)': ndti_val,
                        'CDOM (สารอินทรีย์)': cdom_val,
                        'NDWI (ดัชนีน้ำ)': ndwi_val,
                        'ระดับความเสี่ยง': plan['Risk']
                    })

                    action_plan_list.append({
                        'ชื่อบ่อ': pond_name,
                        'ระดับความเสี่ยง': plan['Risk'],
                        'การจัดการใบพัดตีน้ำ': plan['Aeration'],
                        'การปรับแผนให้อาหาร': plan['Feed'],
                        'การปรับสภาพน้ำและเคมี/จุลินทรีย์': plan['Treatment'],
                        'รายละเอียดวิเคราะห์': plan['Detail']
                    })

                    # Time Series
                    s2_indexed = s2.map(add_indices)
                    def extract_stats(img):
                        d = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
                        m_dict = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=ee_pond, scale=10)
                        return ee.Feature(None, {'date': d, 'NDCI': m_dict.get('NDCI'), 'NDTI': m_dict.get('NDTI'), 'CDOM': m_dict.get('CDOM')})

                    ts_features = s2_indexed.map(extract_stats).getInfo()['features']
                    for f in ts_features:
                        p = f['properties']
                        if p['NDCI'] is not None:
                            time_series_all.append({
                                'ชื่อบ่อ': pond_name,
                                'Date': p['date'],
                                'NDCI': round(p['NDCI'], 3),
                                'NDTI': round(p['NDTI'], 3),
                                'CDOM': round(p['CDOM'], 3)
                            })

            # --- 1. ตารางสรุปค่าน้ำดัชนี ---
            st.divider()
            st.subheader("📊 ตารางสรุปดัชนีคุณภาพน้ำจากดาวเทียมล่าสุด (เทียบทุกบ่อ)")
            df_summary = pd.DataFrame(summary_results)
            st.dataframe(df_summary, use_container_width=True)

            # --- 2. ตารางแผนการจัดการบ่อกุ้ง (Daily Action Plan Table) ---
            st.divider()
            st.subheader("📋 ตารางแผนการจัดการและคำแนะนำการดูแลบ่อกุ้ง (Action Plan)")
            df_action = pd.DataFrame(action_plan_list)
            st.dataframe(df_action, use_container_width=True)

            # --- 3. กราฟ Time Series เปรียบเทียบ ---
            if time_series_all:
                st.divider()
                st.subheader("📈 เปรียบเทียบแนวโน้มย้อนหลังรายบ่อ")
                df_ts = pd.DataFrame(time_series_all)
                df_ts['Date'] = pd.to_datetime(df_ts['Date'])
                df_ts = df_ts.sort_values('Date')

                metric_choice = st.selectbox("เลือกดัชนีที่ต้องการดูแนวโน้มเปรียบเทียบ", ["NDCI", "NDTI", "CDOM"])
                fig = px.line(df_ts, x='Date', y=metric_choice, color='ชื่อบ่อ', markers=True, title=f"แนวโน้มค่า {metric_choice} ย้อนหลังเปรียบเทียบรายบ่อ")
                fig.update_layout(hovermode="x unified", template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

                # ปุ่มดาวน์โหลด
                csv = df_action.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 ดาวน์โหลดตารางแผนการจัดการบ่อกุ้งทุกบ่อ (CSV)",
                    data=csv,
                    file_name='shrimp_farm_action_plan.csv',
                    mime='text/csv'
                )
