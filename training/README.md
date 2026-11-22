# Training the fight model

`fightkit.py` trains CampusGuard's own fight model (MC3-18, 16 frames at 15 fps, 112x112) from your videos and writes a file the app loads directly. `train_fight_model.ipynb` runs it on Google Colab's free GPU.

Why: the current checkpoint is someone else's published file, and it raises false alarms on calm classroom footage. A model trained on footage like the school's own cameras, with plenty of "nothing happening" video, fixes both.

## Footage you need

| Folder | What | Roughly |
|---|---|---|
| `fight/` | staged fights (actors, adults), real incidents you may use | 60+ clips, 5-30 s each, varied places and cameras |
| `nofight/` | classrooms, corridors, stairs, playground, canteen, sport, running, hugging, play-shoving, crowds | the more the better; at least 3-4 hours, from many cameras |
| `check/` | 30+ minutes of calm footage from the real school, kept out of training | for the false-alarm test |

Hard negatives (play-fighting, sport, crowds running) matter most. Use a different camera or room for check footage than for training, or the test is too easy. Only use footage you have the right to use; for children, get the school's written permission and keep faces out of anything public.

## Using the result

Copy `fight_model.pth` to `models/` (or point Settings to it). It is a plain torchvision `mc3_18` state dict with two classes and fight as class 0, which is what the app expects. Measure it with `python scripts/score_video.py calm.mp4 --calm --model models/fight_model.pth`.

Training starts from torchvision's Kinetics-400 pretrained MC3-18. Check that weight licence before selling (see THIRD_PARTY_NOTICES.md); `--no-pretrained` trains from scratch but needs far more footage.
