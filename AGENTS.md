# Project guidance

- Read README.md and docs/DEVELOPMENT.md before significant changes.
- Source paths are read-only. Never silently modify, rename, delete, or synchronize comparison inputs.
- Keep numerical image comparison independent of 8-bit preview rendering and UI themes.
- Preserve original resolution, channel order, and bit depth in metrics. State normalization and SSIM conventions explicitly.
- Keep expensive filesystem/decoder/metric work off the UI thread and discard stale task results.
- Run `.venv/Scripts/python.exe -m unittest discover -s tests -v` for engine changes.
- Run `.venv/Scripts/python.exe tests/ui_smoke.py` for UI changes and inspect screenshots in validation/.
- Build with scripts/build.ps1 and smoke-test the built executable before delivering a Windows release.
- Do not add tests that merely duplicate implementation; prefer analytical values and observable user behavior.
