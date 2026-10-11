import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as io
import json
from datetime import datetime, timedelta

# --- 1. ตั้งค่าหน้าเว็บ & Custom CSS สไตล์โมเดิร์น ---
st.set_page_config(
    page_title="ShrimpSmart - ระบบตรวจเช็คคุณภาพน้ำบ่อกุ้งดาวเทียม",
    page_icon="🦐",
    layout="wide"
)

st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }
    .stButton>button {
        background-color: #007bff;
        color: white;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px 24px;
        border: none;
        box-shadow: 0 4px 6px rgba(0,123,255,0.2);
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #0056b3;
        transform: translateY(-2px);
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. ยืนยันตัวตน GEE ---
@st.cache_resource
def init_gee():
    try:
        service_account_info = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
        key_json_str = json.dumps(service_account_info)
        credentials = ee.ServiceAccountCredentials(
            service_account_info["client_email"],
            key_data=key_json_str
        )
        ee.Initialize(credentials)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ GEE: {e}")

init_gee()

# --- Header Zone ---
st.title("🦐 ShrimpSmart: ระบบติดตามคุณภาพน้ำบ่อกุ้งด้วยดาวเทียม")
st.caption("ระบบวิเคราะห์ NDCI, NDTI และ CDOM อัตโนมัติจากภาพดาวเทียม Sentinel-2 สำหรับฟาร์มกุ้ง")

st.divider()

# --- Sidebar Controls ---
st.sidebar.header("⚙️ ตั้งค่าและเลือกพื้นที่")

# Preset บ่อกุ้ง 5 บ่อ ฉะเชิงเทรา
PRESET_PONDS = {
    "กำหนดเอง/วาดบนแผนที่": None,
    "บ่อที่ 1 (อ.บางปะกง)": [13.5821, 100.9543],
    "บ่อที่ 2 (อ.บางปะกง)": [13.5850, 100.9580],
    "บ่อที่ 3 (อ.บางปะกง)": [13.5790, 100.9510],
    "บ่อที่ 4 (อ.บ้านโพธิ์)": [13.6120, 101.0210],
    "บ่อที่ 5 (อ.บ้านโพธิ์)": [13.6150, 101.0250],
}

selected_preset = st.sidebar.selectbox("🏢 เลือกบ่อกุ้งล่วงหน้า (Preset)", list(PRESET_PONDS.keys()))

if selected_preset != "กำหนดเอง/วาดบนแผนที่":
    default_lat, default_lon = PRESET_PONDS[selected_preset]
else:
    default_lat, default_lon = 13.5821, 100.9543

col_lat, col_lon = st.sidebar.columns(2)
lat_input = col_lat.number_input("ละติจูด", value=default_lat, format="%.6f")
lon_input = col_lon.number_input("ลองจิจูด", value=default_lon, format="%.6f")
zoom_input = st.sidebar.slider("ระดับ Zoom", 12, 18, 16)

st.sidebar.subheader("📅 เลือกช่วงเวลาวิเคราะห์")
end_date = st.sidebar.date_input("วันที่สิ้นสุด", datetime.now())
start_date = st.sidebar.date_input("วันที่เริ่มต้น (สำหรับวิเคราะห์แนวโน้ม)", end_date - timedelta(days=60))

# --- Main Layout ---
col_map, col_info = st.columns([7, 5])

with col_map:
    st.subheader("🗺️ แผนที่ฟาร์มกุ้ง")
    m = folium.Map(location=[lat_input, lon_input], zoom_start=zoom_input)
    
    # เพิ่ม Tile ดาวเทียมแบบชัดพิเศษ
    folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Satellite').add_to(m)
    
    # หมุดพิกัด
    folium.Marker([lat_input, lon_input], popup=f"ตำแหน่ง: {selected_preset}", icon=folium.Icon(color="red", icon="info-sign")).add_to(m)
    
    from folium.plugins import Draw
    Draw(export=True, filename='my_pond.geojson').add_to(m)
    
    map_data = st_folium(m, width=700, height=450, key="shrimp_map")

with col_info:
    st.subheader("📌 คำแนะนำการใช้งาน")
    st.info("""
    1. **เลือกบ่อกุ้ง:** เลือกจากรายการ Preset ด้านซ้าย หรือป้อนพิกัด
    2. **วาดรูปทรง:** ใช้เครื่องมือวาดสี่เหลี่ยม/โพลีกอนบนแผนที่เพื่อครอบบ่อ
    3. **เริ่มวิเคราะห์:** กดปุ่มด้านล่างเพื่อดึงค่าประมวลผลดาวเทียม
    """)
    
    btn_analyze = st.button("🚀 เริ่มวิเคราะห์คุณภาพน้ำบ่อนี้", use_container_width=True)

# --- Processing Zone ---
if btn_analyze:
    if map_data and map_data.get("all_drawings"):
        user_geometry = map_data["all_drawings"][0]["geometry"]
        coordinates = user_geometry["coordinates"]
        ee_pond = ee.Geometry.Polygon(coordinates)
    else:
        # หากไม่ได้วาด ให้สร้างบัฟเฟอร์ขนาดเล็ก 30 เมตรรอบพิกัด
        ee_pond = ee.Geometry.Point([lon_input, lat_input]).buffer(30)
        st.warning("⚠️ ไม่พบรูปทรงที่วาด ระบบจะคำนวณพื้นที่รัศมี 30 เมตรรอบจุดพิกัดแทน")

    with st.spinner("🔄 กำลังประมวลผลภาพดาวเทียม Sentinel-2 และคำนวณดัชนีคุณภาพน้ำ..."):
        # ดึง ImageCollection
        s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(ee_pond)
              .filterDate(start_date.strftime('%Y-%m-%d'), (end_date + timedelta(days=1)).strftime('%Y-%m-%d'))
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
              .sort('system:time_start', False))

        count = s2.size().getInfo()
        
        if count == 0:
            st.error("❌ ไม่พบภาพดาวเทียมที่ไม่มีเมฆในช่วงเวลาที่เลือก กรุณาขยายช่วงวันที่เริ่มต้นย้อนหลัง")
        else:
            # 1. คำนวณภาพล่าสุด
            latest_img = s2.first()
            date_str = ee.Date(latest_img.get('system:time_start')).format('YYYY-MM-dd').getInfo()
            
            def add_indices(img):
                ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')
                ndci = img.normalizedDifference(['B5', 'B4']).rename('NDCI')
                ndti = img.normalizedDifference(['B4', 'B3']).rename('NDTI')
                cdom = img.select('B3').divide(img.select('B1')).rename('CDOM')
                return img.addBands([ndwi, ndci, ndti, cdom])

            latest_calc = add_indices(latest_img)
            stats = latest_calc.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_pond,
                scale=10
            ).getInfo()

            ndci_val = round(stats.get('NDCI', 0), 3) if stats.get('NDCI') else 0
            ndti_val = round(stats.get('NDTI', 0), 3) if stats.get('NDTI') else 0
            cdom_val = round(stats.get('CDOM', 0), 3) if stats.get('CDOM') else 0

            st.divider()
            st.subheader(f"📊 ผลการวิเคราะห์ภาพถ่ายล่าสุด (วันที่ {date_str})")

            c1, c2, c3 = st.columns(3)
            c1.metric("NDCI (คลอโรฟิลล์-เอ)", ndci_val, delta="แพลงก์ตอน" if ndci_val > 0.2 else "ต่ำ")
            c2.metric("NDTI (ความขุ่น)", ndti_val, delta="ตะกอน" if ndti_val > 0.1 else "ใส")
            c3.metric("CDOM (สารอินทรีย์)", cdom_val, delta="สูง" if cdom_val > 1.3 else "ปกติ")

            # แสดงสถานะ
            st.subheader("💡 การประเมินสถานะและคำแนะนำ")
            if ndci_val < 0.15 and ndti_val > 0:
                st.error("🚨 **สถานะ: วิกฤต (เสี่ยงแพลงก์ตอนดรอป/น้ำล้ม)**\n\n**ข้อแนะนำ:** เปิดเครื่องตีน้ำตลอด 24 ชม. และสาดปูนขาวปรับสภาพน้ำด่วน!")
            elif cdom_val > 1.35:
                st.warning("⚠️ **สถานะ: เฝ้าระวัง (สารอินทรีย์สะสมสูง)**\n\n**ข้อแนะนำ:** เร่งดูดเลนกลางบ่อ และเติมจุลินทรีย์ย่อยสลาย")
            else:
                st.success("✅ **สถานะ: ปกติ (สมดุลน้ำดี)**\n\n**ข้อแนะนำ:** ควบคุมการให้อาหารตามตารางปกติ")

            # 2. คำนวณ Time Series ย้อนหลัง
            st.divider()
            st.subheader("📈 แนวโน้มคุณภาพน้ำย้อนหลัง (Time Series Trend)")
            
            s2_indexed = s2.map(add_indices)

            def extract_stats(img):
                date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
                mean_dict = img.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_pond,
                    scale=10
                )
                return ee.Feature(None, {
                    'date': date,
                    'NDCI': mean_dict.get('NDCI'),
                    'NDTI': mean_dict.get('NDTI'),
                    'CDOM': mean_dict.get('CDOM')
                })

            time_series_features = s2_indexed.map(extract_stats).getInfo()['features']
            
            data_list = []
            for f in time_series_features:
                props = f['properties']
                if props['NDCI'] is not None:
                    data_list.append({
                        'Date': props['date'],
                        'NDCI': round(props['NDCI'], 3),
                        'NDTI': round(props['NDTI'], 3),
                        'CDOM': round(props['CDOM'], 3)
                    })

            df = pd.DataFrame(data_list)
            if not df.empty:
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.sort_values('Date')

                # สร้างกราฟ Plotly
                fig = px.line(df, x='Date', y=['NDCI', 'NDTI', 'CDOM'],
                              markers=True,
                              labels={'value': 'ค่าดัชนี', 'variable': 'ดัชนีคุณภาพน้ำ'},
                              title="กราฟแสดงการเปลี่ยนแปลงคุณภาพน้ำย้อนหลัง")
                fig.update_layout(hovermode="x unified", template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

                # 3. ปุ่มส่งออกข้อมูล CSV
                st.subheader("📊 ส่งออกข้อมูลรายงาน")
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 ดาวน์โหลดรายงานค่าน้ำ (CSV)",
                    data=csv,
                    file_name=f'water_quality_report_{date_str}.csv',
                    mime='text/csv'
                )
