from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from detection.temporal_model import TemporalFightModel
from config import TEMPORAL_MODEL
print('Loading:', TEMPORAL_MODEL)
m = TemporalFightModel(TEMPORAL_MODEL)
print('Temporal MC3 model loaded successfully on', m.device)
