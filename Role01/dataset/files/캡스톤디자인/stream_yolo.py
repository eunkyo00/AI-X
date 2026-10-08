import cv2
from ultralytics import YOLO
from flask import Flask, Response

app = Flask(__name__)
model = YOLO('/home/team-d/obstacle_detection/best_incomplete_ncnn_model', task='detect')

def generate_frames():
    cap = cv2.VideoCapture(0)
    
    while True:
        success, frame = cap.read()
        if not success: break

        results = model.predict(
            source=frame, 
            imgsz=320, 
            conf=0.5,      # 신뢰도 50%
            iou=0.45,       # 이 값을 조절하면 겹치는 박스가 사라짐
            verbose=False,
            stream=False
        )

        annotated_frame = results[0].plot() 
        
        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

@app.route('/')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
