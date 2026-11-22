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
- **Spontim 1.0** (`models/model_16_m3_0.8888.pth`) was created by the CampusGuard owner starting from four open-source models, which were then removed from the repository. Work built from open-source models inherits their licences. The four models, their licences (MIT and Apache-2.0 allow commercial use; GPL/AGPL and "non-commercial" or "research only" licences may not) and the open datasets used for training must be listed here with a link to each licence. Status: names and licences not yet recorded.
- **Other models** (`yolo11n.pt`, `yolo11n-pose.pt`) are not in the repository and are not CampusGuard's. They are Ultralytics models under the AGPL point above.
