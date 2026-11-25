"""====Ayarlar:===="""
confidence = 0.5
frame_skip = 2
show_fps = True
camera = 0
"""================"""

import dashboard
from flask import Flask, Response
import cvai
import time
import logging
import queue
import threading
from ultralytics import YOLO

#model = YOLO("models/best_int8_openvino_model")
model = YOLO("models/best.pt")

app = Flask(__name__)
app.register_blueprint(dashboard.bp)
cvaim = cvai.Main(model, confidence, frame_skip, 320, "cuda", 0, "Fire", (0,0,255), show_fps, (255,0,0), (0,255,0), True)

@app.route("/video")
def video():
    return Response(cvaim.generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def komut_calistir(deger):
    if deger == "sa":
        return "as"

def dash_th():
    while cvaim.running:
        
        try:
            komut = dashboard.komut_kuyrugu.get_nowait()
        except queue.Empty:
            time.sleep(0.01)
            continue

        komut_id = komut["id"]

        try:
            sonuc = komut_calistir(komut["value"])
            dashboard.sonuclar[komut_id] = sonuc

        except Exception as e:
            dashboard.sonuclar[komut_id] = {
                "error": str(e)
            }
def detect_th():
    empty_count = 0
    radar_d = -1
    while cvaim.running:
        regions = cvaim.detected_regions

        if "LEFT" in regions and radar_d != 300:
            dashboard.durum["radar"] = [300]
            radar_d = 300
            empty_count = 0
            dashboard.algilama("Sol tarafta yangın var!")

        elif "CENTER" in regions and radar_d != 0:
            dashboard.durum["radar"] = [0]
            radar_d = 0
            empty_count = 0
            dashboard.algilama("Orta tarafta yangın var!")


        elif "RIGHT" in regions and radar_d != 60:
            dashboard.durum["radar"] = [60]
            radar_d = 60
            empty_count = 0
            dashboard.algilama("Sağ tarafta yangın var!")


        elif not regions:
            empty_count += 1

            if empty_count >= 3 and radar_d != -1:
                dashboard.durum["radar"] = []
                radar_d = -1

        else:
            empty_count = 0

        time.sleep(0.02)


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    dash_t = threading.Thread(target=dash_th, daemon=True)
    detect_t = threading.Thread(target=detect_th, daemon=True)
    try:
        cvaim.start()
        dash_t.start()
        detect_t.start()
        app.run(host="0.0.0.0", port=5000, threaded=True)
    except KeyboardInterrupt:
        cvaim.stop()
        dash_t.join()
