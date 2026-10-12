import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, timedelta

# --- 1. ตั้งค่าหน้าเว็บ & Custom CSS สไตล์คลีน สะอาดตา ---
st.set_page_config(
    page_title="ระบบวิเคราะห์คุณภาพน้ำบ่อกุ้งจากดาวเทียม",
    page_icon="🦐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS จัดแต่ง Layout และยืดแผนที่ให้เต็มพื้นที่
st.markdown("""
    <style>
    #MainMenu, footer, header {visibility: hidden !important;}
    
    /* ปรับแต่งพื้นที่หลักให้กว้างชิดขอบ */
    .main .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    
    /* สไตล์ปุ่มประมวลผลด้านซ้าย */
    .stButton>button {
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 12px 20px !important;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3) !important;
        transition: all 0.2s !important;
    }
    
    .stButton>button:hover {
        background-color: #4338ca !important;
        transform: translateY(-1px);
    }
    
    /* ปรับแต่งกล่อง Info คำแนะนำใน Sidebar */
    .sidebar-info-box {
        background-color: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 8px;
        padding: 14px;
        margin-top: 10px;
        margin-bottom: 15px;
    }
    .sidebar-info-box h4 {
        color: #1e40af;
        margin-top: 0;
        margin-bottom: 8px;
        font-size: 15px;
    }
    .sidebar-info-box ol {
        margin: 0;
        padding-left: 18px;
        color: #1e3a8a;
        font-size: 13px;
        line-height: 1.6;
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

# --- 3. Sidebar ด้านซ้าย (รวมคำแนะนำ + ปุ่มวิเคราะห์ไว้ที่เดียว) ---
with st.sidebar:
    st.title("⚙️ ตั้งค่าการค้นหาและเวลา")
    
    st.markdown("### 🏢 ตัวเลือกพิกัดเริ่มต้น")
    PRESET_PONDS = {
        "กำหนดเอง (พิมพ์พิกัด)": [13.5821, 100.9543],
        "บ่อที่ 1 (อ.บางปะกง)": [13.5821, 100.9543],
        "บ่อที่ 2 (อ.บางปะกง)": [13.5850, 100.9580],
        "บ่อที่ 3 (อ.บางปะกง)": [13.5790, 100.9510],
        "บ่อที่ 4 (อ.บ้านโพธิ์)": [13.6120, 101.0210],
        "บ่อที่ 5 (อ.บ้านโพธิ์)": [13.6150, 101.0250],
    }
    selected_preset = st.selectbox("เลือกตำแหน่งเริ่มต้น", list(PRESET_PONDS.keys()))
    default_lat, default_lon = PRESET_PONDS[selected_preset]

    st.markdown("### 📍 ระบุพิกัดค้นหาตำแหน่ง")
    col_lat, col_lon = st.columns(2)
    lat_input = col_lat.number_input("ละติจูด", value=default_lat, format="%.6f")
    lon_input = col_lon.number_input("ลองจิจูด", value=default_lon, format="%.6f")
    zoom_input = st.slider("ระดับ Zoom แผนที่", 12, 18, 16)

    st.markdown("### 📅 เลือกช่วงเวลาวิเคราะห์")
    today = datetime.now()
    min_date = datetime(2017, 1, 1)
    
    end_date = st.date_input("วันที่สิ้นสุด", value=today, min_value=min_date, max_value=today)
    start_date = st.date_input("วันที่เริ่มต้น (ดูแนวโน้ม)", value=end_date - timedelta(days=60), min_value=min_date, max_value=today)

    st.markdown("---")
    
    # 📌 คำแนะนำการใช้งาน (ย้ายมาฝั่งซ้าย)
    st.markdown("""
        <div class="sidebar-info-box">
            <h4>📌 ขั้นตอนการใช้งาน</h4>
            <ol>
                <li><b>ค้นหาตำแหน่ง:</b> ป้อนพิกัด แถบซ้ายมือ แผนที่จะย้ายไปตำแหน่งนั้น</li>
                <li><b>วาดหลายๆ บ่อ:</b> ใช้เครื่องมือวาดสี่เหลี่ยม/โพลีกอน บนแผนที่ <b>วาดล้อมรอบบ่อกุ้งหลายๆ บ่อได้เลย</b> (บ่อ 1, บ่อ 2, บ่อ 3 ฯลฯ)</li>
                <li><b>เริ่มวิเคราะห์:</b> กดปุ่มด้านล่างเพื่อประมวลผลค่าน้ำทุกบ่อพร้อมกัน</li>
            </ol>
        </div>
    """, unsafe_allow_html=True)
    
    # 🚀 ปุ่มประมวลผล (ย้ายมาฝั่งซ้าย)
    btn_analyze = st.button("🚀 ประมวลผลและสร้างแผนจัดการบ่อกุ้งทุกบ่อ", use_container_width=True)

# --- 4. พื้นที่แผนที่ขวามือ (ขยายเต็มจอใหญ่สะใจ) ---
st.subheader("🗺️ แผนที่ฟาร์มกุ้ง (ใช้วาดหลายบ่อ)")
st.caption("ป้อนพิกัดฟาร์ม วาดรูปทรงบ่อกุ้งหลายๆ บ่อ แล้วประมวลผลดัชนีค่าน้ำอัตโนมัติจากภาพดาวเทียม Sentinel-2")

m = folium.Map(location=[lat_input, lon_input], zoom_start=zoom_input, tiles=None, control_scale=True)

# ภาพดาวเทียมรายละเอียดสูง Google Satellite
folium.TileLayer(
    tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    attr='Google Satellite',
    name='Google Satellite',
    overlay=False,
    control=True
).add_to(m)

# ภาพดาวเทียมพร้อมชื่อสถานที่/ถนน Google Hybrid
folium.TileLayer(
    tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attr='Google Hybrid',
    name='Google Satellite Hybrid',
    overlay=False,
    control=True
).add_to(m)

folium.LayerControl().add_to(m)

# หมุดพิกัดค้นหา
folium.Marker(
    [lat_input, lon_input],
    popup=f"พิกัดค้นหา: {lat_input}, {lon_input}",
    icon=folium.Icon(color="red", icon="info-sign")
).add_to(m)

# เครื่องมือวาดบ่อกุ้ง
from folium.plugins import Draw
Draw(
    export=True,
    filename='my_shrimp_ponds.geojson',
    position='topleft',
    draw_options={'polyline': False, 'circle': False, 'marker': False, 'circlemarker': False}
).add_to(m)

# แสดงแผนที่เต็มความกว้าง และเพิ่มความสูงเป็น 850px เต็มหน้าจอ
map_data = st_folium(m, width="100%", height=850, key="shrimp_map")

# --- 5. ฟังก์ชันคำนวณ & Action Plan ---
def add_indices(img):
    ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')
    ndci = img.normalizedDifference(['B5', 'B4']).rename('NDCI')
    ndti = img.normalizedDifference(['B4', 'B3']).rename('NDTI')
    cdom = img.select('B3').divide(img.select('B1')).rename('CDOM')
    return img.addBands([ndwi, ndci, ndti, cdom])

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

# --- 6. ส่วนประมวลผลเมื่อกดปุ่มวิเคราะห์ ---
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

                    # Time Series Extract
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

            # --- แสดงผลตารางและกราฟด้านล่างแผนที่ ---
            st.divider()
            st.subheader("📊 ตารางสรุปดัชนีคุณภาพน้ำจากดาวเทียมล่าสุด (เทียบทุกบ่อ)")
            df_summary = pd.DataFrame(summary_results)
            st.dataframe(df_summary, use_container_width=True)

            st.divider()
            st.subheader("📋 ตารางแผนการจัดการและคำแนะนำการดูแลบ่อกุ้ง (Daily Action Plan)")
            df_action = pd.DataFrame(action_plan_list)
            st.dataframe(df_action, use_container_width=True)

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

                csv = df_action.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 ดาวน์โหลดตารางแผนการจัดการบ่อกุ้งทุกบ่อ (CSV)",
                    data=csv,
                    file_name='shrimp_farm_action_plan.csv',
                    mime='text/csv'
                )
