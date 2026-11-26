# Charts

`experiment-design.png` / `.svg` describe planned work; they contain no measured performance.

Run `python notes/generate_report.py` from the project directory to regenerate these and any measured retrieval, model, or training charts. Result charts appear only when the corresponding CSV logs contain valid completed runs or actual training steps. The generated `reports/summary.md` links the current chart set.

PNG is for quick viewing; SVG is for editing/export. Keep published figures together with their CSV inputs and frozen run reports. Old cohort charts are retained; an old file's presence does not mean it belongs to the latest report.
