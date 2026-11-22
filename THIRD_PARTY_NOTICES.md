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
- **Spontim 1.0** (`models/model_16_m3_0.8888.pth`) was trained entirely by the CampusGuard owner, so its weights are CampusGuard's own. Two things still need a written answer, because they decide what you can say to a school: (1) the licence of every dataset it was trained or fine-tuned on (your own footage is fine; many public fight datasets are research-only), and (2) whether training started from pretrained weights, such as the Kinetics-pretrained MC3-18 that ships with torchvision, and under what licence those come.
- **Other models** (`yolo11n.pt`, `yolo11n-pose.pt`) are not in the repository and are not CampusGuard's. They are Ultralytics models under the AGPL point above.
