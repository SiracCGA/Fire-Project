import cv2
from ai_runner import ai_runner
from flask_worker import init_flask, run_flask
import queue

if __name__ == "__main__":
    frame_queue = queue.Queue(maxsize=2)
    runner = ai_runner(frame_queue)
    runner.start()
    init_flask(frame_queue)
    try:
        run_flask(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        runner.stop()