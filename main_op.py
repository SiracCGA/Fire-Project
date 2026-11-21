from ultralytics import YOLO
from flask import Flask, Response
import cv2
import threading
import queue
import time
import os

os.environ["OMP_NUM_THREADS"] = "16"

class Main:
    def __init__(self, model, confidence, frame_skip, imgsz, device, camera, detect_lbl, detect_clr, fps_txt, fpstxt_clr):
        self.model = model
        self.confidence = confidence
        self.frame_skip = frame_skip
        self.imgsz = imgsz
        self.device = device
        self.camera = camera
        self.label = detect_lbl
        self.color = detect_clr
        self.fps_txt = fps_txt
        self.fpstxt_clr = fpstxt_clr

        if self.frame_skip < 1:
            raise ValueError("frame_skip en az 1 olmalı!")

        self.app = Flask(__name__)
        self.cap = None

        self.lock = threading.Lock()
        self.ai_thread = None
        self.cam_thread = None

        self.latest_frame = None
        self.running = False

        self.output_queue = queue.Queue(maxsize=2)

        self.fps = 0
        self.inference_time = 0
        self.start_t = time.perf_counter()

    def generate_frames(self):
        while self.running:
            try:
                frame = self.output_queue.get(timeout=0.05)
                
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    continue

                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    buffer.tobytes() +
                    b'\r\n'
                )
            except queue.Empty:
                continue

    def flask_routes(self):
        @self.app.route("/video")
        def index():
            return Response(self.generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame') 

    def start(self):
        self.cap = cv2.VideoCapture(self.camera)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        if not self.cap.isOpened():
            raise RuntimeError("Kamera Açılamadı!")

        self.running = True
        self.cam_thread = threading.Thread(target=self.cam_reader, daemon=True)
        self.ai_thread = threading.Thread(target=self.update, daemon=True)
        
        self.cam_thread.start()
        self.ai_thread.start()

        self.flask_routes()
        self.app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
            
    def stop(self):
        self.running = False
        if self.ai_thread:
            self.ai_thread.join()
        if self.cam_thread:
            self.cam_thread.join()
        if self.cap:
            self.cap.release()

    def cam_reader(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue
            with self.lock:
                self.latest_frame = frame

    def update(self):
        frame_counter = 0
        while self.running:
            with self.lock:
                if self.latest_frame is None:
                    continue
                frame_to_process = self.latest_frame.copy()

            # Frame skip kontrolü
            if frame_counter % self.frame_skip != 0:
                frame_counter += 1
                continue
            frame_counter += 1

            t0 = time.perf_counter()

            results = self.model.predict(
                frame_to_process,
                conf=self.confidence,
                verbose=False,
                imgsz=self.imgsz,
                device=self.device,
                stream=False
            )

            inference_time = time.perf_counter() - t0
            self.fps = 1 / inference_time if inference_time > 0 else 0

            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    cv2.rectangle(frame_to_process, (x1, y1), (x2, y2), self.color, 2)

                    text = f"{self.label} %{conf*100:.0f}"
                    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

                    cv2.rectangle(frame_to_process, (x1, y1-20), (x1+w, y1), self.color, -1)
                    cv2.putText(frame_to_process, text, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            if self.fps_txt:
                fps_text = f"FPS: {self.fps:.1f}"
                cv2.putText(frame_to_process, fps_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, self.fpstxt_clr, 2)

            if self.output_queue.full():
                try:
                    self.output_queue.get_nowait()
                except queue.Empty:
                    pass

            self.output_queue.put(frame_to_process)

if __name__ == "__main__":

    ####################Settings####################
    device = "cpu"
    confidence = 0.5
    frame_skip = 1
    imgsz = 320
    camera = 0
    box_color = (0,0,255)
    fps_color = (0,255,0)
    show_fps = True
    detect_label = "Fire"
    #################################################


    if device == "cuda":
        model = YOLO("models/best.pt")
        devic = "0"
    elif device == "cpu":
        model = YOLO("models/best_int8_openvino_model")
        devic = "cpu"
    elif device == "vulkan":
        model = YOLO("models/best_ncnn_model")
        devic = "vulkan:0"
    else:
        raise ValueError ("device: cuda, cpu, vulkan bunlardan biri olmalıdır!!")
    app = Main(
        model=model,
        confidence=confidence,
        frame_skip=frame_skip,
        imgsz=imgsz,
        device=devic,
        camera=camera,
        detect_lbl=detect_label,
        detect_clr=box_color,
        fps_txt=show_fps,
        fpstxt_clr=fps_color
    )

    try:
        app.start()
    except KeyboardInterrupt:
        print("\nProgram kapatılıyor...")
    finally:
        app.stop()
