import streamlit as st
import zipfile
import json
import io
import os
import shutil
import tempfile
import time
from PIL import Image
import piexif
from datetime import datetime

st.set_page_config(page_title="MementoSync", layout="centered")

# Hide Streamlit's default UI elements (Menu, Deploy button, Footer)
# hide_streamlit_style = """
# <style>
#     #MainMenu {visibility: hidden;}
#     footer {visibility: hidden;}
#     header {visibility: hidden;}
# </style>
# """
# st.markdown(hide_streamlit_style, unsafe_allow_html=True)


def cleanup_old_temp_files(max_age_seconds=3600):
    """Cleans up temp directories created by this app older than max_age_seconds."""
    temp_base = tempfile.gettempdir()
    # We look for folders starting with "mementosync_" to be safe,
    # but since we use standard mkdtemp, we might need a specific prefix pattern
    # or just rely on OS cleanup if we can't identify ours easily.
    # BETTER APPROACH: Use a dedicated subdirectory in temp for this app.
    
    app_temp_dir = os.path.join(temp_base, "mementosync_app_temp")
    if not os.path.exists(app_temp_dir):
        os.makedirs(app_temp_dir, exist_ok=True)
        return app_temp_dir
        
    now = time.time()
    for filename in os.listdir(app_temp_dir):
        file_path = os.path.join(app_temp_dir, filename)
        try:
            if os.path.getmtime(file_path) < now - max_age_seconds:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
        except Exception as e:
            print(f"Error cleaning up {file_path}: {e}")
            
    return app_temp_dir

# Initialize/Cleanup on run
APP_TEMP_DIR = cleanup_old_temp_files()

def get_exif_timestamp(timestamp_str):
    """Converts a timestamp string to EXIF format: 'YYYY:MM:DD HH:MM:SS'"""
    try:
        # Google Takeout timestamps can be simple numbers (unix timestamp) or strings
        ts = int(timestamp_str)
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None

def to_deg(value, loc):
    """Converts decimal coordinates to DMS (Degrees, Minutes, Seconds) for EXIF."""
    if value < 0:
        loc_value = loc[1]
    else:
        loc_value = loc[0]
    abs_value = abs(value)
    deg = int(abs_value)
    t1 = (abs_value - deg) * 60
    min = int(t1)
    sec = round((t1 - min) * 60 * 10000)
    return (deg, 1), (min, 1), (sec, 10000), loc_value

def set_gps_location(exif_dict, lat, lng, altitude=0.0):
    """Adds GPS data to the EXIF dictionary."""
    lat_deg = to_deg(lat, ["N", "S"])
    lng_deg = to_deg(lng, ["E", "W"])
    
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = lat_deg[3]
    exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_deg[0:3]
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = lng_deg[3]
    exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lng_deg[0:3]
    
    # Altitude (Byte 0 = Above Sea Level, 1 = Below)
    ref = 1 if altitude < 0 else 0
    exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = ref
    # Fraction for altitude
    alt_tuple = (int(abs(altitude) * 100), 100)
    exif_dict["GPS"][piexif.GPSIFD.GPSAltitude] = alt_tuple

def process_zip(uploaded_zip):
    # Check disk space
    # Heuristic: need at least 3x the size of the zip (input copy? + uncompressed one file + output zip building)
    # Actually, uploaded_zip is in memory/temp by Streamlit. We just need space for output zip.
    # Let's verify we have at least 2GB or 3x file size safe margin.
    total, used, free = shutil.disk_usage(APP_TEMP_DIR)
    
    input_size = uploaded_zip.size
    required_space = input_size * 2.5 # Safety factor
    
    if free < required_space:
        raise Exception(f"Insufficient disk space. Free: {free/1024**3:.2f}GB, Required approx: {required_space/1024**3:.2f}GB")

    # Create a unique temp folder for this process request
    # We use mkdtemp to avoid collisions
    process_dir = tempfile.mkdtemp(dir=APP_TEMP_DIR)
    output_zip_path = os.path.join(process_dir, "processed_photos.zip")

    try:
        # We process stream-to-stream where possible, but ZipFile needs random access for write usually requires a file-like object.
        # Streamlit uploaded_file is a BytesIO-like object.
        
        with zipfile.ZipFile(uploaded_zip, 'r') as z_in:
            all_files = z_in.namelist()
            
            # Map for JSONs
            json_map = {}
            for f in all_files:
                if f.lower().endswith('.json'):
                    json_map[f] = f 
            
            # Open output zip on DISK
            with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                image_files = [f for f in all_files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
                total_images = len(image_files)
                
                for idx, img_path in enumerate(image_files):
                    if idx % 10 == 0:
                        progress_bar.progress(int((idx / total_images) * 100))
                        status_text.text(f"Processing {idx + 1}/{total_images}: {os.path.basename(img_path)}")
                    
                    # Read image into RAM (one image is small enough)
                    img_data = z_in.read(img_path)
                    
                    # --- MATCHING LOGIC ---
                    possible_jsons = [
                        img_path + ".json", 
                        os.path.splitext(img_path)[0] + ".json",
                        img_path + ".supplemental-metadata.json",
                        os.path.splitext(img_path)[0] + ".supplemental-metadata.json"
                    ]
                    
                    matched_json = None
                    for pj in possible_jsons:
                        if pj in json_map:
                            matched_json = pj
                            break
                    
                    new_img_data = img_data
                    
                    if matched_json:
                        try:
                            # Read JSON
                            json_content = json.loads(z_in.read(matched_json).decode('utf-8'))
                            
                            photo_time = json_content.get('photoTakenTime', {}).get('timestamp')
                            geo_data = json_content.get('geoData', {})
                            lat = geo_data.get('latitude')
                            lng = geo_data.get('longitude')
                            alt = geo_data.get('altitude', 0.0)
                            
                            # --- EXIF MODIFICATION (PIL Method) ---
                            img = Image.open(io.BytesIO(img_data))
                            
                            if img.format == 'JPEG':
                                exif_dict = {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}, "thumbnail":None}
                                try:
                                    if "exif" in img.info:
                                        exif_dict = piexif.load(img.info["exif"])
                                except Exception:
                                    pass
                                    
                                if photo_time:
                                    exif_ts = get_exif_timestamp(photo_time)
                                    if exif_ts:
                                        exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_ts
                                        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_ts
                                        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_ts

                                if lat is not None and lng is not None:
                                    set_gps_location(exif_dict, lat, lng, alt)
                                
                                exif_bytes = piexif.dump(exif_dict)
                                
                                out_buffer = io.BytesIO()
                                img.save(out_buffer, format="JPEG", exif=exif_bytes, quality=95)
                                new_img_data = out_buffer.getvalue()
                                
                        except Exception as e:
                            print(f"Error processing {img_path}: {e}")
                    
                    # Write to output zip on DISK
                    z_out.writestr(img_path, new_img_data)
                    
                progress_bar.progress(100)
                status_text.text("Processing complete!")
    
    except Exception as e:
        # Cleanup if we fail during processing
        if os.path.exists(output_zip_path):
            os.unlink(output_zip_path)
        os.rmdir(process_dir) # Remove dir if empty or handle cleanup
        raise e

    return output_zip_path

st.title("📸 MementoSync")
st.markdown("""
Upload your **Google Takeout** zip file. 
This tool will read the accompanying `.json` files and inject `Date Taken` and `GPS` data back into your photos.
**Note:** Processing is done on-disk to handle large files.
""")

uploaded_file = st.file_uploader("Choose a zip file (Max 15GB)", type="zip")

if uploaded_file is not None:
    st.info("File uploaded. Click below to start processing.")
    if st.button("Process Photos"):
        with st.spinner("Processing..."):
            try:
                # Returns path to temporary file on disk
                processed_zip_path = process_zip(uploaded_file)
                
                st.success("Photos processed successfully!")
                
                original_name = uploaded_file.name
                output_filename = os.path.splitext(original_name)[0] + "_fixed.zip"
                
                # Open the file for reading to stream it to the user
                with open(processed_zip_path, "rb") as f:
                    st.download_button(
                        label="Download Fixed Zip",
                        data=f,
                        file_name=output_filename,
                        mime="application/zip"
                    )
                
                # Note: We cannot immediately delete the file here because download_button
                # might arguably need it or re-runs might complicate it.
                # However, since we open 'f' inside the context manager, 'data=f' reads it into memory?
                # Streamlit docs say: "If data is a file-like object, it is read from the current position to the end."
                # If the file is huge (2GB), reading it all into 'data' might spike RAM again?
                # Streamlit handles large files better if passed as a file path? No, file_name arg is just the download name.
                # If we pass a file object, Streamlit reads it.
                # Ideally, to save RAM for the DOWNLOAD itself, we should rely on Streamlit serving it.
                # But st.download_button implementation usually buffers.
                # If RAM is critical, we just ensured PROCESSING is low-RAM.
                # Configuring Streamlit Server options maxUploadSize covers upload.
                # Configuring download:
                # If the file is on disk, we rely on the periodic cleanup to remove it later.
                
            except Exception as e:
                st.error(f"An error occurred: {e}")
                import traceback
                st.error(traceback.format_exc())
