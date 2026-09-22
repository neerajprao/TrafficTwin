"""
Phase 1 - Count the Traffic.

Runs the geo-trax aerial vehicle detector (YOLOv8s trained on drone/top-down
footage: https://huggingface.co/rfonod/geo-trax) with tracking over the Astra
Biz Center junction video to detect and count vehicles per class (motorcycle,
car, bus, truck), and writes an annotated output video for visual
verification.
"""
from collections import defaultdict

import cv2
from huggingface_hub import hf_hub_download
from ultralytics import YOLO

VIDEO_PATH = "data/video/astra_biz_center.mp4"
OUTPUT_VIDEO = "detection/annotated_astra_biz_center.mp4"
MODEL_REPO = "rfonod/geo-trax"
MODEL_FILE = "geotrax_hbb_yolov8s_1920_v1.pt"
IMG_SIZE = 1920  # geo-trax model was trained/validated at this resolution

# geo-trax classes we care about for traffic counting (0=Car, 1=Bus,
# 2=Truck, 3=Motorcycle; classes 4/5 are Pedestrian/Bicycle, unused here).
VEHICLE_CLASSES = {
    "Car": "car",
    "Motorcycle": "motorcycle",
    "Bus": "bus",
    "Truck": "truck",
}

# Single-character label drawn on each box instead of "id class conf".
CLASS_CHAR = {
    "Car": "C",
    "Bus": "B",
    "Truck": "T",
    "Motorcycle": "M",
}
FONT_SCALE = 0.5
BOX_COLOR = (0, 255, 0)

if __name__ == "__main__":
    weights = hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILE)
    model = YOLO(weights)

    cap = cv2.VideoCapture(VIDEO_PATH)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    writer = cv2.VideoWriter(
        OUTPUT_VIDEO, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )

    seen_ids_per_class = defaultdict(set)
    frame_count = 0

    results = model.track(
        source=VIDEO_PATH,
        imgsz=IMG_SIZE,
        classes=[0, 1, 2, 3],  # Car, Bus, Truck, Motorcycle (geo-trax ids)
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        device="mps",
        save=False,
        verbose=False,
    )

    for r in results:
        frame_count += 1
        frame = r.orig_img
        if r.boxes is not None and r.boxes.id is not None:
            boxes = r.boxes.xyxy.cpu().numpy()
            ids = r.boxes.id.int().tolist()
            clss = r.boxes.cls.int().tolist()
            for (x1, y1, x2, y2), track_id, cls_id in zip(boxes, ids, clss):
                cls_name = model.names[cls_id]
                seen_ids_per_class[cls_name].add(track_id)
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, 1)
                cv2.putText(
                    frame,
                    CLASS_CHAR.get(cls_name, "?"),
                    (x1, max(y1 - 4, 0)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    FONT_SCALE,
                    BOX_COLOR,
                    1,
                    cv2.LINE_AA,
                )
        writer.write(frame)

        if frame_count % 300 == 0:
            print(f"...processed {frame_count} frames")

    writer.release()

    print(f"\nProcessed {frame_count} frames total.\n")
    print("Unique vehicle counts per class (by tracker ID):")
    total = 0
    for cls_name, ids in seen_ids_per_class.items():
        print(f"  {cls_name}: {len(ids)}")
        total += len(ids)
    print(f"  TOTAL: {total}")
