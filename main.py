from ultralytics import YOLO
from flask import Flask, Response
import cv2
import threading
import time

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
        self.processed_frame = None
        self.processed_jpeg = None

        self.frame_id = 0
        self.processed_frame_id = -1
        self.jpeg_id = 0

        self.running = False

        self.fps = 0
        self.inference_time = 0
        self.start_t = time.perf_counter()


    def generate_frames(self):
        last_id = -1

        while self.running:
            with self.lock:
                jpeg = self.processed_jpeg
                jpeg_id = self.jpeg_id

            if jpeg is None or jpeg_id == last_id:
                time.sleep(0.001)
                continue

            last_id = jpeg_id

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                jpeg +
                b'\r\n'
            )

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
                time.sleep(0.01)
                continue
            with self.lock:
                self.latest_frame = frame
                self.frame_id += 1

    def update(self):
        while self.running:

            with self.lock:
                if self.latest_frame is None:
                    frame_to_process = None

                elif self.frame_id == self.processed_frame_id:
                    frame_to_process = None

                elif self.frame_id % self.frame_skip != 0:
                    self.processed_frame_id = self.frame_id
                    frame_to_process = None

                else:
                    frame_to_process = self.latest_frame.copy()
                    self.processed_frame_id = self.frame_id

            if frame_to_process is None:
                time.sleep(0.001)
                continue

            t0 = time.perf_counter()

            results = self.model.predict(
                frame_to_process,
                conf=self.confidence,
                verbose=False,
                imgsz=self.imgsz,
                device=self.device
            )

            if not hasattr(self, "backend_checked"):
                print("Model backend:", self.model.predictor.model.__class__.__name__)
                print("Device:", self.model.predictor.device)
                self.backend_checked = True

            self.inference_time = time.perf_counter() - t0
            self.fps = 1 / self.inference_time if self.inference_time > 0 else 0

            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    cv2.rectangle(
                        frame_to_process,
                        (x1, y1),
                        (x2, y2),
                        self.color,
                        2
                    )

                    text = f"{self.label} %{conf*100:.0f}"

                    (w, h), _ = cv2.getTextSize(
                        text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                    )

                    cv2.rectangle(
                        frame_to_process,
                        (x1, y1-20),
                        (x1+w, y1),
                        self.color,
                        -1
                    )

                    cv2.putText(
                        frame_to_process,
                        text,
                        (x1, y1-5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1
                    )

            if self.fps_txt:
                fps_text = f"FPS: {self.fps:.1f}"

                cv2.putText(
                    frame_to_process,
                    fps_text,
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    self.fpstxt_clr,
                    2
                )

            ret, buffer = cv2.imencode(
                '.jpg',
                frame_to_process,
                [cv2.IMWRITE_JPEG_QUALITY, 80]
            )

            if ret:
                with self.lock:
                    self.processed_frame = frame_to_process.copy()
                    self.processed_jpeg = buffer.tobytes()
                    self.jpeg_id += 1

if __name__ == "__main__":
    model = YOLO("best.pt")

    app = Main(
        model=model,
        confidence=0.5,
        frame_skip=1,
        imgsz=320,
        device="0",
        camera=0,
        detect_lbl="Fire",
        detect_clr=(255, 0, 0),
        fps_txt=True,
        fpstxt_clr=(0, 255, 0)
    )

    try:
        app.start()
    except KeyboardInterrupt:
        print("\nProgram kapatılıyor...")
    finally:
        app.stop()