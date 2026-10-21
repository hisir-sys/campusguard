# Anatomy skill integration — CampusGuard desktop

The project-level Anatomy skill is pinned as a Git submodule at `.agents/skills/anatomy`.

## Initialize after cloning

```powershell
git submodule update --init --recursive
```

The pinned upstream revision is `wheresryan22/anatomy@1482e8469b0a9e0d8cc18ea2740a01423d29ae80` (MIT). It requires Node.js 20.10+ and Chrome/Chromium for browser checks. Anatomy is a development-time authoring skill, not a runtime dependency of the PySide6 app.

## CampusGuard visual direction

Use Anatomy for optional, explanatory technical figures that make the real pipeline easier to understand:
- Keep the existing PySide6 application, workflows, settings, incident storage, camera workers, AI pipeline, and visual styling intact.
- Candidate visual: an interactive isometric pipeline explainer for local camera capture → person detection/tracking → pose estimation → 16-frame temporal classifier → thresholded incident/alert → human review.
- Clearly distinguish conceptual animation from live camera/model output. Do not fabricate detections, confidence values, incident states, or performance metrics.
- Keep visuals in a separate documentation/help view or standalone development artifact first. Do not put WebGL, browser rendering, or a new JavaScript runtime into the production desktop app unless separately designed and approved.
- Validate the existing Python test suite and app startup after any future integration; visual-only work must not change inference, alert thresholds, data storage, or camera lifecycle.
