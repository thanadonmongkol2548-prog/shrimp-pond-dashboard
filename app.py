import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import pandas as pd

# 1. ยืนยันตัวตน GEE บน Streamlit Cloud ด้วย Secrets
@st.cache_resource
def init_gee():
    try:
        # ดึงคีย์จาก Secrets
        service_account_info = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
        credentials = ee.ServiceAccountCredentials(
            service_account_info["client_email"],
            key_data=service_account_info
        )
        ee.Initialize(credentials, project=service_account_info["project_id"])
    except Exception as e:
        # รองรับกรณีรันในเครื่อง Local (ถ้าไม่มี secrets)
        try:
            ee.Initialize()
        except:
            st.error(f"เกิดข้อผิดพลาดในการเชื่อมต่อ GEE: {e}")

init_gee()

st.set_page_config(page_title="ระบบวิเคราะห์คุณภาพน้ำบ่อกุ้งดาวเทียม", layout="wide")

st.title("🦐 ระบบตรวจเช็คคุณภาพน้ำบ่อกุ้งด้วยดาวเทียม (Self-Service)")
st.write("📌 **วิธีใช้งาน:** เลื่อนแผนที่ไปที่ฟาร์มของคุณ ใช้เครื่องมือวาดสี่เหลี่ยม/โพลีกอน (รูปทรง) ครอบบ่อกุ้งของคุณ แล้วกด **'เริ่มวิเคราะห์คุณภาพน้ำ'**")

# 2. สร้างแผนที่ Interactive
m = folium.Map(location=[13.60, 100.90], zoom_start=13)
folium.TileLayer('https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', attr='Google', name='Satellite').add_to(m)

from folium.plugins import Draw
Draw(export=True, filename='my_pond.geojson').add_to(m)

map_data = st_folium(m, width=1200, height=500)

# 3. ปุ่มกดคำนวณ
if st.button("🚀 เริ่มวิเคราะห์คุณภาพน้ำบ่อนี้"):
    if map_data and map_data.get("all_drawings"):
        user_geometry = map_data["all_drawings"][0]["geometry"]
        coordinates = user_geometry["coordinates"]
        
        ee_pond = ee.Geometry.Polygon(coordinates)
        st.info("🔄 กำลังดึงภาพดาวเทียม Sentinel-2 และประมวลผลค่าน้ำเบื้องหลัง...")
        
        s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(ee_pond)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
              .sort('system:time_start', False))
        
        latest_img = s2.first()
        
        ndwi = latest_img.normalizedDifference(['B3', 'B8']).rename('NDWI')
        ndci = latest_img.normalizedDifference(['B5', 'B4']).rename('NDCI')
        ndti = latest_img.normalizedDifference(['B4', 'B3']).rename('NDTI')
        cdom = latest_img.select('B3').divide(latest_img.select('B1')).rename('CDOM')
        
        multi_band = latest_img.addBands([ndwi, ndci, ndti, cdom])
        
        stats = multi_band.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=ee_pond,
            scale=10
        ).getInfo()
        
        st.success("✅ ประมวลผลสำเร็จ!")
        
        col1, col2, col3 = st.columns(3)
        ndci_val = round(stats.get('NDCI', 0), 3) if stats.get('NDCI') else 0
        ndti_val = round(stats.get('NDTI', 0), 3) if stats.get('NDTI') else 0
        cdom_val = round(stats.get('CDOM', 0), 3) if stats.get('CDOM') else 0
        
        col1.metric("NDCI (คลอโรฟิลล์-เอ)", ndci_val)
        col2.metric("NDTI (ความขุ่น)", ndti_val)
        col3.metric("CDOM (สารอินทรีย์)", cdom_val)
        
        st.subheader("💡 การประเมินสถานะและคำแนะนำสำหรับบ่อนี้")
        if ndci_val < 0.15 and ndti_val > 0:
            st.error("🚨 **สถานะ: วิกฤต (เสี่ยงแพลงก์ตอนดรอป/น้ำล้ม)**\n\n**ข้อแนะนำ:** เปิดเครื่องตีน้ำตลอด 24 ชม. และสาดปูนขาวปรับสภาพน้ำด่วน!")
        elif cdom_val > 1.35:
            st.warning("⚠️ **สถานะ: เฝ้าระวัง (สารอินทรีย์สะสมสูง)**\n\n**ข้อแนะนำ:** เร่งดูดเลนกลางบ่อ และเติมจุลินทรีย์ย่อยสลาย")
        else:
            st.success("✅ **สถานะ: ปกติ (สมดุลน้ำดี)**\n\n**ข้อแนะนำ:** ควบคุมการให้อาหารตามตารางปกติ")
    else:
        st.warning("⚠️ กรุณาใช้นิ้ว/เมาส์วาดรูปทรงครอบบ่อกุ้งของคุณบนแผนที่ก่อนครับ")
