# Spectabular animation

## How to run

```
uv sync
uv run jupyter lab
```

(Under the Nix flake, entering the devShell already runs `uv sync` and
activates `.venv` for you.)

### Without uv (pip only)

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m jupyter lab
```

`requirements.txt` is exported from `uv.lock` (`uv export --format
requirements-txt`), so it stays in sync with the uv-managed dependency set.

## Contents

- **`anywidget/FormalVizWidget.ipynb`**: a generic, reusable `anywidget`
  for animating an SVG diagram whose visual state is driven by a formal
  (Spectabular) model.

- **`anywidget/elevator/Elevator.ipynb`**: an example built on
  `FormalVizWidget`: a 3-floor elevator rendered from an SVG, driven by the
  elevator's formal spec. It walks through button-press/arrival scenarios,
  animated transitions, and the widget's branching/forking history.

  The formal spec behind this example (state variables, events, invariants)
  lives in **`spec/ElevatorSpectabular.ipynb`**.

## Report

The main write-up, "Spectabular Visualization Report", is in
**`report/report.ipynb`** (rendered HTML: `report/report.html`). It surveys
visualization approaches for Spectabular models, including the
`anywidget`-based approach developed in this repo.
