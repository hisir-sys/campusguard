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
- **The current fight checkpoint, shown in the app as "Spontim 1.0"** (`models/model_16_m3_0.8888.pth`): the code's own model manifest (`campusguard/model_manifest.py`) and `scripts/download_verified_models.py` say this is the weights file published by MohamedSebaie in `Fight_Detection_From_Surveillance_Cameras-PyTorch_Project` (the file name is identical). That repository declares the MIT licence for its code, but states no terms for the weights file and names no training dataset. The owner has said the model was created from four open-source models; that is not recorded anywhere in the repository. **Until this is settled in writing, treat the checkpoint as someone else's work: do not sell it under the Spontim name, and plan to replace it with a model CampusGuard trains itself on data whose licence allows commercial use** (see `training/`).
- **Other models** (`yolo11n.pt`, `yolo11n-pose.pt`) are not in the repository and are not CampusGuard's. They are Ultralytics models under the AGPL point above.
