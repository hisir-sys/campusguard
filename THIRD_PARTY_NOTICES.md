# Third-party components

CampusGuard uses the open-source and third-party components below. Each stays under its own licence, which the CampusGuard Proprietary Licence does not change. Licence names are as I understand them and must be checked before any commercial release.

| Component | Used for | Licence (to verify) |
|---|---|---|
| PySide6 (Qt for Python) | Desktop interface | LGPL-3.0 (dynamic linking; keep the notice and allow replacement) |
| OpenCV (opencv-python) | Reading camera video | Apache-2.0 |
| NumPy | Numeric work | BSD-3-Clause |
| PyTorch, torchvision | Running the AI models | BSD-style |
| keyring | Windows credential vault | MIT |
| **Ultralytics YOLO** (`yolo11n.pt`, `yolo11n-pose.pt`) | Finding people and poses | **AGPL-3.0, or a paid Ultralytics Enterprise Licence** |

## Open items that need a decision before selling

- **Ultralytics YOLO is AGPL-3.0.** Shipping it inside a closed-source paid product needs the Ultralytics Enterprise Licence, or the product must be replaced with a permissively licensed detector. The CampusGuard Proprietary Licence cannot override AGPL for that component.
- **Spontim 1.0** (`models/model_16_m3_0.8888.pth`) is described as an MC3-18 model fine-tuned from the published FDSC work. The licence of that work, its pretrained weights and the training datasets must be confirmed. Many public fight datasets are research-only.
