import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, timedelta

# --- 1. ตั้งค่าหน้าเว็บ & Custom CSS สไตล์โมเดิร์น ---
st.set_page_config(
    page_title="ShrimpSmart Pro - ระบบวิเคราะห์และวางแผนจัดการบ่อกุ้ง",
    page_icon="🦐",
    layout="wide"
)

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric {
        background-color: #ffffff;
        padding: 12px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
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
st.title("🦐 ShrimpSmart Pro: ระบบวิเคราะห์และวางแผนจัดการบ่อกุ้ง")
st.caption("ระบบประมวลผลดัชนีคุณภาพน้ำ (NDCI, NDTI, CDOM, NDWI) พร้อมตารางแผนการจัดการบ่อกุ้งรายวัน")

st.divider()

# --- Sidebar Controls ---
st.sidebar.header("⚙️ เลือกบ่อและช่วงเวลา")

PRESET_PONDS = {
    "บ่อที่ 1 (อ.บางปะกง)": [13.5821, 100.9543],
    "บ่อที่ 2 (อ.บางปะกง)": [13.5850, 100.9580],
    "บ่อที่ 3 (อ.บางปะกง)": [13.5790, 100.9510],
    "บ่อที่ 4 (อ.บ้านโพธิ์)": [13.6120, 101.0210],
    "บ่อที่ 5 (อ.บ้านโพธิ์)": [13.6150, 101.0250],
}

mode = st.sidebar.radio("โหมดการทำงาน", ["วาดบ่อเองบนแผนที่ (Multi-Draw)", "เลือกกลุ่มบ่อ Preset"])

selected_presets = []
if mode == "เลือกกลุ่มบ่อ Preset":
    selected_presets = st.sidebar.multiselect(
        "เลือกบ่อกุ้งที่ต้องการเปรียบเทียบ",
        list(PRESET_PONDS.keys()),
        default=["บ่อที่ 1 (อ.บางปะกง)", "บ่อที่ 2 (อ.บางปะกง)"]
    )

st.sidebar.subheader("📅 เลือกช่วงเวลาวิเคราะห์")
end_date = st.sidebar.date_input("วันที่สิ้นสุด", datetime.now())
start_date = st.sidebar.date_input("วันที่เริ่มต้น (สำหรับวิเคราะห์แนวโน้ม)", end_date - timedelta(days=60))

# --- Main Layout ---
col_map, col_info = st.columns([7, 5])

with col_map:
    st.subheader("🗺️ แผนที่ฟาร์มกุ้ง")
    m = folium.Map(location=[13.5821, 100.9543], zoom_start=14)
    folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Satellite').add_to(m)
    
    if mode == "เลือกกลุ่มบ่อ Preset" and selected_presets:
        for name in selected_presets:
            coord = PRESET_PONDS[name]
            folium.Marker(coord, popup=name, icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)

    from folium.plugins import Draw
    Draw(export=True, filename='my_ponds.geojson').add_to(m)
    
    map_data = st_folium(m, width=700, height=450, key="shrimp_map")

with col_info:
    st.subheader("📌 คำแนะนำการใช้งาน")
    if mode == "วาดบ่อเองบนแผนที่ (Multi-Draw)":
        st.info("ใช้อุปกรณ์วาดโพลีกอนบนแผนที่เพื่อเลือกพื้นที่บ่อกุ้ง สามารถวาดหลายบ่อพร้อมกันได้")
    else:
        st.info("เลือกรายชื่อบ่อกุ้งจากเมนูด้านซ้ายเพื่อทำการวิเคราะห์ตามพิกัดฟาร์ม")
    
    btn_analyze = st.button("🚀 ประมวลผลและสร้างแผนจัดการบ่อกุ้ง", use_container_width=True)

# --- Function สำหรับคำนวณค่าน้ำ 4 ดัชนี ---
def add_indices(img):
    ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')
    ndci = img.normalizedDifference(['B5', 'B4']).rename('NDCI')
    ndti = img.normalizedDifference(['B4', 'B3']).rename('NDTI')
    cdom = img.select('B3').divide(img.select('B1')).rename('CDOM')
    return img.addBands([ndwi, ndci, ndti, cdom])

# --- ฟังก์ชันให้คำแนะนำและสร้าง Action Plan ---
def generate_action_plan(ndci, ndti, cdom, ndwi):
    # กำหนดสถานะและข้อเสนอแนะ
    if ndci < 0.10 and ndti > 0.15:
        risk = "🔴 วิกฤต (แพลงก์ตอนดรอป/น้ำล้ม)"
        detail = "ความหนาแน่นแพลงก์ตอนพืชต่ำมาก ตะกอนดินสูง น้ำขาดความสมดุล เสี่ยงกุ้งน็อกออกซิเจน"
        aeration = "เปิดใบพัดตีน้ำเต็มกำลัง 24 ชม."
        feed = "ลดอาหารลง 30 - 50% ทันที"
        treatment = "สาดปูนขาว (CaCO3) 10-15 กก./ไร่ และเร่งทำสีน้ำเติมเชื้อแพลงก์ตอน"
    elif ndci > 0.40:
        risk = "🟡 เฝ้าระวัง (แพลงก์ตอนบลูม/น้ำเข้มจัด)"
        detail = "แพลงก์ตอนพืชหนาแน่นเกินไป เสี่ยงต่อค่า pH แกว่งสูงช่วงบ่าย และออกซิเจนดรอปช่วงดึก"
        aeration = "เปิดตีน้ำเพิ่มช่วงเวลา 22.00 - 06.00 น."
        feed = "ลดอาหารลง 10 - 20%"
        treatment = "ดักถ่ายน้ำชั้นบนออก หรือสาดจุลินทรีย์คุมแพลงก์ตอนช่วงเย็น"
    elif cdom > 1.35:
        risk = "🟡 เฝ้าระวัง (สารอินทรีย์สะสมสูง)"
        detail = "มีเศษอาหาร เลน หรือสารอินทรีย์ละลายน้ำสะสมสูง เสี่ยงต่อการเกิดก๊าซพิษแอมโมเนีย/ไนไตรต์"
        aeration = "เปิดตีน้ำเพื่อเพิ่มการหมุนเวียนของน้ำ"
        feed = "ควบคุมปริมาณอาหาร ห้ามให้อาหารเหลือ"
        treatment = "เร่งดูดเลนกลางบ่อ และสาดจุลินทรีย์ย่อยสลายเลนทุกๆ 3 วัน"
    elif ndti < -0.10 and ndci < 0.15:
        risk = "🟡 เฝ้าระวัง (น้ำใสเกินไป)"
        detail = "น้ำใส แสงแดดส่องถึงพื้นบ่อ เสี่ยงต่อการเกิดตะไคร่น้ำ/ขี้แดดพื้นบ่อ"
        aeration = "เปิดตีน้ำตามรอบปกติ"
        feed = "ให้อาหารตามปกติ"
        treatment = "เติมสีน้ำหรือจุลินทรีย์สังเคราะห์แสงเพื่อคุมความใสของน้ำ"
    else:
        risk = "🟢 ปกติ (สภาพน้ำสมดุลดี)"
        detail = "ค่าน้ำอยู่ในเกณฑ์เหมาะสม ทั้งระดับแพลงก์ตอน ความขุ่น และสารอินทรีย์"
        aeration = "เปิดตีน้ำตามรอบเวลาปกติ"
        feed = "ให้อาหารตามตารางคำนวณปกติ 100%"
        treatment = "รักษาสภาพน้ำ สาดจุลินทรีย์โปรไบโอติกตามรอบบำรุงรักษา"

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

    if mode == "วาดบ่อเองบนแผนที่ (Multi-Draw)":
        if map_data and map_data.get("all_drawings"):
            drawings = map_data["all_drawings"]
            for idx, draw in enumerate(drawings):
                coords = draw["geometry"]["coordinates"]
                geom = ee.Geometry.Polygon(coords)
                ponds_to_process.append({'name': f'บ่อที่วาด {idx + 1}', 'geometry': geom})
        else:
            st.warning("⚠️ ไม่พบรูปทรงที่วาดบนแผนที่ กรุณาวาดรูปทรงบ่อกุ้งก่อนครับ")
    else:
        if selected_presets:
            for name in selected_presets:
                coord = PRESET_PONDS[name]
                geom = ee.Geometry.Point([coord[1], coord[0]]).buffer(30)
                ponds_to_process.append({'name': name, 'geometry': geom})
        else:
            st.warning("⚠️ กรุณาเลือกบ่อกุ้งจากรายการด้านซ้าย")

    if ponds_to_process:
        with st.spinner(f"🔄 กำลังประมวลผลและสร้างแผนการจัดการสำหรับ {len(ponds_to_process)} บ่อ..."):
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
            st.subheader("📊 ตารางดัชนีคุณภาพน้ำจากดาวเทียมล่าสุด")
            df_summary = pd.DataFrame(summary_results)
            st.dataframe(df_summary, use_container_width=True)

            # --- 2. ตารางแผนการจัดการบ่อกุ้ง (Daily Action Plan Table) ---
            st.divider()
            st.subheader("📋 ตารางแผนการจัดการและคำแนะนำการดูแลบ่อกุ้ง (Farm Action Plan)")
            df_action = pd.DataFrame(action_plan_list)
            st.dataframe(df_action, use_container_width=True)

            # --- 3. กราฟ Time Series ---
            if time_series_all:
                st.divider()
                st.subheader("📈 เปรียบเทียบแนวโน้มย้อนหลังรายบ่อ")
                df_ts = pd.DataFrame(time_series_all)
                df_ts['Date'] = pd.to_datetime(df_ts['Date'])
                df_ts = df_ts.sort_values('Date')

                metric_choice = st.selectbox("เลือกดัชนีที่ต้องการดูแนวโน้ม", ["NDCI", "NDTI", "CDOM"])
                fig = px.line(df_ts, x='Date', y=metric_choice, color='ชื่อบ่อ', markers=True, title=f"แนวโน้มค่า {metric_choice} ย้อนหลัง")
                fig.update_layout(hovermode="x unified", template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

                # ปุ่มดาวน์โหลด
                csv = df_action.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 ดาวน์โหลดตารางแผนการจัดการบ่อกุ้ง (CSV)",
                    data=csv,
                    file_name='shrimp_farm_action_plan.csv',
                    mime='text/csv'
                )
