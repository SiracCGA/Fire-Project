import cv2
import queue
from flask import Flask, Response

app = Flask(__name__)
_frame_queue = None

def init_flask(shared_queue):
    global _frame_queue
    _frame_queue = shared_queue

def generate_frames():
    while True:
        while True:
            if _frame_queue is None:
                continue
            try:
                frame = _frame_queue.get(timeout=0.05)
                
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ret:
                    continue
                    
                yield (b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            except queue.Empty:
                continue
@app.route('/video')
def index():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_flask(host='0.0.0.0', port=5000):
    app.run(host=host, port=port, threaded=True, use_reloader=False)