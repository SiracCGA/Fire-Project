from ultralytics import YOLO
import cv2
import time
import ai
import threading
import queue

class ai_runner:
    def __init__(self, output_queue):
        self.model = YOLO("best_ncnn_model/")
        self.config = {
            "confidence": 0.5,
            "imgsz": 320,
            "color": (0, 0, 255)
        }
        self.frame_skip = 1
        self.lock = threading.Lock()
        self.camera_source = 0
        self.output_queue = output_queue if output_queue is not None else queue.Queue(maxsize=2)
        self.ai_processor = ai.ai(self.config, self.frame_skip, self.model, self.lock)
        self.cap = None
        self.running = False
        self.thread = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()

    def start(self):
        self.cap = cv2.VideoCapture(self.camera_source)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.running = True
        self.cam_thread = threading.Thread(target=self._cam_reader, daemon=True)
        self.cam_thread.start()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _cam_reader(self):
        """Kamerayı son sürat okuyup buffer'ın şişmesini engelleyen mini döngü"""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                break
            with self.frame_lock:
                self.latest_frame = frame

    def _update(self):
        while self.running:
            with self.frame_lock:
                if self.latest_frame is None:
                    time.sleep(0.005)
                    continue
                # İşlenecek en taze kareyi al
                frame_to_process = self.latest_frame.copy()
            
            # AI modelini çalıştır
            processed_frame = self.ai_processor.ai(frame_to_process)
            
            if processed_frame is not None:
                if self.output_queue.full():
                    try:
                        self.output_queue.get_nowait()
                    except queue.Empty:
                        pass
                
                self.output_queue.put(processed_frame)
            
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        if self.cap:
            self.cap.release()