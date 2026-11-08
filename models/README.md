# CampusGuard model checkpoints

Model weights are intentionally not committed to this repository except the one detector below.

## Spontim 1.0 (the only detection model)
- File: `models/model_16_m3_0.8888.pth`
- Architecture: MC3-18 (FDSC fine-tuned)
- Classes: `fight`, `noFight`
- Fight class: 0
- Input: 16 RGB frames, 112x112
- Status: verified against the published FDSC inference contract

Person detection and pose use `models/yolo11n.pt` and `models/yolo11n-pose.pt`.
A missing model file is reported as **MISSING** and CampusGuard never reports fights without a loaded model.
