import threading
import cv2
from ultralytics import YOLO


model = YOLO("best_ncnn_model/")
cap = cv2.VideoCapture(0)
lock = threading.Lock()
frame_counter = 0
latest_frame = None
processed_frame = None
running = True

frame_skip = 0
confidence = 0.15
color_cfg = (255, 0, 0)


def ai():
    global frame_counter
    global processed_frame
    global lock

    while running:
        with lock:
          if latest_frame is None:
              continue
          frame = latest_frame.copy()
        
        if frame_skip == 0:
            results = model.predict(frame, conf=confidence, verbose=False, imgsz=640)
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    label = model.names[cls_id]

                    if conf >= confidence:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        color = color_cfg

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                        text = f"{label} %{conf*100:.0f}"
                        (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                        cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
                        cv2.putText(frame, text, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            with lock:
                processed_frame = frame.copy()

        frame_counter += 1

worker_th = threading.Thread(target=ai, daemon=True)
worker_th.start()

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    with lock:
      latest_frame = frame.copy()
      display_frame = processed_frame if processed_frame is not None else frame
    cv2.imshow("pnc", display_frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
      break
running = False
cap.release()
cv2.destroyAllWindows()