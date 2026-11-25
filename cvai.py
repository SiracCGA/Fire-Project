from ultralytics import YOLO
import cv2
import threading
import queue
import time
import os

os.environ["OMP_NUM_THREADS"] = "16"

class Main:
    def __init__(self, model, confidence, frame_skip, imgsz, device, camera, detect_lbl, detect_clr, fps_txt, fpstxt_clr, area_clr, area_line):
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

        self.detected_regions = []
        self.detection_lock = threading.Lock()

        self.area_clr = area_clr
        self.area_line = area_line

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

            detected_regions = set()
            frame_width = frame_to_process.shape[1]
            region_1 = frame_width // 3
            region_2 = (frame_width * 2) // 3

            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    center_x = (x1 + x2) // 2

                    if center_x < region_1:
                        detected_regions.add("LEFT")

                    elif center_x < region_2:
                        detected_regions.add("CENTER")

                    else:
                        detected_regions.add("RIGHT")

                    cv2.rectangle(frame_to_process, (x1, y1), (x2, y2), self.color, 2)

                    text = f"{self.label} %{conf*100:.0f}"
                    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

                    cv2.rectangle(frame_to_process, (x1, y1-20), (x1+w, y1), self.color, -1)
                    cv2.putText(frame_to_process, text, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            if self.area_line:
                # Bölge çizgileri
                h, w = frame_to_process.shape[:2]

                cv2.line(frame_to_process, (region_1, 0), (region_1, h), self.area_clr, 2)
                cv2.line(frame_to_process, (region_2, 0), (region_2, h), self.area_clr, 2)

                # Bölge isimleri
                cv2.putText(frame_to_process, "LEFT", (20, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.area_clr, 2)

                cv2.putText(frame_to_process, "CENTER", (region_1 + 10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.area_clr, 2)

                cv2.putText(frame_to_process, "RIGHT", (region_2 + 10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.area_clr, 2)

                # Algılanan bölgeleri kaydet
                with self.detection_lock:
                    self.detected_regions = sorted(detected_regions)
            
            if self.fps_txt:
                fps_text = f"FPS: {self.fps:.1f}"
                cv2.putText(frame_to_process, fps_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, self.fpstxt_clr, 2)

            if self.output_queue.full():
                try:
                    self.output_queue.get_nowait()
                except queue.Empty:
                    pass

            self.output_queue.put(frame_to_process)
