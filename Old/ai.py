import cv2
import time

class ai:
    def __init__(self, config, frame_skip, model, lock):
        self.frame_counter = 0
        self.frame_skip = frame_skip
        self.lock = lock

        self.yolo_counter = 0
        self.yolo_fps = 0
        self.start = time.perf_counter()

        self.processed_frame = None
        self.model = model
        self.config = config

    def ai(self, frame):
        current_frame = frame.copy()
        if self.frame_counter % self.frame_skip == 0:
            results = self.model.predict(frame, conf=self.config["confidence"], verbose=False, imgsz=self.config["imgsz"], device="vulkan:0")

            self.elasped_time = time.perf_counter() - self.start
            self.yolo_fps = 1 / self.elasped_time
            self.start = time.perf_counter()

            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    label = self.model.names[cls_id]

                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    color = self.config["color"]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    text = f"{label} %{conf*100:.0f}"
                    (w,h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
                    cv2.putText(frame, text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            fps_text = f"FPS: {self.yolo_fps:.1f}"
            cv2.putText(frame, fps_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            with self.lock:
                self.processed_frame = frame.copy()
        self.frame_counter += 1
        return self.processed_frame if self.processed_frame is not None else current_frame
