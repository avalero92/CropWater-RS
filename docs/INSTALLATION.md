# Installation

## pip

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python cropwater_rs.py
```

## Conda

```bash
conda env create -f environment.yml
conda activate cropwater-rs
python cropwater_rs.py
```

A clean Python 3.12 environment is recommended for the public release. Tkinter is normally bundled with official Windows Python installers. CDSE access requires user-owned OAuth credentials.
