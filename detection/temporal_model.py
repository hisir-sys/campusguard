"""MC3-18 temporal fight classifier using the supplied checkpoint."""
from pathlib import Path
import torch
import torchvision


class TemporalFightModel:
    def __init__(self, checkpoint: Path, device=None):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model = torchvision.models.video.mc3_18(weights=None)
        self.model.fc = torch.nn.Linear(self.model.fc.in_features, 2)
        state = torch.load(checkpoint, map_location=self.device)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device).eval()

    @torch.inference_mode()
    def predict(self, clip):
        x = torch.from_numpy(clip).to(self.device)
        logits = self.model(x)
        probs = torch.softmax(logits, dim=1)[0]
        fight = float(probs[0].item())
        no_fight = float(probs[1].item())
        label = "fight" if fight >= no_fight else "noFight"
        return {"label": label, "fight_probability": fight, "no_fight_probability": no_fight}
