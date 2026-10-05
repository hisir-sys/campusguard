# CampusGuard violence-model checkpoints

Model weights are intentionally not committed to this repository.

## Operational models

### Current MC3-18
- File: `models/fight_mc3_18.pth`
- Architecture: MC3-18
- Classes: `fight`, `noFight`
- Fight class: 0
- Input: 16 RGB frames, 112x112
- Status: verified

### FDSC MC3-18
- File: `models/model_16_m3_0.8888.pth`
- Architecture: MC3-18
- Classes: `fight`, `noFight`
- Fight class: 0
- Input: 16 RGB frames, 112x112
- Status: verified against the published FDSC inference contract

### X3D-M
- File: `models/final_x3d_realtime.pt`
- Architecture: X3D-M
- Classes: `non-violent`, `violent`
- Fight class: 1
- Input: 16 RGB frames, 224x224
- Normalization: mean 0.45, std 0.225
- Status: verified against the published checkpoint contract

## Not yet operational

### FDSC R3D-18
- File: `models/fdsc_r3d_18.pth`
- Architecture: R3D-18
- Status: checkpoint/class semantics still require verification

### CampusGuard Enhanced
- Ensemble mode
- Status: technical issue — checkpoint unavailable
- The architecture and preprocessing contract are documented, but the original trained checkpoint is not currently available from the official FDSC repository/package.
- CampusGuard therefore does not treat this model as operational and does not allow it to be selected in Settings.

Missing optional model files are reported as **MISSING**, while documented-but-unavailable checkpoints are reported as **TECHNICAL ISSUE**. A checkpoint that loads but has unverified class semantics is **BLOCKED** and cannot produce violence decisions.
