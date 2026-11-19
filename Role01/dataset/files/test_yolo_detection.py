from ultralytics import YOLO

# 사전 학습 모델 불러오기
model = YOLO("yolov8n.pt")

# 웹캠 영상 객체 탐지
results = model.predict(
    source=0,
    imgsz=640,
    conf=0.5,
    show=True
)