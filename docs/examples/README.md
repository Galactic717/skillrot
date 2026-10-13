# Reproducible library example

These controlled fixtures demonstrate a duplicate command and overly broad, repeated
descriptions. They are examples, not a sample of customer libraries or a measured
runtime experiment. The `after` fixture removes the duplicate and narrows descriptions
to each skill's purpose. Skillrot itself does not edit either library.

From the repository root, run both cases with the same assumptions:

```bash
python skillrot.py docs/examples/before --no-usage --context-window 8000 --budget-fraction 0.01 --json
python skillrot.py docs/examples/after --no-usage --context-window 8000 --budget-fraction 0.01 --json
```

The deliberately small 8,000-token example window produces an 80-token listing budget.
Real deployments should use their intended model window and loader settings. Counts
are character-ratio estimates. Predicted name-only entries remain invocable by name.

The release preparation includes corresponding JSON/text/SVG and SHA256 provenance
under `docs/runs/current-example/`; charts are also in `docs/assets/current-budget-*.svg`.
Generate the files again after changing the CLI or fixtures. Historical September
videos are retained separately and do not describe this version.
