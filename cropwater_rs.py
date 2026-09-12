
import os
import sys
import threading
import time
import json
import logging
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import date

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from matplotlib.cm import ScalarMappable, get_cmap
from matplotlib.colors import BoundaryNorm
from matplotlib.patches import Patch
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

try:
    from scipy.signal import savgol_filter
    from scipy.sparse import diags, eye
    from scipy.sparse.linalg import spsolve
    SCIPY_AVAILABLE = True
except Exception:
    SCIPY_AVAILABLE = False

from sentinelhub import (
    SHConfig,
    DataCollection,
    Geometry,
    CRS,
    SentinelHubStatistical,
    SentinelHubStatisticalDownloadClient,
)


APP_VERSION = "1.0.0"
APP_TITLE = f"CropWater-RS v{APP_VERSION} — Remote Sensing · Phenology · Irrigation"

CROPS = [
    "BARLEY",
    "WHEAT",
    "MAIZE",
    "PEA",
    "SUNFLOWER",
    "SOYBEAN",
    "ALFALFA",
    "COTTON",
    "RICE",
    "POTATO",
    "OTHER",
]

# Common aliases accepted when an input vector contains a crop column.
# The original source value is retained in ``crop_source`` for provenance,
# while ``crop`` is normalized to the controlled vocabulary used by the app.
CROP_ALIASES = {
    "BARLEY": "BARLEY",
    "CEBADA": "BARLEY",
    "WHEAT": "WHEAT",
    "TRIGO": "WHEAT",
    "TRIGO BLANDO": "WHEAT",
    "TRIGO DURO": "WHEAT",
    "MAIZE": "MAIZE",
    "CORN": "MAIZE",
    "MAIZ": "MAIZE",
    "MAÍZ": "MAIZE",
    "PEA": "PEA",
    "PEAS": "PEA",
    "GUISANTE": "PEA",
    "GUISANTES": "PEA",
    "SUNFLOWER": "SUNFLOWER",
    "GIRASOL": "SUNFLOWER",
    "SOYBEAN": "SOYBEAN",
    "SOY": "SOYBEAN",
    "SOJA": "SOYBEAN",
    "ALFALFA": "ALFALFA",
    "COTTON": "COTTON",
    "ALGODON": "COTTON",
    "ALGODÓN": "COTTON",
    "RICE": "RICE",
    "ARROZ": "RICE",
    "POTATO": "POTATO",
    "POTATOES": "POTATO",
    "PATATA": "POTATO",
    "PATATAS": "POTATO",
    "OTHER": "OTHER",
    "OTRO": "OTHER",
    "OTROS": "OTHER",
}


# ---------------------------------------------------------------------
# Curated pilot catalogue: DIRECT Kc-NDVI relationships only.
# Crop-specific equations are offered together with a general model.
# Kcb relationships are intentionally excluded.
# ---------------------------------------------------------------------
KC_CATALOG = {
    "kamble_2013_general": {
        "label": "Kamble et al. (2013) — General",
        "crops": ["ALL"],
        "equation": "Kc = 1.457 × NDVI - 0.1725",
        "a": 1.457,
        "b": -0.1725,
        "reference": "Kamble, Kilic & Hubbard (2013), Remote Sensing 5:1588–1602",
        "doi": "10.3390/rs5041588",
        "scope": "General agricultural relationship; MODIS/AmeriFlux, Nebraska, USA",
    },
    "gontia_tiwari_2010_wheat": {
        "label": "Gontia & Tiwari (2010) — Wheat",
        "crops": ["WHEAT"],
        "equation": "Kc = 2.7109 × NDVI + 0.424",
        "a": 2.7109,
        "b": 0.424,
        "reference": "Gontia & Tiwari (2010), Water Resources Management 24:1399–1414",
        "doi": "10.1007/s11269-009-9505-3",
        "scope": "Wheat; IRS-P6; India; KcFAO relationship",
    },
    "rocha_2012_maize": {
        "label": "Rocha et al. (2012) — Maize",
        "crops": ["MAIZE"],
        "equation": "Kc = 1.37 × NDVI - 0.017",
        "a": 1.37,
        "b": -0.017,
        "reference": "Rocha et al. (2012) — maize relationship reported in later scientific syntheses",
        "doi": "",
        "scope": "Maize; Portugal",
    },
    "singh_irmak_2009_soybean": {
        "label": "Singh & Irmak (2009) — Soybean",
        "crops": ["SOYBEAN"],
        "equation": "Kc = 1.217 × NDVI - 0.034",
        "a": 1.217,
        "b": -0.034,
        "reference": "Singh & Irmak (2009) — soybean relationship",
        "doi": "",
        "scope": "Soybean; USA",
    },
    "reyes_2015_alfalfa": {
        "label": "Reyes-González et al. (2015) — Alfalfa",
        "crops": ["ALFALFA"],
        "equation": "Kc = 2.112 × NDVI - 0.4989",
        "a": 2.112,
        "b": -0.4989,
        "reference": "Reyes-González et al. (2015) — alfalfa relationship",
        "doi": "",
        "scope": "Alfalfa; Mexico",
    },
    "rossi_2010_rice": {
        "label": "Rossi et al. (2010) — Rice",
        "crops": ["RICE"],
        "equation": "Kc = 0.206 × NDVI + 1.076",
        "a": 0.206,
        "b": 1.076,
        "reference": "Rossi et al. (2010) — rice relationship reported in later scientific syntheses",
        "doi": "",
        "scope": "Rice; MODIS",
    },
}


# Common metadata schema for direct Kc-NDVI relationships.
# Calibration ranges remain blank until verified against each primary paper.
for _kc_meta in KC_CATALOG.values():
    _kc_meta.setdefault("kc_type", "Kc")
    _kc_meta.setdefault("sensor", "Not specified")
    _kc_meta.setdefault("study_region", _kc_meta.get("scope", "Not specified"))
    _kc_meta.setdefault("r2", None)
    _kc_meta.setdefault("ndvi_min", None)
    _kc_meta.setdefault("ndvi_max", None)
    _kc_meta.setdefault("kc_min", None)
    _kc_meta.setdefault("kc_max", None)
    _kc_meta.setdefault(
        "calibration_note",
        "Calibration domain not encoded yet; verify against the primary publication."
    )
    _kc_meta.setdefault("source_type", "built-in")
    _kc_meta.setdefault("verification_status", "not specified")


CDSE_BASE_URL = "https://sh.dataspace.copernicus.eu"
CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

# Sentinel-2 L2A NDVI with an SCL-based valid-pixel mask.
# Excluded SCL classes:
# 0 = NO_DATA
# 1 = SATURATED/DEFECTIVE
# 3 = CLOUD_SHADOW
# 8 = CLOUD_MEDIUM_PROBABILITY
# 9 = CLOUD_HIGH_PROBABILITY
# 10 = THIN_CIRRUS
# 11 = SNOW/ICE
NDVI_EVALSCRIPT = r"""
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B08", "SCL", "dataMask"]
    }],
    output: [
      {
        id: "ndvi",
        bands: 1,
        sampleType: "FLOAT32"
      },
      {
        id: "dataMask",
        bands: 1
      }
    ]
  };
}

function evaluatePixel(sample) {
  let invalidSCL = [0, 1, 3, 8, 9, 10, 11].includes(sample.SCL);
  let valid = sample.dataMask === 1 && !invalidSCL;

  if (!valid) {
    return {
      ndvi: [NaN],
      dataMask: [0]
    };
  }

  let den = sample.B08 + sample.B04;
  let ndvi = den === 0 ? NaN : (sample.B08 - sample.B04) / den;

  return {
    ndvi: [ndvi],
    dataMask: [1]
  };
}
"""


def calculate_linear_kc(ndvi, a, b, constrain_nonnegative=True):
    """Direct literature relationship Kc = a*NDVI + b."""
    values = np.asarray(ndvi, dtype=float) * float(a) + float(b)
    if constrain_nonnegative:
        values = np.maximum(values, 0.0)
    return values


def calculate_etc(kc, eto):
    """Crop evapotranspiration / CWR in mm d-1."""
    return np.asarray(kc, dtype=float) * np.asarray(eto, dtype=float)


def calculate_net_iwr(etc, pe):
    """Simplified daily net IWR = max(ETc - Pe, 0), in mm d-1."""
    return np.maximum(
        np.asarray(etc, dtype=float) - np.asarray(pe, dtype=float),
        0.0,
    )




class CropWaterRSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1440x900")
        self.minsize(1180, 760)

        self.gdf = None
        self.source_gdf = None
        self.ndvi_results = {}
        self.temporal_results = {}
        self.config_cdse = None
        self.current_file = None

        # Phase 2 state
        self.kc_assignments = {}
        self.kc_results = {}
        self.meteo_df = None
        self.water_results = {}
        self.meteo_file = None
        self.temporal_quality = {}
        self.run_metadata = {}

        # Independent QUANT phenology module
        self.quant_results = {}
        self.quant_water_summary = {}

        self.base_dir = Path(__file__).resolve().parent
        self.assets_dir = self.base_dir / "assets"
        self.kc_library_path = self.base_dir / "kc_ndvi_library.json"
        self.software_metadata_path = self.base_dir / "software_metadata.json"
        self.software_metadata = self._load_software_metadata()

        # Official CropWater-RS visual identity.
        self.header_logo_image = None
        self.about_logo_image = None
        self.app_icon_image = None
        self._load_brand_assets()

        self.log_dir = Path.home() / ".cropwater_rs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / "cropwater_rs.log"
        self._setup_logging()
        self._load_kc_library()

        self._build_style()
        self._build_menu()
        self._build_ui()
        logging.info("CropWater-RS %s started", APP_VERSION)

    def _load_brand_assets(self):
        """Load official CropWater-RS logo assets without making them mandatory."""
        try:
            header_path = self.assets_dir / "cropwater_rs_emblem_92.png"
            about_path = self.assets_dir / "cropwater_rs_logo.png"
            icon_path = self.assets_dir / "cropwater_rs_icon_64.png"

            if header_path.exists():
                self.header_logo_image = tk.PhotoImage(file=str(header_path))

            if about_path.exists():
                self.about_logo_image = tk.PhotoImage(file=str(about_path))

            if icon_path.exists():
                self.app_icon_image = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self.app_icon_image)

            # On Windows, prefer the multi-resolution .ico when available.
            ico_path = self.assets_dir / "cropwater_rs.ico"
            if sys.platform.startswith("win") and ico_path.exists():
                try:
                    self.iconbitmap(default=str(ico_path))
                except Exception:
                    pass
        except Exception as exc:
            # Branding must never prevent the scientific application from starting.
            self.header_logo_image = None
            self.about_logo_image = None
            self.app_icon_image = None
            try:
                logging.warning("Could not load CropWater-RS brand assets: %s", exc)
            except Exception:
                pass

    def _setup_logging(self):
        logging.basicConfig(
            filename=self.log_path,
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            force=True,
        )

    def report_callback_exception(self, exc, val, tb):
        logging.error(
            "Unhandled GUI exception:\n%s",
            "".join(traceback.format_exception(exc, val, tb)),
        )
        messagebox.showerror(
            "Unexpected error",
            "An unexpected error occurred.\n\n"
            f"Technical details were written to:\n{self.log_path}",
        )

    def _load_software_metadata(self):
        defaults = {
            "software_name": "CropWater-RS",
            "version": APP_VERSION,
            "author": "Alexey Valero-Jorge",
            "affiliation": "Configure in software_metadata.json",
            "email": "Configure in software_metadata.json",
            "orcid": "Configure in software_metadata.json",
            "repository_url": "",
            "zenodo_doi": "",
            "license": "GPL-3.0",
            "preferred_citation": (
                f"Valero-Jorge, A. ({date.today().year}). CropWater-RS "
                f"(Version {APP_VERSION}) [Computer software]."
            ),
        }
        try:
            if self.software_metadata_path.exists():
                loaded = json.loads(
                    self.software_metadata_path.read_text(encoding="utf-8")
                )
                defaults.update(loaded)
        except Exception as exc:
            logging.warning("Could not read software metadata: %s", exc)
        return defaults

    def _load_kc_library(self):
        global KC_CATALOG
        if not self.kc_library_path.exists():
            logging.info("External Kc library not found; built-in catalogue used.")
            return
        try:
            loaded = json.loads(
                self.kc_library_path.read_text(encoding="utf-8")
            )
            if not isinstance(loaded, dict) or not loaded:
                raise ValueError("Kc library must be a non-empty JSON object.")

            cleaned = {}
            for model_id, m in loaded.items():
                required = ["label", "crops", "a", "b", "reference"]
                missing = [x for x in required if x not in m]
                if missing:
                    raise ValueError(
                        f"{model_id}: missing required field(s): "
                        + ", ".join(missing)
                    )
                m = dict(m)
                m["a"] = float(m["a"])
                m["b"] = float(m["b"])
                m["crops"] = [str(c).upper() for c in m["crops"]]
                m.setdefault(
                    "equation",
                    f"Kc = {m['a']} × NDVI "
                    + (f"+ {m['b']}" if m["b"] >= 0 else f"- {abs(m['b'])}")
                )
                m.setdefault("doi", "")
                m.setdefault("scope", "")
                m.setdefault("kc_type", "Kc")
                m.setdefault("sensor", "Not specified")
                m.setdefault("study_region", "Not specified")
                m.setdefault("r2", None)
                m.setdefault("ndvi_min", None)
                m.setdefault("ndvi_max", None)
                m.setdefault("kc_min", None)
                m.setdefault("kc_max", None)
                m.setdefault("source_type", "built-in")
                m.setdefault("verification_status", "not specified")
                m.setdefault("calibration_note", "")
                cleaned[str(model_id)] = m

            KC_CATALOG = cleaned
            logging.info("Loaded %d Kc-NDVI relationships", len(KC_CATALOG))
        except Exception as exc:
            logging.exception("Kc library load failed")
            messagebox.showwarning(
                "Kc–NDVI library",
                "The external Kc library could not be loaded. "
                "The internal catalogue will be used.\n\n"
                f"{exc}",
            )

    def _save_kc_library(self):
        self.kc_library_path.write_text(
            json.dumps(KC_CATALOG, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logging.info("Kc-NDVI library saved: %s", self.kc_library_path)

    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Import parcels…", command=self.import_parcels)
        file_menu.add_separator()
        file_menu.add_command(label="Export all NDVI results…", command=self.export_all_results)
        file_menu.add_command(label="Export Kc / CWR / IWR…", command=self.export_water_results)
        file_menu.add_command(label="Export spatial results (GeoPackage)…", command=self.export_spatial_results)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(label="Kc–NDVI Library…", command=self.open_kc_library_manager)
        tools_menu.add_command(label="Open log folder", command=self.open_log_folder)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Methodology", command=self.show_methodology)
        help_menu.add_command(label="Citation / Contact", command=self.show_about)
        help_menu.add_command(label="About CropWater-RS", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def open_log_folder(self):
        try:
            path = str(self.log_dir)
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showinfo("Log file", str(self.log_path))

    def show_methodology(self):
        messagebox.showinfo(
            "CropWater-RS methodology",
            "Core scientific workflow\n\n"
            "NDVI = (B08 - B04) / (B08 + B04)\n\n"
            "Kc = a × NDVI + b\n\n"
            "ETc / CWR = Kc × ETo\n\n"
            "Net IWR(d) = max[ETc(d) - Pe(d), 0]\n\n"
            "The net IWR implementation is a simplified daily requirement. "
            "It does not represent a complete soil-water balance and does not "
            "include soil-water storage, runoff, deep percolation or capillary rise.\n\n"
            "Accumulated CWR/IWR requires a continuous daily reconstructed NDVI/Kc series.\n\n"
            "Parcel crop labelling can be performed manually or imported in batch from "
            "user-selected vector attributes. ID/CROPS (or parcel_id/crop) are auto-detected "
            "when attribute mode is used, but any source columns can be selected explicitly.\n\n"
            "QUANT phenology is an independent optional module. It applies parcel-wise "
            "amplitude thresholds to reconstructed daily NDVI to derive FAO-56-style "
            "stage boundaries, following an adaptation of French et al. (2023)."
        )

    def show_about(self):
        m = self.software_metadata
        win = tk.Toplevel(self)
        win.title("About / Citation — CropWater-RS")
        win.transient(self)
        win.geometry("700x760")
        win.minsize(620, 650)

        outer = ttk.Frame(win, style="Surface.TFrame", padding=18)
        outer.pack(fill="both", expand=True)

        if self.about_logo_image is not None:
            ttk.Label(
                outer,
                image=self.about_logo_image,
                style="Surface.TLabel",
            ).pack(anchor="center", pady=(0, 10))

        ttk.Label(
            outer,
            text=f"CropWater-RS v{APP_VERSION}",
            font=("Segoe UI Semibold", 18),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Remote Sensing · Phenology · Irrigation",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        info = (
            f"Author: {m.get('author', '')}\n"
            f"Affiliation: {m.get('affiliation', '')}\n"
            f"E-mail: {m.get('email', '')}\n"
            f"ORCID: {m.get('orcid', '')}\n"
            f"License: {m.get('license', 'GPL-3.0')}\n"
            f"Repository: {m.get('repository_url') or 'Not configured'}\n"
            f"Zenodo DOI: {m.get('zenodo_doi') or 'Not configured'}"
        )
        ttk.Label(outer, text=info, justify="left", wraplength=600).pack(fill="x", anchor="w")

        ttk.Separator(outer).pack(fill="x", pady=14)
        ttk.Label(outer, text="Preferred citation", style="SectionTitle.TLabel").pack(anchor="w")

        citation = m.get("preferred_citation", "")
        txt = tk.Text(outer, height=6, wrap="word")
        txt.pack(fill="both", expand=True, pady=(5, 10))
        txt.insert("1.0", citation)
        txt.configure(state="disabled")

        def copy_citation():
            self.clipboard_clear()
            self.clipboard_append(citation)
            self.update_idletasks()

        buttons = ttk.Frame(outer, style="Surface.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Copy citation", command=copy_citation, style="Primary.TButton").pack(side="left")

        repo = m.get("repository_url", "").strip()
        if repo:
            ttk.Button(
                buttons,
                text="Open repository",
                command=lambda: webbrowser.open(repo),
                style="Secondary.TButton",
            ).pack(side="left", padx=(8, 0))

        ttk.Button(buttons, text="Close", command=win.destroy, style="Secondary.TButton").pack(side="right")

    def open_kc_library_manager(self):
        win = tk.Toplevel(self)
        win.title("Kc–NDVI Library")
        win.geometry("980x560")
        win.minsize(820, 460)
        win.transient(self)

        root = ttk.Frame(win, style="Surface.TFrame", padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Kc–NDVI relationship library", style="SectionTitle.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text=(
                "Built-in relations preserve their provenance. "
                "New relations added here are explicitly marked as user-defined/unverified."
            ),
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=(2, 8))

        cols = ("id", "crop", "equation", "status", "reference")
        tree = ttk.Treeview(root, columns=cols, show="headings", height=15)
        for col, title, width in [
            ("id", "Model ID", 155),
            ("crop", "Crop(s)", 110),
            ("equation", "Equation", 190),
            ("status", "Status", 175),
            ("reference", "Reference", 300),
        ]:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="both", expand=True)

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            for mid, m in KC_CATALOG.items():
                tree.insert(
                    "", "end", iid=mid,
                    values=(
                        mid,
                        ", ".join(m.get("crops", [])),
                        m.get("equation", ""),
                        m.get("verification_status", ""),
                        m.get("reference", ""),
                    ),
                )

        def selected_id():
            sel = tree.selection()
            return sel[0] if sel else None

        def view_details():
            mid = selected_id()
            if not mid:
                return
            m = KC_CATALOG[mid]
            details = "\n".join([
                f"ID: {mid}",
                f"Label: {m.get('label', '')}",
                f"Crop(s): {', '.join(m.get('crops', []))}",
                f"Equation: {m.get('equation', '')}",
                f"Reference: {m.get('reference', '')}",
                f"DOI: {m.get('doi', '') or '—'}",
                f"Sensor: {m.get('sensor', '')}",
                f"Region: {m.get('study_region', '')}",
                f"R²: {m.get('r2', '') if m.get('r2') is not None else '—'}",
                f"NDVI calibration range: {m.get('ndvi_min')} – {m.get('ndvi_max')}",
                f"Source type: {m.get('source_type', '')}",
                f"Verification: {m.get('verification_status', '')}",
                f"Notes: {m.get('calibration_note', '')}",
            ])
            messagebox.showinfo("Kc–NDVI relationship", details, parent=win)

        def edit_relation():
            mid = selected_id()
            if not mid:
                messagebox.showwarning("Kc library", "Select a relationship.", parent=win)
                return
            if KC_CATALOG[mid].get("source_type") != "user-defined":
                messagebox.showinfo(
                    "Kc library",
                    "Built-in relationships are read-only to preserve scientific provenance.",
                    parent=win,
                )
                return
            self._open_kc_relation_editor(parent=win, model_id=mid, refresh_callback=refresh)

        def remove_relation():
            mid = selected_id()
            if not mid:
                return
            if KC_CATALOG[mid].get("source_type") != "user-defined":
                messagebox.showinfo(
                    "Kc library",
                    "Built-in relationships cannot be removed.",
                    parent=win,
                )
                return
            if not messagebox.askyesno("Remove relationship", f"Remove '{mid}'?", parent=win):
                return
            del KC_CATALOG[mid]
            self._save_kc_library()
            for pid, assigned in list(self.kc_assignments.items()):
                if assigned == mid:
                    self.kc_assignments.pop(pid, None)
                    self._invalidate_from_kc(pid)
            self._refresh_kc_tree()
            refresh()

        row = ttk.Frame(root, style="Surface.TFrame")
        row.pack(fill="x", pady=(9, 0))
        ttk.Button(
            row, text="Add relationship",
            command=lambda: self._open_kc_relation_editor(parent=win, refresh_callback=refresh),
            style="Primary.TButton",
        ).pack(side="left")
        ttk.Button(row, text="Edit user-defined", command=edit_relation, style="Secondary.TButton").pack(side="left", padx=(7, 0))
        ttk.Button(row, text="Remove user-defined", command=remove_relation, style="Secondary.TButton").pack(side="left", padx=(7, 0))
        ttk.Button(row, text="View details", command=view_details, style="Secondary.TButton").pack(side="left", padx=(7, 0))
        ttk.Button(row, text="Close", command=win.destroy, style="Secondary.TButton").pack(side="right")
        tree.bind("<Double-1>", lambda _e: view_details())
        refresh()

    def _open_kc_relation_editor(self, parent, model_id=None, refresh_callback=None):
        existing = KC_CATALOG.get(model_id, {}) if model_id else {}

        win = tk.Toplevel(parent)
        win.title("Edit Kc–NDVI relationship" if model_id else "Add Kc–NDVI relationship")
        win.geometry("660x690")
        win.transient(parent)

        frame = ttk.Frame(win, style="Surface.TFrame", padding=14)
        frame.pack(fill="both", expand=True)

        fields = {}
        specs = [
            ("label", "Display label", existing.get("label", "")),
            ("crops", "Crop(s), comma separated", ", ".join(existing.get("crops", ["ALL"]))),
            ("a", "Slope a", str(existing.get("a", ""))),
            ("b", "Intercept b", str(existing.get("b", ""))),
            ("reference", "Primary reference", existing.get("reference", "")),
            ("doi", "DOI", existing.get("doi", "")),
            ("sensor", "Sensor / platform", existing.get("sensor", "")),
            ("study_region", "Study region", existing.get("study_region", "")),
            ("r2", "R² (optional)", "" if existing.get("r2") is None else str(existing.get("r2"))),
            ("ndvi_min", "NDVI calibration minimum (optional)", "" if existing.get("ndvi_min") is None else str(existing.get("ndvi_min"))),
            ("ndvi_max", "NDVI calibration maximum (optional)", "" if existing.get("ndvi_max") is None else str(existing.get("ndvi_max"))),
            ("scope", "Scope / notes", existing.get("scope", "")),
        ]

        for r, (key, label, value) in enumerate(specs):
            ttk.Label(frame, text=label, style="Field.TLabel").grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=value)
            ttk.Entry(frame, textvariable=var).grid(row=r, column=1, sticky="ew", padx=(10, 0), pady=4)
            fields[key] = var

        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text=(
                "User-added relationships are stored externally and exported as "
                "'user-defined / unverified' until independently checked."
            ),
            style="Info.TLabel",
            wraplength=600,
            justify="left",
        ).grid(row=len(specs), column=0, columnspan=2, sticky="ew", pady=(10, 6))

        def optional_float(value):
            value = value.strip()
            return None if value == "" else float(value)

        def save():
            try:
                label = fields["label"].get().strip()
                crops = [c.strip().upper() for c in fields["crops"].get().split(",") if c.strip()]
                if not label or not crops:
                    raise ValueError("Label and at least one crop are required.")
                a = float(fields["a"].get())
                b = float(fields["b"].get())

                if model_id:
                    mid = model_id
                else:
                    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "user_model"
                    mid = base
                    k = 2
                    while mid in KC_CATALOG:
                        mid = f"{base}_{k}"
                        k += 1

                equation = f"Kc = {a:g} × NDVI " + (f"+ {b:g}" if b >= 0 else f"- {abs(b):g}")
                KC_CATALOG[mid] = {
                    "label": label,
                    "crops": crops,
                    "equation": equation,
                    "a": a,
                    "b": b,
                    "reference": fields["reference"].get().strip(),
                    "doi": fields["doi"].get().strip(),
                    "scope": fields["scope"].get().strip(),
                    "kc_type": "Kc",
                    "sensor": fields["sensor"].get().strip() or "Not specified",
                    "study_region": fields["study_region"].get().strip() or "Not specified",
                    "r2": optional_float(fields["r2"].get()),
                    "ndvi_min": optional_float(fields["ndvi_min"].get()),
                    "ndvi_max": optional_float(fields["ndvi_max"].get()),
                    "kc_min": None,
                    "kc_max": None,
                    "source_type": "user-defined",
                    "verification_status": "user-defined / unverified",
                    "calibration_note": "Added by the user; scientific verification is the user's responsibility.",
                }
                self._save_kc_library()
                self._refresh_kc_tree()
                if refresh_callback:
                    refresh_callback()
                logging.info("User Kc relationship saved: %s", mid)
                win.destroy()
            except Exception as exc:
                messagebox.showerror("Kc relationship", str(exc), parent=win)

        btns = ttk.Frame(frame, style="Surface.TFrame")
        btns.grid(row=len(specs)+1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(btns, text="Save relationship", command=save, style="Primary.TButton").pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy, style="Secondary.TButton").pack(side="right")

    def _build_style(self):
        self.ui = {
            "bg": "#F4F7FA",
            "surface": "#FFFFFF",
            "surface_alt": "#F8FAFC",
            "border": "#D8E0E8",
            "text": "#1D2A35",
            "muted": "#667788",
            "primary": "#176B87",
            "primary_hover": "#135A72",
            "accent": "#64CCC5",
            "success": "#2F855A",
            "warning": "#B7791F",
        }

        self.configure(bg=self.ui["bg"])

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".",
            font=("Segoe UI", 10),
            background=self.ui["bg"],
            foreground=self.ui["text"],
        )

        style.configure(
            "App.TFrame",
            background=self.ui["bg"],
        )
        style.configure(
            "Surface.TFrame",
            background=self.ui["surface"],
        )
        style.configure(
            "Card.TFrame",
            background=self.ui["surface"],
            relief="solid",
            borderwidth=1,
        )
        style.configure(
            "Header.TFrame",
            background=self.ui["primary"],
        )

        style.configure(
            "AppTitle.TLabel",
            font=("Segoe UI Semibold", 20),
            foreground="white",
            background=self.ui["primary"],
        )
        style.configure(
            "AppSubtitle.TLabel",
            font=("Segoe UI", 10),
            foreground="#DCEEF4",
            background=self.ui["primary"],
        )
        style.configure(
            "HeaderStatus.TLabel",
            font=("Segoe UI Semibold", 9),
            foreground="white",
            background=self.ui["primary"],
        )

        style.configure(
            "SectionTitle.TLabel",
            font=("Segoe UI Semibold", 11),
            foreground=self.ui["text"],
            background=self.ui["surface"],
        )
        style.configure(
            "SectionNumber.TLabel",
            font=("Segoe UI Semibold", 10),
            foreground="white",
            background=self.ui["primary"],
            padding=(7, 3),
        )
        style.configure(
            "Field.TLabel",
            font=("Segoe UI Semibold", 9),
            foreground=self.ui["text"],
            background=self.ui["surface"],
        )
        style.configure(
            "Muted.TLabel",
            font=("Segoe UI", 9),
            foreground=self.ui["muted"],
            background=self.ui["surface"],
        )
        style.configure(
            "Info.TLabel",
            font=("Segoe UI", 9),
            foreground=self.ui["muted"],
            background=self.ui["surface_alt"],
            padding=7,
        )
        style.configure(
            "StatusBar.TLabel",
            font=("Segoe UI", 9),
            foreground=self.ui["muted"],
            background=self.ui["surface"],
        )

        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(10, 7),
            background=self.ui["primary"],
            foreground="white",
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", self.ui["primary_hover"]),
                ("disabled", "#A9BAC3"),
            ],
            foreground=[("disabled", "#F3F5F6")],
        )

        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            padding=(9, 6),
            background="#EAF1F5",
            foreground=self.ui["text"],
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#DCE8EE")],
        )

        style.configure(
            "Compact.TButton",
            font=("Segoe UI", 9),
            padding=(7, 4),
        )

        style.configure(
            "TEntry",
            padding=5,
            fieldbackground="white",
        )
        style.configure(
            "TCombobox",
            padding=4,
        )
        style.configure(
            "TSpinbox",
            padding=4,
        )

        style.configure(
            "Treeview",
            background="white",
            fieldbackground="white",
            foreground=self.ui["text"],
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 9),
            background="#EAF1F5",
            foreground=self.ui["text"],
            relief="flat",
            padding=6,
        )
        style.map(
            "Treeview",
            background=[("selected", self.ui["primary"])],
            foreground=[("selected", "white")],
        )

        style.configure(
            "TNotebook",
            background=self.ui["bg"],
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            font=("Segoe UI Semibold", 10),
            padding=(16, 8),
            background="#E8EEF2",
            foreground=self.ui["muted"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.ui["surface"])],
            foreground=[("selected", self.ui["primary"])],
        )

        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#E5EDF1",
            background=self.ui["primary"],
            bordercolor="#E5EDF1",
            lightcolor=self.ui["primary"],
            darkcolor=self.ui["primary"],
        )

    def _make_card(self, parent, number, title, subtitle=None, pady=(0, 10)):
        outer = ttk.Frame(parent, style="Card.TFrame", padding=0)
        outer.pack(fill="x", pady=pady)

        header = ttk.Frame(outer, style="Surface.TFrame", padding=(10, 9, 10, 6))
        header.pack(fill="x")

        ttk.Label(
            header,
            text=str(number),
            style="SectionNumber.TLabel",
        ).pack(side="left", padx=(0, 8))

        title_box = ttk.Frame(header, style="Surface.TFrame")
        title_box.pack(side="left", fill="x", expand=True)

        ttk.Label(
            title_box,
            text=title,
            style="SectionTitle.TLabel",
        ).pack(anchor="w")

        if subtitle:
            ttk.Label(
                title_box,
                text=subtitle,
                style="Muted.TLabel",
                wraplength=370,
                justify="left",
            ).pack(anchor="w", pady=(1, 0))

        body = ttk.Frame(outer, style="Surface.TFrame", padding=(10, 5, 10, 10))
        body.pack(fill="x")
        return body

    def _field_label(self, parent, text):
        return ttk.Label(parent, text=text, style="Field.TLabel")

    def _build_ui(self):
        # Top application header
        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 13))
        header.pack(fill="x")

        brand = ttk.Frame(header, style="Header.TFrame")
        brand.pack(side="left", fill="x", expand=True)

        if self.header_logo_image is not None:
            ttk.Label(
                brand,
                image=self.header_logo_image,
                style="Header.TLabel",
            ).pack(side="left", padx=(0, 12))

        brand_text = ttk.Frame(brand, style="Header.TFrame")
        brand_text.pack(side="left", fill="x", expand=True)

        ttk.Label(
            brand_text,
            text="CropWater-RS",
            style="AppTitle.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            brand_text,
            text="Remote Sensing · Phenology · Irrigation",
            style="AppSubtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            header,
            textvariable=self.status_var,
            style="HeaderStatus.TLabel",
        ).pack(side="right", padx=(16, 0))

        # Top-level application modules.
        # QUANT is deliberately separated from the main NDVI/Kc/water workflow.
        self.module_notebook = ttk.Notebook(self)
        self.module_notebook.pack(fill="both", expand=True, padx=12, pady=(10, 8))

        self.workflow_module = ttk.Frame(
            self.module_notebook,
            style="App.TFrame",
        )
        self.quant_module = ttk.Frame(
            self.module_notebook,
            style="App.TFrame",
        )

        self.module_notebook.add(
            self.workflow_module,
            text="Main workflow",
        )
        self.module_notebook.add(
            self.quant_module,
            text="QUANT phenology",
        )

        # Main scientific workflow workspace
        workspace = ttk.Frame(
            self.workflow_module,
            style="App.TFrame",
            padding=(0, 0, 0, 0),
        )
        workspace.pack(fill="both", expand=True)

        main = ttk.Panedwindow(workspace, orient="horizontal")
        main.pack(fill="both", expand=True)

        left_container = ttk.Frame(main, style="App.TFrame")
        self.right_panel = ttk.Frame(main, style="App.TFrame", padding=(10, 0, 0, 0))

        main.add(left_container, weight=2)
        main.add(self.right_panel, weight=5)

        # Scrollable workflow panel
        self.left_canvas = tk.Canvas(
            left_container,
            bg=self.ui["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.left_scrollbar = ttk.Scrollbar(
            left_container,
            orient="vertical",
            command=self.left_canvas.yview,
        )
        self.left_canvas.configure(yscrollcommand=self.left_scrollbar.set)

        self.left_scrollbar.pack(side="right", fill="y")
        self.left_canvas.pack(side="left", fill="both", expand=True)

        self.left_panel = ttk.Frame(
            self.left_canvas,
            style="App.TFrame",
            padding=(0, 0, 6, 6),
        )
        self.left_window = self.left_canvas.create_window(
            (0, 0),
            window=self.left_panel,
            anchor="nw",
        )

        self.left_panel.bind(
            "<Configure>",
            lambda event: self.left_canvas.configure(
                scrollregion=self.left_canvas.bbox("all")
            ),
        )
        self.left_canvas.bind(
            "<Configure>",
            lambda event: self.left_canvas.itemconfigure(
                self.left_window, width=event.width
            ),
        )

        self.left_canvas.bind(
            "<Enter>",
            lambda event: self.bind_all("<MouseWheel>", self._on_left_mousewheel),
        )
        self.left_canvas.bind(
            "<Leave>",
            lambda event: self.unbind_all("<MouseWheel>"),
        )

        self._build_left_panel()
        self._build_right_panel()
        self._build_quant_module()

        # Persistent bottom status bar
        statusbar = ttk.Frame(self, style="Surface.TFrame", padding=(12, 5))
        statusbar.pack(fill="x", side="bottom")

        ttk.Label(
            statusbar,
            text="Research workflow:",
            style="StatusBar.TLabel",
        ).pack(side="left")
        ttk.Label(
            statusbar,
            text="Parcels → NDVI → temporal processing → Kc → CWR / IWR",
            style="StatusBar.TLabel",
        ).pack(side="left", padx=(5, 0))

    def _on_left_mousewheel(self, event):
        """Scroll the left controls panel with the mouse wheel."""
        self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _build_left_panel(self):
        # =============================================================
        # 1. PARCELS
        # =============================================================
        frm_parcels = self._make_card(
            self.left_panel,
            "1",
            "Parcels",
            "Load polygon parcels and choose manual or attribute-based crop labelling.",
        )

        ttk.Button(
            frm_parcels,
            text="Import parcel file",
            command=self.import_parcels,
            style="Primary.TButton",
        ).pack(fill="x")

        self.file_var = tk.StringVar(value="No parcel file loaded")
        ttk.Label(
            frm_parcels,
            textvariable=self.file_var,
            style="Muted.TLabel",
            wraplength=390,
        ).pack(fill="x", pady=(7, 5))

        # ---------------------------------------------------------
        # Crop labelling mode
        # ---------------------------------------------------------
        mode_box = ttk.Frame(
            frm_parcels,
            style="Surface.TFrame",
        )
        mode_box.pack(fill="x", pady=(2, 7))

        self._field_label(
            mode_box,
            "Crop labelling",
        ).pack(anchor="w")

        self.crop_label_mode_var = tk.StringVar(value="manual")

        radio_row = ttk.Frame(
            mode_box,
            style="Surface.TFrame",
        )
        radio_row.pack(fill="x", pady=(2, 5))

        ttk.Radiobutton(
            radio_row,
            text="Manual assignment",
            value="manual",
            variable=self.crop_label_mode_var,
            command=self._update_crop_labelling_mode,
        ).pack(side="left")

        ttk.Radiobutton(
            radio_row,
            text="Use vector attributes",
            value="attributes",
            variable=self.crop_label_mode_var,
            command=self._update_crop_labelling_mode,
        ).pack(side="left", padx=(12, 0))

        # Attribute mapping controls. They are populated after a vector
        # layer is loaded and remain disabled in manual mode.
        self.vector_fields_frame = ttk.Frame(
            mode_box,
            style="Surface.TFrame",
        )
        self.vector_fields_frame.pack(fill="x", pady=(2, 0))

        self._field_label(
            self.vector_fields_frame,
            "ID field",
        ).grid(row=0, column=0, sticky="w")
        self._field_label(
            self.vector_fields_frame,
            "Crop field",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.id_field_var = tk.StringVar(value="<Auto>")
        self.crop_field_var = tk.StringVar(value="<Auto>")

        self.id_field_combo = ttk.Combobox(
            self.vector_fields_frame,
            textvariable=self.id_field_var,
            state="disabled",
        )
        self.id_field_combo.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(2, 0),
        )

        self.crop_field_combo = ttk.Combobox(
            self.vector_fields_frame,
            textvariable=self.crop_field_var,
            state="disabled",
        )
        self.crop_field_combo.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(2, 0),
        )

        self.vector_fields_frame.columnconfigure(0, weight=1)
        self.vector_fields_frame.columnconfigure(1, weight=1)

        self.apply_fields_btn = ttk.Button(
            mode_box,
            text="Apply selected vector fields",
            command=self.apply_vector_fields,
            style="Secondary.TButton",
            state="disabled",
        )
        self.apply_fields_btn.pack(fill="x", pady=(6, 0))

        self.crop_mode_info_var = tk.StringVar(
            value=(
                "Manual mode: select a parcel below and assign its crop. "
                "Parcel IDs are still imported automatically when available."
            )
        )
        ttk.Label(
            mode_box,
            textvariable=self.crop_mode_info_var,
            style="Muted.TLabel",
            wraplength=390,
            justify="left",
        ).pack(fill="x", pady=(5, 0))

        cols = ("id", "area_ha", "crop")

        parcel_tree_wrap = ttk.Frame(
            frm_parcels,
            style="Surface.TFrame",
        )
        parcel_tree_wrap.pack(fill="both", expand=True, pady=(3, 7))

        self.tree = ttk.Treeview(
            parcel_tree_wrap,
            columns=cols,
            show="headings",
            height=7,
            selectmode="browse",
        )
        self.tree.heading("id", text="Parcel")
        self.tree.heading("area_ha", text="Area (ha)")
        self.tree.heading("crop", text="Crop")
        self.tree.column("id", width=85, anchor="center")
        self.tree.column("area_ha", width=90, anchor="e")
        self.tree.column("crop", width=145, anchor="center")

        parcel_tree_scroll = ttk.Scrollbar(
            parcel_tree_wrap,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(
            yscrollcommand=parcel_tree_scroll.set
        )
        self.tree.pack(
            side="left",
            fill="both",
            expand=True,
        )
        parcel_tree_scroll.pack(
            side="right",
            fill="y",
        )

        self.tree.bind("<<TreeviewSelect>>", self._on_parcel_selected)

        cropbox = ttk.Frame(frm_parcels, style="Surface.TFrame")
        cropbox.pack(fill="x")
        self._field_label(cropbox, "Crop").grid(row=0, column=0, sticky="w")

        self.crop_var = tk.StringVar(value=CROPS[0])
        self.crop_combo = ttk.Combobox(
            cropbox,
            textvariable=self.crop_var,
            values=CROPS,
            state="readonly",
        )
        self.crop_combo.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.assign_crop_btn = ttk.Button(
            cropbox,
            text="Assign",
            command=self.assign_crop,
            style="Secondary.TButton",
        )
        self.assign_crop_btn.grid(
            row=1,
            column=1,
            padx=(7, 0),
            pady=(2, 0),
        )

        cropbox.columnconfigure(0, weight=1)
        self._update_crop_labelling_mode()


        # =============================================================
        # 2. CDSE
        # =============================================================
        frm_cdse = self._make_card(
            self.left_panel,
            "2",
            "Copernicus Data Space",
            "OAuth credentials are used only to request Sentinel-2 statistics.",
        )

        self._field_label(frm_cdse, "Client ID").pack(anchor="w")
        self.client_id_var = tk.StringVar(value=os.getenv("CDSE_CLIENT_ID", ""))
        ttk.Entry(
            frm_cdse,
            textvariable=self.client_id_var,
        ).pack(fill="x", pady=(2, 7))

        self._field_label(frm_cdse, "Client Secret").pack(anchor="w")
        self.client_secret_var = tk.StringVar(value=os.getenv("CDSE_CLIENT_SECRET", ""))
        ttk.Entry(
            frm_cdse,
            textvariable=self.client_secret_var,
            show="•",
        ).pack(fill="x", pady=(2, 7))

        ttk.Button(
            frm_cdse,
            text="Configure and test connection",
            command=self.configure_cdse,
            style="Primary.TButton",
        ).pack(fill="x")

        # =============================================================
        # 3. SENTINEL-2 NDVI
        # =============================================================
        frm_s2 = self._make_card(
            self.left_panel,
            "3",
            "Sentinel-2 NDVI",
            "Parcel-level P50 NDVI with SCL quality masking.",
        )

        dates = ttk.Frame(frm_s2, style="Surface.TFrame")
        dates.pack(fill="x")

        self._field_label(dates, "Start date").grid(row=0, column=0, sticky="w")
        self._field_label(dates, "End date").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        current_year = date.today().year
        self.start_var = tk.StringVar(value=f"{current_year}-01-01")
        self.end_var = tk.StringVar(value=date.today().isoformat())

        self.start_entry = ttk.Entry(dates, textvariable=self.start_var)
        self.start_entry.grid(row=1, column=0, sticky="ew", pady=(2, 7))

        self.end_entry = ttk.Entry(dates, textvariable=self.end_var)
        self.end_entry.grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 7)
        )

        self.start_entry.bind("<FocusOut>", lambda event: self._refresh_plot_period())
        self.end_entry.bind("<FocusOut>", lambda event: self._refresh_plot_period())
        self.start_entry.bind("<Return>", lambda event: self._refresh_plot_period())
        self.end_entry.bind("<Return>", lambda event: self._refresh_plot_period())

        dates.columnconfigure(0, weight=1)
        dates.columnconfigure(1, weight=1)

        opts = ttk.Frame(frm_s2, style="Surface.TFrame")
        opts.pack(fill="x")

        self._field_label(opts, "Aggregation").grid(row=0, column=0, sticky="w")
        self._field_label(opts, "Min. valid pixels (%)").grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        self.interval_var = tk.StringVar(value="P1D")
        ttk.Combobox(
            opts,
            textvariable=self.interval_var,
            values=["P1D", "P5D", "P10D"],
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 7))

        self.valid_pct_var = tk.DoubleVar(value=70.0)
        self.valid_pct_spin = ttk.Spinbox(
            opts,
            from_=0,
            to=100,
            increment=5,
            textvariable=self.valid_pct_var,
        )
        self.valid_pct_spin.grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(2, 7)
        )

        opts.columnconfigure(0, weight=1)
        opts.columnconfigure(1, weight=1)

        self.valid_pct_var.trace_add(
            "write",
            lambda *_args: self.after_idle(self._recalculate_valid_threshold),
        )

        self.run_btn = ttk.Button(
            frm_s2,
            text="Calculate NDVI for all parcels",
            command=self.run_ndvi,
            style="Primary.TButton",
        )
        self.run_btn.pack(fill="x")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(
            frm_s2,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
        )
        self.progress.pack(fill="x", pady=(8, 3))

        self.progress_text_var = tk.StringVar(value="Ready")
        ttk.Label(
            frm_s2,
            textvariable=self.progress_text_var,
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 6))

        exportrow = ttk.Frame(frm_s2, style="Surface.TFrame")
        exportrow.pack(fill="x")

        ttk.Button(
            exportrow,
            text="Export selected",
            command=self.export_csv,
            style="Secondary.TButton",
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            exportrow,
            text="Export all",
            command=self.export_all_results,
            style="Secondary.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(7, 0))

        # =============================================================
        # 4. TEMPORAL PROCESSING
        # =============================================================
        frm_temporal = self._make_card(
            self.left_panel,
            "4",
            "Temporal processing",
            "Reconstruct a continuous NDVI trajectory for water calculations.",
        )

        self._field_label(frm_temporal, "Method").pack(anchor="w")
        self.temporal_method_var = tk.StringVar(value="Whittaker")
        self.temporal_method_combo = ttk.Combobox(
            frm_temporal,
            textvariable=self.temporal_method_var,
            values=[
                "Raw observations",
                "Linear interpolation",
                "Whittaker",
                "Savitzky-Golay",
                "Kalman",
            ],
            state="readonly",
        )
        self.temporal_method_combo.pack(fill="x", pady=(2, 7))

        # Dynamic parameter area: only relevant controls are displayed.
        self.temporal_param_frame = ttk.Frame(
            frm_temporal, style="Surface.TFrame"
        )
        self.temporal_param_frame.pack(fill="x")

        self.whittaker_frame = ttk.Frame(
            self.temporal_param_frame, style="Surface.TFrame"
        )
        self._field_label(self.whittaker_frame, "Whittaker λ").pack(anchor="w")
        self.whittaker_lambda_var = tk.DoubleVar(value=1000.0)
        ttk.Entry(
            self.whittaker_frame,
            textvariable=self.whittaker_lambda_var,
        ).pack(fill="x", pady=(2, 7))

        self.sg_frame = ttk.Frame(
            self.temporal_param_frame, style="Surface.TFrame"
        )
        self._field_label(self.sg_frame, "Savitzky-Golay window (days)").pack(anchor="w")
        self.sg_window_var = tk.IntVar(value=15)
        ttk.Spinbox(
            self.sg_frame,
            from_=5,
            to=61,
            increment=2,
            textvariable=self.sg_window_var,
        ).pack(fill="x", pady=(2, 7))

        self.temporal_method_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._update_temporal_parameter_visibility(),
        )

        self._field_label(frm_temporal, "Output resolution").pack(anchor="w")
        self.output_resolution_var = tk.StringVar(value="Daily")
        ttk.Combobox(
            frm_temporal,
            textvariable=self.output_resolution_var,
            values=["Daily", "5 days", "10 days"],
            state="readonly",
        ).pack(fill="x", pady=(2, 7))

        self.constrain_ndvi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm_temporal,
            text="Constrain reconstructed NDVI to 0–1",
            variable=self.constrain_ndvi_var,
        ).pack(anchor="w")

        self.show_rejected_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm_temporal,
            text="Show rejected observations",
            variable=self.show_rejected_var,
            command=self._refresh_selected_plot,
        ).pack(anchor="w", pady=(3, 7))

        ttk.Button(
            frm_temporal,
            text="Process all temporal series",
            command=self.process_temporal_all,
            style="Primary.TButton",
        ).pack(fill="x")

        self.temporal_diag_var = tk.StringVar(
            value="Fit diagnostics: not calculated"
        )
        ttk.Label(
            frm_temporal,
            textvariable=self.temporal_diag_var,
            style="Info.TLabel",
            wraplength=390,
            justify="left",
        ).pack(fill="x", pady=(8, 0))

        self._update_temporal_parameter_visibility()

        # =============================================================
        # 5. KC + WATER REQUIREMENTS
        # =============================================================
        frm_water = self._make_card(
            self.left_panel,
            "5",
            "Kc and water requirements",
            "Assign a literature Kc–NDVI relation, then calculate ETc/CWR and optional net IWR.",
        )

        self._field_label(frm_water, "Kc model by parcel").pack(anchor="w")

        kc_cols = ("parcel", "crop", "model")
        kc_tree_wrap = ttk.Frame(
            frm_water,
            style="Surface.TFrame",
        )
        kc_tree_wrap.pack(fill="x", pady=(3, 7))

        self.kc_tree = ttk.Treeview(
            kc_tree_wrap,
            columns=kc_cols,
            show="headings",
            height=5,
            selectmode="browse",
        )
        self.kc_tree.heading("parcel", text="Parcel")
        self.kc_tree.heading("crop", text="Crop")
        self.kc_tree.heading("model", text="Kc–NDVI relation")
        self.kc_tree.column("parcel", width=65, anchor="center")
        self.kc_tree.column("crop", width=85, anchor="center")
        self.kc_tree.column("model", width=225, anchor="w")

        kc_tree_scroll = ttk.Scrollbar(
            kc_tree_wrap,
            orient="vertical",
            command=self.kc_tree.yview,
        )
        self.kc_tree.configure(
            yscrollcommand=kc_tree_scroll.set
        )
        self.kc_tree.pack(
            side="left",
            fill="x",
            expand=True,
        )
        kc_tree_scroll.pack(
            side="right",
            fill="y",
        )

        self.kc_tree.bind("<<TreeviewSelect>>", self._on_kc_parcel_selected)

        self._field_label(frm_water, "Available relationship").pack(anchor="w")
        self.kc_model_var = tk.StringVar(value="")
        self.kc_model_combo = ttk.Combobox(
            frm_water,
            textvariable=self.kc_model_var,
            state="readonly",
        )
        self.kc_model_combo.pack(fill="x", pady=(2, 5))
        self.kc_model_combo.bind("<<ComboboxSelected>>", self._show_kc_model_info)

        self.kc_info_var = tk.StringVar(
            value="Select a parcel and a Kc relationship."
        )
        ttk.Label(
            frm_water,
            textvariable=self.kc_info_var,
            style="Info.TLabel",
            wraplength=390,
            justify="left",
        ).pack(fill="x", pady=(2, 7))

        kc_buttons = ttk.Frame(frm_water, style="Surface.TFrame")
        kc_buttons.pack(fill="x")
        ttk.Button(
            kc_buttons,
            text="Apply to parcel",
            command=self.assign_kc_selected,
            style="Secondary.TButton",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            kc_buttons,
            text="Apply to same crop",
            command=self.assign_kc_same_crop,
            style="Secondary.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(7, 0))

        ttk.Separator(frm_water, orient="horizontal").pack(fill="x", pady=10)

        kc_opts = ttk.Frame(frm_water, style="Surface.TFrame")
        kc_opts.pack(fill="x")

        self._field_label(kc_opts, "NDVI source for Kc").pack(anchor="w")
        self.kc_ndvi_source_var = tk.StringVar(value="Processed if available")
        ttk.Combobox(
            kc_opts,
            textvariable=self.kc_ndvi_source_var,
            values=[
                "Processed if available",
                "Processed only",
                "Raw accepted observations",
            ],
            state="readonly",
        ).pack(fill="x", pady=(2, 5))

        self.kc_clip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            kc_opts,
            text="Constrain Kc to non-negative values",
            variable=self.kc_clip_var,
        ).pack(anchor="w", pady=(1, 7))

        ttk.Button(
            frm_water,
            text="Calculate Kc for all parcels",
            command=self.calculate_kc_all,
            style="Primary.TButton",
        ).pack(fill="x")

        ttk.Separator(frm_water, orient="horizontal").pack(fill="x", pady=10)

        self._field_label(frm_water, "Meteorological data").pack(anchor="w")
        ttk.Label(
            frm_water,
            text="Required: Date + ETo. Add Pe for net IWR. Optional parcel_id enables parcel-specific meteorology.",
            style="Muted.TLabel",
            wraplength=390,
            justify="left",
        ).pack(fill="x", pady=(1, 5))

        self.meteo_file_var = tk.StringVar(value="No meteorological CSV loaded")

        metrow = ttk.Frame(frm_water, style="Surface.TFrame")
        metrow.pack(fill="x")

        ttk.Button(
            metrow,
            text="Load CSV",
            command=self.load_meteo_csv,
            style="Secondary.TButton",
        ).pack(side="left")

        ttk.Label(
            metrow,
            textvariable=self.meteo_file_var,
            style="Muted.TLabel",
            wraplength=285,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        modebox = ttk.Frame(frm_water, style="Surface.TFrame")
        modebox.pack(fill="x", pady=(8, 0))

        self._field_label(modebox, "Calculation mode").pack(anchor="w")
        self.water_mode_var = tk.StringVar(value="CWR / ETc only")
        ttk.Combobox(
            modebox,
            textvariable=self.water_mode_var,
            values=["CWR / ETc only", "Net IWR"],
            state="readonly",
        ).pack(fill="x", pady=(2, 7))

        ttk.Button(
            frm_water,
            text="Calculate CWR / IWR",
            command=self.calculate_water_all,
            style="Primary.TButton",
        ).pack(fill="x")

        ttk.Button(
            frm_water,
            text="Export Kc / CWR / IWR",
            command=self.export_water_results,
            style="Secondary.TButton",
        ).pack(fill="x", pady=(7, 0))

        self.water_summary_var = tk.StringVar(
            value="Water results: not calculated"
        )
        ttk.Label(
            frm_water,
            textvariable=self.water_summary_var,
            style="Info.TLabel",
            wraplength=390,
            justify="left",
        ).pack(fill="x", pady=(8, 0))

    def _update_temporal_parameter_visibility(self):
        if not hasattr(self, "temporal_param_frame"):
            return

        self.whittaker_frame.pack_forget()
        self.sg_frame.pack_forget()

        method = self.temporal_method_var.get()
        if method == "Whittaker":
            self.whittaker_frame.pack(fill="x")
        elif method == "Savitzky-Golay":
            self.sg_frame.pack(fill="x")

    # =============================================================
    # QUANT PHENOLOGY MODULE
    # Adapted from French et al. (2023), Agricultural Water Management
    # =============================================================
    def _build_quant_module(self):
        outer = ttk.Frame(
            self.quant_module,
            style="App.TFrame",
            padding=(12, 10, 12, 10),
        )
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(
            outer,
            style="Surface.TFrame",
            padding=(14, 11),
        )
        header.pack(fill="x", pady=(0, 8))

        titlebox = ttk.Frame(header, style="Surface.TFrame")
        titlebox.pack(side="left", fill="x", expand=True)

        ttk.Label(
            titlebox,
            text="QUANT phenological partitioning",
            style="SectionTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            titlebox,
            text=(
                "Independent parcel-wise detection of FAO-56-style stage boundaries "
                "from the reconstructed daily NDVI curve."
            ),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        self.quant_notebook = ttk.Notebook(outer)
        self.quant_notebook.pack(fill="both", expand=True)

        self.quant_analysis_tab = ttk.Frame(
            self.quant_notebook,
            style="Surface.TFrame",
            padding=10,
        )
        self.quant_method_tab = ttk.Frame(
            self.quant_notebook,
            style="Surface.TFrame",
            padding=16,
        )

        self.quant_notebook.add(
            self.quant_analysis_tab,
            text="QUANT analysis",
        )
        self.quant_notebook.add(
            self.quant_method_tab,
            text="Method & reference",
        )

        # ---------------------------------------------------------
        # Analysis tab
        # ---------------------------------------------------------
        body = ttk.Panedwindow(
            self.quant_analysis_tab,
            orient="horizontal",
        )
        body.pack(fill="both", expand=True)

        # Scrollable left-side controls. This prevents lower QUANT
        # controls/results from becoming inaccessible on smaller screens.
        control_host = ttk.Frame(
            body,
            style="App.TFrame",
            padding=(0, 0, 8, 0),
        )
        plot_side = ttk.Frame(
            body,
            style="App.TFrame",
            padding=(8, 0, 0, 0),
        )
        body.add(control_host, weight=2)
        body.add(plot_side, weight=5)

        control_canvas = tk.Canvas(
            control_host,
            highlightthickness=0,
            bd=0,
            bg=self.ui["bg"],
        )
        control_scrollbar = ttk.Scrollbar(
            control_host,
            orient="vertical",
            command=control_canvas.yview,
        )
        control_canvas.configure(
            yscrollcommand=control_scrollbar.set
        )

        control_canvas.pack(
            side="left",
            fill="both",
            expand=True,
        )
        control_scrollbar.pack(
            side="right",
            fill="y",
        )

        control = ttk.Frame(
            control_canvas,
            style="App.TFrame",
            padding=(0, 0, 4, 0),
        )
        control_window = control_canvas.create_window(
            (0, 0),
            window=control,
            anchor="nw",
        )

        def _quant_control_configure(_event=None):
            control_canvas.configure(
                scrollregion=control_canvas.bbox("all")
            )

        def _quant_canvas_configure(event):
            control_canvas.itemconfigure(
                control_window,
                width=event.width,
            )

        control.bind(
            "<Configure>",
            _quant_control_configure,
        )
        control_canvas.bind(
            "<Configure>",
            _quant_canvas_configure,
        )

        # Mouse wheel support while the pointer is over the QUANT controls.
        def _quant_mousewheel(event):
            delta = -1 if event.delta > 0 else 1
            control_canvas.yview_scroll(delta, "units")

        control_canvas.bind(
            "<Enter>",
            lambda _e: control_canvas.bind_all(
                "<MouseWheel>",
                _quant_mousewheel,
            ),
        )
        control_canvas.bind(
            "<Leave>",
            lambda _e: control_canvas.unbind_all(
                "<MouseWheel>"
            ),
        )

        # Parameters
        params = ttk.Frame(
            control,
            style="Card.TFrame",
            padding=12,
        )
        params.pack(fill="x", pady=(0, 8))

        ttk.Label(
            params,
            text="User-defined amplitude thresholds",
            style="SectionTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            params,
            text=(
                "Thresholds are percentages of the parcel-specific NDVI amplitude "
                "between the pre-peak minimum and seasonal maximum."
            ),
            style="Muted.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        grid = ttk.Frame(params, style="Surface.TFrame")
        grid.pack(fill="x")

        self.quant_q1_var = tk.DoubleVar(value=10.0)
        self.quant_q2_var = tk.DoubleVar(value=90.0)
        self.quant_q3_var = tk.DoubleVar(value=90.0)
        self.quant_q4_var = tk.DoubleVar(value=50.0)

        fields = [
            ("INI → DEV, rising (%)", self.quant_q1_var),
            ("DEV → MID, rising (%)", self.quant_q2_var),
            ("MID → END, falling (%)", self.quant_q3_var),
            ("End of season, falling (%)", self.quant_q4_var),
        ]

        for r, (label, var) in enumerate(fields):
            ttk.Label(
                grid,
                text=label,
                style="Field.TLabel",
            ).grid(row=r, column=0, sticky="w", pady=4)
            ttk.Spinbox(
                grid,
                from_=1,
                to=99,
                increment=1,
                textvariable=var,
                width=8,
            ).grid(row=r, column=1, sticky="e", padx=(10, 0), pady=4)

        grid.columnconfigure(0, weight=1)

        ttk.Label(
            params,
            text=(
                "Defaults reproduce the French et al. QUANT thresholds: "
                "10% and 90% on the ascending limb, 90% for the end of MID, "
                "and 50% for the end of the growing season."
            ),
            style="Info.TLabel",
            wraplength=360,
            justify="left",
        ).pack(fill="x", pady=(9, 8))

        ttk.Button(
            params,
            text="Calculate QUANT for all parcels",
            command=self.calculate_quant_all,
            style="Primary.TButton",
        ).pack(fill="x")

        btnrow = ttk.Frame(params, style="Surface.TFrame")
        btnrow.pack(fill="x", pady=(7, 0))

        ttk.Button(
            btnrow,
            text="Export QUANT CSV",
            command=self.export_quant_results,
            style="Secondary.TButton",
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            btnrow,
            text="Summarize water by phase",
            command=self.calculate_quant_water_summary,
            style="Secondary.TButton",
        ).pack(side="left", fill="x", expand=True, padx=(7, 0))

        # Parcel result table
        table_card = ttk.Frame(
            control,
            style="Card.TFrame",
            padding=10,
        )
        table_card.pack(fill="both", expand=True)

        ttk.Label(
            table_card,
            text="Parcel-specific transitions",
            style="SectionTitle.TLabel",
        ).pack(anchor="w", pady=(0, 5))

        qcols = ("parcel", "status", "q1", "q2", "q3", "q4")
        self.quant_tree = ttk.Treeview(
            table_card,
            columns=qcols,
            show="headings",
            height=12,
            selectmode="browse",
        )
        headings = {
            "parcel": "Parcel",
            "status": "Status",
            "q1": "INI/DEV",
            "q2": "DEV/MID",
            "q3": "MID/END",
            "q4": "EOS",
        }
        widths = {
            "parcel": 68,
            "status": 92,
            "q1": 78,
            "q2": 78,
            "q3": 78,
            "q4": 78,
        }
        for c in qcols:
            self.quant_tree.heading(c, text=headings[c])
            self.quant_tree.column(
                c,
                width=widths[c],
                anchor="center",
            )
        tree_wrap = ttk.Frame(
            table_card,
            style="Surface.TFrame",
        )
        tree_wrap.pack(fill="both", expand=True)

        quant_tree_scroll = ttk.Scrollbar(
            tree_wrap,
            orient="vertical",
            command=self.quant_tree.yview,
        )
        self.quant_tree.configure(
            yscrollcommand=quant_tree_scroll.set
        )
        self.quant_tree.pack(
            in_=tree_wrap,
            side="left",
            fill="both",
            expand=True,
        )
        quant_tree_scroll.pack(
            in_=tree_wrap,
            side="right",
            fill="y",
        )

        self.quant_tree.bind(
            "<<TreeviewSelect>>",
            self._on_quant_parcel_selected,
        )

        self.quant_status_var = tk.StringVar(
            value="Run temporal processing first, then calculate QUANT."
        )
        ttk.Label(
            table_card,
            textvariable=self.quant_status_var,
            style="Info.TLabel",
            wraplength=365,
            justify="left",
        ).pack(fill="x", pady=(8, 0))

        # QUANT plot
        plot_header = ttk.Frame(
            plot_side,
            style="Surface.TFrame",
            padding=(10, 8),
        )
        plot_header.pack(fill="x", pady=(0, 7))

        ttk.Label(
            plot_header,
            text="Parcel QUANT profile",
            style="SectionTitle.TLabel",
        ).pack(side="left")

        nav = ttk.Frame(
            plot_header,
            style="Surface.TFrame",
        )
        nav.pack(side="right")

        ttk.Button(
            nav,
            text="◀ Previous",
            command=lambda: self._navigate_quant_parcel(-1),
            style="Secondary.TButton",
        ).pack(side="left")

        self.quant_nav_var = tk.StringVar(
            value="Parcel — / —"
        )
        ttk.Label(
            nav,
            textvariable=self.quant_nav_var,
            style="Muted.TLabel",
            width=16,
            anchor="center",
        ).pack(side="left", padx=8)

        ttk.Button(
            nav,
            text="Next ▶",
            command=lambda: self._navigate_quant_parcel(1),
            style="Secondary.TButton",
        ).pack(side="left")

        plot_subheader = ttk.Frame(
            plot_side,
            style="Surface.TFrame",
            padding=(10, 0, 10, 5),
        )
        plot_subheader.pack(fill="x")

        ttk.Label(
            plot_subheader,
            text="Reconstructed daily NDVI + parcel-specific transition points",
            style="Muted.TLabel",
        ).pack(side="left")

        plot_card = ttk.Frame(
            plot_side,
            style="Card.TFrame",
            padding=8,
        )
        plot_card.pack(fill="both", expand=True)

        figq = Figure(
            figsize=(8.5, 5.8),
            dpi=100,
            facecolor="white",
        )
        self.ax_quant = figq.add_subplot(111)
        self.ax_quant.set_title(
            "QUANT results will be shown here",
            pad=12,
        )
        self.ax_quant.set_xlabel("Date")
        self.ax_quant.set_ylabel("NDVI")
        self.ax_quant.set_ylim(0, 1)
        self.ax_quant.grid(True, alpha=0.22)
        self.ax_quant.spines["top"].set_visible(False)
        self.ax_quant.spines["right"].set_visible(False)

        self.canvas_quant = FigureCanvasTkAgg(
            figq,
            master=plot_card,
        )
        self.canvas_quant.draw()
        self.canvas_quant.get_tk_widget().pack(
            fill="both",
            expand=True,
        )

        toolbarq = NavigationToolbar2Tk(
            self.canvas_quant,
            plot_card,
            pack_toolbar=False,
        )
        toolbarq.update()
        toolbarq.pack(fill="x", pady=(4, 0))

        # ---------------------------------------------------------
        # Method/reference tab
        # ---------------------------------------------------------
        ttk.Label(
            self.quant_method_tab,
            text="QUANT method implemented in CropWater-RS",
            style="SectionTitle.TLabel",
        ).pack(anchor="w")

        method_text = (
            "CropWater-RS implements an adapted, parcel-wise version of the "
            "quantile procedure described by French et al. (2023) for deriving "
            "FAO-56-style crop growth-stage transitions from filtered daily NDVI.\n\n"
            "For every parcel independently, the application identifies the seasonal "
            "NDVI maximum and the preceding minimum. The NDVI amplitude is defined as "
            "A = NDVImax − NDVImin. User-defined percentages are converted to absolute "
            "thresholds as NDVIq = NDVImin + q·A. Transition dates are then obtained "
            "by linear interpolation of threshold crossings on the ascending and "
            "descending limbs of the reconstructed daily curve.\n\n"
            "Default thresholds reproduce the values used by French et al.: "
            "10% for INI→DEV, 90% for DEV→MID, 90% on the descending limb for "
            "MID→END, and 50% on the descending limb for the end of the season.\n\n"
            "Important adaptation in CropWater-RS: French et al. constrained the "
            "planting date using crop-specific FAO-56 initial-stage durations and a "
            "±10-day window. CropWater-RS does not impose that external constraint. "
            "Instead, the pre-peak NDVI minimum is retained as the parcel-specific "
            "cycle start. Therefore, results should be interpreted as remotely sensed "
            "FAO-56-style stage partitioning, not as direct observations of physiological "
            "crop stages.\n\n"
            "All calculations are performed independently for each parcel. If the "
            "smoothed curve does not provide the required threshold crossings, that "
            "parcel is flagged as incomplete rather than assigning an artificial date."
        )

        txt = tk.Text(
            self.quant_method_tab,
            wrap="word",
            height=20,
            relief="flat",
            padx=12,
            pady=12,
            bg="white",
            fg=self.ui["text"],
            font=("Segoe UI", 10),
        )
        txt.pack(fill="both", expand=True, pady=(8, 10))
        txt.insert("1.0", method_text)
        txt.configure(state="disabled")

        ref_card = ttk.Frame(
            self.quant_method_tab,
            style="Card.TFrame",
            padding=12,
        )
        ref_card.pack(fill="x")

        ttk.Label(
            ref_card,
            text="Primary reference",
            style="SectionTitle.TLabel",
        ).pack(anchor="w")

        reference = (
            "French, A.N., Sanchez, C.A., Wirth, T., Scott, A., Shields, J.W., "
            "Bautista, E., Saber, M.N., Wisniewski, E., & Gohardoust, M.R. (2023). "
            "Remote sensing of evapotranspiration for irrigated crops at Yuma, "
            "Arizona, USA. Agricultural Water Management, 290, 108582. "
            "https://doi.org/10.1016/j.agwat.2023.108582"
        )

        ttk.Label(
            ref_card,
            text=reference,
            style="Muted.TLabel",
            wraplength=1050,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))

        ttk.Button(
            ref_card,
            text="Open DOI",
            command=lambda: webbrowser.open(
                "https://doi.org/10.1016/j.agwat.2023.108582"
            ),
            style="Secondary.TButton",
        ).pack(anchor="w")

    def _validate_quant_thresholds(self):
        vals = [
            float(self.quant_q1_var.get()),
            float(self.quant_q2_var.get()),
            float(self.quant_q3_var.get()),
            float(self.quant_q4_var.get()),
        ]
        if any(v <= 0 or v >= 100 for v in vals):
            raise ValueError(
                "All QUANT thresholds must be between 0 and 100%."
            )
        q1, q2, q3, q4 = vals
        if q1 >= q2:
            raise ValueError(
                "The ascending INI→DEV threshold must be lower than DEV→MID."
            )
        if q4 >= q3:
            raise ValueError(
                "For the descending limb, the EOS threshold must be lower "
                "than the MID→END threshold."
            )
        return vals

    @staticmethod
    def _quant_crossing_date(dates, values, threshold, direction):
        dates = pd.to_datetime(pd.Series(dates), errors="coerce").reset_index(drop=True)
        values = pd.Series(values, dtype=float).reset_index(drop=True)

        hits = []
        for i in range(len(values) - 1):
            y0 = values.iloc[i]
            y1 = values.iloc[i + 1]
            if not np.isfinite(y0) or not np.isfinite(y1):
                continue

            if direction == "rising":
                crossed = (y0 <= threshold <= y1) and (y1 > y0)
            else:
                crossed = (y0 >= threshold >= y1) and (y1 < y0)

            if not crossed:
                continue

            t0 = dates.iloc[i]
            t1 = dates.iloc[i + 1]
            if pd.isna(t0) or pd.isna(t1):
                continue

            frac = (threshold - y0) / (y1 - y0)
            dt = t0 + (t1 - t0) * float(frac)
            hits.append(pd.Timestamp(dt))

        if not hits:
            return pd.NaT

        # Right-most crossing is more robust to small residual oscillations
        # and is consistent with the late-season selection described by French et al.
        return hits[-1] if direction == "falling" else hits[0]

    def _calculate_quant_one(self, parcel_id):
        result = self.temporal_results.get(str(parcel_id))
        if result is None:
            # tolerate legacy keys not converted to str
            result = self.temporal_results.get(parcel_id)
        if not result:
            raise ValueError("No reconstructed temporal series.")

        daily = result.get("daily")
        if daily is None or daily.empty:
            raise ValueError("Daily reconstructed NDVI is unavailable.")

        df = daily[["date", "ndvi_reconstructed_daily"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["ndvi_reconstructed_daily"] = pd.to_numeric(
            df["ndvi_reconstructed_daily"],
            errors="coerce",
        )
        df = (
            df.dropna()
            .drop_duplicates("date")
            .sort_values("date")
            .reset_index(drop=True)
        )

        if len(df) < 5:
            raise ValueError("Too few daily values for QUANT.")

        vals = df["ndvi_reconstructed_daily"].to_numpy(dtype=float)
        peak_pos = int(np.nanargmax(vals))
        if peak_pos < 2 or peak_pos >= len(df) - 2:
            raise ValueError(
                "Seasonal maximum is too close to the temporal boundary."
            )

        pre = df.iloc[: peak_pos + 1]
        min_rel = int(np.nanargmin(
            pre["ndvi_reconstructed_daily"].to_numpy(dtype=float)
        ))
        min_pos = min_rel

        ndvi_min = float(df.loc[min_pos, "ndvi_reconstructed_daily"])
        ndvi_max = float(df.loc[peak_pos, "ndvi_reconstructed_daily"])
        amplitude = ndvi_max - ndvi_min

        if not np.isfinite(amplitude) or amplitude <= 0.05:
            raise ValueError(
                f"Insufficient seasonal NDVI amplitude ({amplitude:.3f})."
            )

        q1, q2, q3, q4 = self._validate_quant_thresholds()

        thresholds = {
            "Q1": ndvi_min + (q1 / 100.0) * amplitude,
            "Q2": ndvi_min + (q2 / 100.0) * amplitude,
            "Q3": ndvi_min + (q3 / 100.0) * amplitude,
            "Q4": ndvi_min + (q4 / 100.0) * amplitude,
        }

        rising = df.iloc[min_pos : peak_pos + 1].copy()
        falling = df.iloc[peak_pos:].copy()

        q1_date = self._quant_crossing_date(
            rising["date"],
            rising["ndvi_reconstructed_daily"],
            thresholds["Q1"],
            "rising",
        )
        q2_date = self._quant_crossing_date(
            rising["date"],
            rising["ndvi_reconstructed_daily"],
            thresholds["Q2"],
            "rising",
        )
        q3_date = self._quant_crossing_date(
            falling["date"],
            falling["ndvi_reconstructed_daily"],
            thresholds["Q3"],
            "falling",
        )
        q4_date = self._quant_crossing_date(
            falling["date"],
            falling["ndvi_reconstructed_daily"],
            thresholds["Q4"],
            "falling",
        )

        cycle_start = pd.Timestamp(df.loc[min_pos, "date"])
        peak_date = pd.Timestamp(df.loc[peak_pos, "date"])

        required = [q1_date, q2_date, q3_date, q4_date]
        complete = all(not pd.isna(x) for x in required)

        durations = {
            "INI_days": np.nan,
            "DEV_days": np.nan,
            "MID_days": np.nan,
            "END_days": np.nan,
            "Total_days": np.nan,
        }

        if complete:
            durations["INI_days"] = (q1_date - cycle_start).total_seconds() / 86400.0
            durations["DEV_days"] = (q2_date - q1_date).total_seconds() / 86400.0
            durations["MID_days"] = (q3_date - q2_date).total_seconds() / 86400.0
            durations["END_days"] = (q4_date - q3_date).total_seconds() / 86400.0
            durations["Total_days"] = (q4_date - cycle_start).total_seconds() / 86400.0

            if any(v < 0 for v in durations.values()):
                complete = False

        crop = ""
        if self.gdf is not None:
            hit = self.gdf[
                self.gdf["parcel_id"].astype(str) == str(parcel_id)
            ]
            if not hit.empty:
                crop = str(hit.iloc[0]["crop"])

        out = {
            "parcel_id": str(parcel_id),
            "crop": crop,
            "status": "Complete" if complete else "Incomplete",
            "cycle_start_date": cycle_start,
            "cycle_start_DOY": int(cycle_start.dayofyear),
            "peak_date": peak_date,
            "peak_DOY": int(peak_date.dayofyear),
            "NDVI_min": ndvi_min,
            "NDVI_max": ndvi_max,
            "NDVI_amplitude": amplitude,
            "q1_percent": q1,
            "q2_percent": q2,
            "q3_percent": q3,
            "q4_percent": q4,
            "q1_threshold_ndvi": thresholds["Q1"],
            "q2_threshold_ndvi": thresholds["Q2"],
            "q3_threshold_ndvi": thresholds["Q3"],
            "q4_threshold_ndvi": thresholds["Q4"],
            "Q1_date": q1_date,
            "Q2_date": q2_date,
            "Q3_date": q3_date,
            "Q4_date": q4_date,
            "Q1_DOY": int(q1_date.dayofyear) if not pd.isna(q1_date) else np.nan,
            "Q2_DOY": int(q2_date.dayofyear) if not pd.isna(q2_date) else np.nan,
            "Q3_DOY": int(q3_date.dayofyear) if not pd.isna(q3_date) else np.nan,
            "Q4_DOY": int(q4_date.dayofyear) if not pd.isna(q4_date) else np.nan,
            **durations,
        }
        return out

    def calculate_quant_all(self):
        if not self.temporal_results:
            messagebox.showwarning(
                "QUANT",
                "No reconstructed daily NDVI series are available.\n\n"
                "Run Temporal processing in the Main workflow first.",
            )
            return

        try:
            self._validate_quant_thresholds()
        except Exception as exc:
            messagebox.showerror("QUANT parameters", str(exc))
            return

        self.quant_results.clear()
        self.quant_water_summary.clear()
        errors = []

        parcel_ids = []
        if self.gdf is not None:
            parcel_ids = self.gdf["parcel_id"].astype(str).tolist()
        else:
            parcel_ids = [str(k) for k in self.temporal_results.keys()]

        for pid in parcel_ids:
            try:
                self.quant_results[pid] = self._calculate_quant_one(pid)
            except Exception as exc:
                self.quant_results[pid] = {
                    "parcel_id": pid,
                    "crop": "",
                    "status": "Incomplete",
                    "error": str(exc),
                }
                errors.append((pid, str(exc)))

        self._refresh_quant_tree()

        if parcel_ids:
            self._select_quant_parcel(parcel_ids[0])

        complete_n = sum(
            1
            for r in self.quant_results.values()
            if r.get("status") == "Complete"
        )
        self.quant_status_var.set(
            f"QUANT completed: {complete_n}/{len(parcel_ids)} parcel(s) complete. "
            "Each parcel was analysed independently."
        )

        logging.info(
            "QUANT completed: %d/%d complete",
            complete_n,
            len(parcel_ids),
        )

        if errors:
            preview = "\n".join(
                f"{pid}: {msg}" for pid, msg in errors[:5]
            )
            messagebox.showwarning(
                "QUANT",
                f"QUANT completed with incomplete parcels.\n\n{preview}",
            )
        else:
            messagebox.showinfo(
                "QUANT",
                f"QUANT completed for {complete_n} parcel(s).",
            )

    def _refresh_quant_tree(self):
        if not hasattr(self, "quant_tree"):
            return

        current = self.quant_tree.selection()
        current_pid = None
        if current:
            current_pid = self.quant_tree.item(
                current[0], "values"
            )[0]

        for item in self.quant_tree.get_children():
            self.quant_tree.delete(item)

        def fmt_doy(v):
            try:
                if pd.isna(v):
                    return "—"
                return str(int(v))
            except Exception:
                return "—"

        for pid, r in self.quant_results.items():
            self.quant_tree.insert(
                "",
                "end",
                iid=str(pid),
                values=(
                    pid,
                    r.get("status", "—"),
                    fmt_doy(r.get("Q1_DOY", np.nan)),
                    fmt_doy(r.get("Q2_DOY", np.nan)),
                    fmt_doy(r.get("Q3_DOY", np.nan)),
                    fmt_doy(r.get("Q4_DOY", np.nan)),
                ),
            )

        if current_pid and str(current_pid) in self.quant_tree.get_children():
            self.quant_tree.selection_set(str(current_pid))

        if hasattr(self, "quant_nav_var"):
            self._update_quant_navigation_label(
                current_pid if current_pid else None
            )

    def _select_quant_parcel(self, parcel_id):
        pid = str(parcel_id)
        if not hasattr(self, "quant_tree"):
            return
        if pid in self.quant_tree.get_children():
            self.quant_tree.selection_set(pid)
            self.quant_tree.focus(pid)
            self.quant_tree.see(pid)
            self._update_quant_navigation_label(pid)
            self._plot_quant_parcel(pid)

    def _navigate_quant_parcel(self, step):
        """Move to previous/next parcel in the QUANT result table."""
        if not hasattr(self, "quant_tree"):
            return

        items = list(self.quant_tree.get_children())
        if not items:
            if hasattr(self, "quant_nav_var"):
                self.quant_nav_var.set("Parcel — / —")
            return

        current = self.quant_tree.selection()
        if current and current[0] in items:
            idx = items.index(current[0])
        else:
            idx = 0

        new_idx = (idx + int(step)) % len(items)
        target = items[new_idx]

        self.quant_tree.selection_set(target)
        self.quant_tree.focus(target)
        self.quant_tree.see(target)
        self._plot_quant_parcel(str(target))

    def _update_quant_navigation_label(self, parcel_id=None):
        if not hasattr(self, "quant_nav_var") or not hasattr(self, "quant_tree"):
            return

        items = list(self.quant_tree.get_children())
        if not items:
            self.quant_nav_var.set("Parcel — / —")
            return

        pid = str(parcel_id) if parcel_id is not None else None
        if pid not in items:
            sel = self.quant_tree.selection()
            pid = sel[0] if sel and sel[0] in items else items[0]

        idx = items.index(pid) + 1
        self.quant_nav_var.set(
            f"{pid}  ({idx}/{len(items)})"
        )

    def _on_quant_parcel_selected(self, _event=None):
        sel = self.quant_tree.selection()
        if not sel:
            return
        pid = str(sel[0])
        self._update_quant_navigation_label(pid)
        self._plot_quant_parcel(pid)

        # Synchronize main workflow parcel selection without forcing
        # the user to leave the QUANT module.
        if self.gdf is not None:
            hits = self.gdf.index[
                self.gdf["parcel_id"].astype(str) == pid
            ].tolist()
            if hits:
                target = str(hits[0])
                if target in self.tree.get_children():
                    self.tree.selection_set(target)
                    self.tree.focus(target)

    def _plot_quant_parcel(self, parcel_id):
        if not hasattr(self, "ax_quant"):
            return

        self.ax_quant.clear()
        self.ax_quant.spines["top"].set_visible(False)
        self.ax_quant.spines["right"].set_visible(False)
        self.ax_quant.grid(True, alpha=0.20)

        result = self.temporal_results.get(parcel_id)
        if result is None:
            # tolerate non-string keys
            result = next(
                (
                    v for k, v in self.temporal_results.items()
                    if str(k) == str(parcel_id)
                ),
                None,
            )

        q = self.quant_results.get(str(parcel_id))

        if not result or result.get("daily") is None:
            self.ax_quant.set_title(
                f"{parcel_id} | No reconstructed daily NDVI"
            )
            self.canvas_quant.draw_idle()
            return

        df = result["daily"].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["ndvi_reconstructed_daily"] = pd.to_numeric(
            df["ndvi_reconstructed_daily"],
            errors="coerce",
        )
        df = df.dropna(
            subset=["date", "ndvi_reconstructed_daily"]
        )

        self.ax_quant.plot(
            df["date"],
            df["ndvi_reconstructed_daily"],
            linewidth=2.0,
            label="Reconstructed daily NDVI",
        )

        if q and q.get("status") == "Complete":
            transitions = [
                ("Q1", q["Q1_date"], q["q1_threshold_ndvi"]),
                ("Q2", q["Q2_date"], q["q2_threshold_ndvi"]),
                ("Q3", q["Q3_date"], q["q3_threshold_ndvi"]),
                ("Q4", q["Q4_date"], q["q4_threshold_ndvi"]),
            ]

            # Phase shading
            phase_intervals = [
                (
                    q["cycle_start_date"],
                    q["Q1_date"],
                    "Initial",
                    0.055,
                ),
                (
                    q["Q1_date"],
                    q["Q2_date"],
                    "Development",
                    0.085,
                ),
                (
                    q["Q2_date"],
                    q["Q3_date"],
                    "Mid-season",
                    0.115,
                ),
                (
                    q["Q3_date"],
                    q["Q4_date"],
                    "Late-season",
                    0.145,
                ),
            ]

            for start, end, label, alpha in phase_intervals:
                self.ax_quant.axvspan(
                    pd.Timestamp(start),
                    pd.Timestamp(end),
                    alpha=alpha,
                    label=label,
                )

            # Threshold lines and transition markers
            for name, dt, ndvi_thr in transitions:
                dt = pd.Timestamp(dt)
                self.ax_quant.axvline(
                    dt,
                    linestyle="--",
                    linewidth=1.2,
                    alpha=0.85,
                )
                self.ax_quant.scatter(
                    [dt],
                    [ndvi_thr],
                    s=45,
                    zorder=6,
                )
                self.ax_quant.annotate(
                    f"{name}\nDOY {dt.dayofyear}",
                    xy=(dt, ndvi_thr),
                    xytext=(5, 8),
                    textcoords="offset points",
                    fontsize=8,
                )

            # Horizontal quantile levels
            for key in [
                "q1_threshold_ndvi",
                "q2_threshold_ndvi",
                "q3_threshold_ndvi",
                "q4_threshold_ndvi",
            ]:
                self.ax_quant.axhline(
                    q[key],
                    linewidth=0.7,
                    linestyle=":",
                    alpha=0.35,
                )

            self.ax_quant.set_title(
                f"{parcel_id} | QUANT parcel-specific FAO-56-style partitioning"
            )
            self.quant_status_var.set(
                f"{parcel_id}: INI={q['INI_days']:.1f} d | "
                f"DEV={q['DEV_days']:.1f} d | "
                f"MID={q['MID_days']:.1f} d | "
                f"END={q['END_days']:.1f} d | "
                f"Total={q['Total_days']:.1f} d"
            )
        else:
            reason = ""
            if q:
                reason = q.get("error", "Required crossings were not identified.")
            self.ax_quant.set_title(
                f"{parcel_id} | Incomplete QUANT"
            )
            self.quant_status_var.set(
                f"{parcel_id}: incomplete QUANT. {reason}"
            )

        self.ax_quant.set_xlabel("Date")
        self.ax_quant.set_ylabel("NDVI")
        self.ax_quant.set_ylim(0, 1)
        self.ax_quant.legend(
            loc="best",
            fontsize=8,
            ncol=2,
        )
        self.canvas_quant.figure.autofmt_xdate()
        self.canvas_quant.figure.tight_layout()
        self.canvas_quant.draw_idle()

    def calculate_quant_water_summary(self):
        if not self.quant_results:
            messagebox.showwarning(
                "QUANT water summary",
                "Calculate QUANT first.",
            )
            return

        if not self.water_results:
            messagebox.showwarning(
                "QUANT water summary",
                "No CWR/IWR results are available.\n\n"
                "Calculate Kc and CWR/IWR in the Main workflow first.",
            )
            return

        self.quant_water_summary.clear()

        for pid, q in self.quant_results.items():
            if q.get("status") != "Complete":
                continue

            wdf = self.water_results.get(pid)
            if wdf is None or wdf.empty:
                continue

            df = wdf.copy()
            date_col = "date" if "date" in df.columns else "Date"
            df[date_col] = pd.to_datetime(
                df[date_col],
                errors="coerce",
            )

            phases = {
                "INI": (
                    pd.Timestamp(q["cycle_start_date"]),
                    pd.Timestamp(q["Q1_date"]),
                ),
                "DEV": (
                    pd.Timestamp(q["Q1_date"]),
                    pd.Timestamp(q["Q2_date"]),
                ),
                "MID": (
                    pd.Timestamp(q["Q2_date"]),
                    pd.Timestamp(q["Q3_date"]),
                ),
                "END": (
                    pd.Timestamp(q["Q3_date"]),
                    pd.Timestamp(q["Q4_date"]),
                ),
            }

            summary = {"parcel_id": pid}
            for phase, (start, end) in phases.items():
                mask = (
                    (df[date_col] >= start.normalize())
                    & (df[date_col] <= end.normalize())
                )
                part = df.loc[mask]

                summary[f"CWR_{phase}_mm"] = (
                    float(part["ETc"].sum())
                    if "ETc" in part.columns
                    else np.nan
                )
                summary[f"IWR_{phase}_mm"] = (
                    float(part["IWR_net"].sum())
                    if "IWR_net" in part.columns
                    else np.nan
                )

            summary["CWR_QUANT_total_mm"] = sum(
                v
                for k, v in summary.items()
                if k.startswith("CWR_")
                and k.endswith("_mm")
                and np.isfinite(v)
            )
            iwr_vals = [
                v
                for k, v in summary.items()
                if k.startswith("IWR_")
                and k.endswith("_mm")
                and np.isfinite(v)
            ]
            summary["IWR_QUANT_total_mm"] = (
                sum(iwr_vals) if iwr_vals else np.nan
            )
            self.quant_water_summary[pid] = summary

        if not self.quant_water_summary:
            messagebox.showwarning(
                "QUANT water summary",
                "No parcel had both complete QUANT results and water calculations.",
            )
            return

        messagebox.showinfo(
            "QUANT water summary",
            f"Phase-specific CWR/IWR summarized for "
            f"{len(self.quant_water_summary)} parcel(s).\n\n"
            "These values will be included in the QUANT CSV export.",
        )

    def _quant_export_dataframe(self):
        rows = []

        for pid, q in self.quant_results.items():
            row = dict(q)

            # Convert dates to export-friendly ISO format.
            for key in [
                "cycle_start_date",
                "peak_date",
                "Q1_date",
                "Q2_date",
                "Q3_date",
                "Q4_date",
            ]:
                if key in row:
                    val = row[key]
                    row[key] = (
                        pd.Timestamp(val).strftime("%Y-%m-%d")
                        if not pd.isna(val)
                        else ""
                    )

            water = self.quant_water_summary.get(pid)
            if water:
                row.update(water)

            rows.append(row)

        return pd.DataFrame(rows)

    def export_quant_results(self):
        if not self.quant_results:
            messagebox.showwarning(
                "Export QUANT",
                "Calculate QUANT first.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Export QUANT results",
            defaultextension=".csv",
            initialfile="QUANT_phenology_all_parcels.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return

        try:
            out = self._quant_export_dataframe()
            out.to_csv(path, index=False)

            metadata_path = Path(path).with_name(
                Path(path).stem + "_metadata.txt"
            )
            q1, q2, q3, q4 = self._validate_quant_thresholds()
            metadata_path.write_text(
                (
                    "CropWater-RS QUANT module\n"
                    f"App version: {APP_VERSION}\n"
                    "Method: adapted QUANT, French et al. (2023)\n"
                    "Reference DOI: https://doi.org/10.1016/j.agwat.2023.108582\n"
                    f"INI->DEV rising threshold: {q1}%\n"
                    f"DEV->MID rising threshold: {q2}%\n"
                    f"MID->END falling threshold: {q3}%\n"
                    f"EOS falling threshold: {q4}%\n"
                    "Cycle start: parcel-specific pre-peak NDVI minimum\n"
                    "Crossings: linear interpolation on reconstructed daily NDVI\n"
                    "Interpretation: remotely sensed FAO-56-style stage partitioning\n"
                ),
                encoding="utf-8",
            )

            logging.info("QUANT export: %s", path)
            messagebox.showinfo(
                "Export QUANT",
                f"QUANT results exported successfully:\n{path}",
            )
        except Exception as exc:
            logging.exception("QUANT export failed")
            messagebox.showerror(
                "Export QUANT",
                str(exc),
            )

    def _build_right_panel(self):
        # Workspace heading
        top = ttk.Frame(self.right_panel, style="Surface.TFrame", padding=(12, 10))
        top.pack(fill="x", pady=(0, 8))

        ttk.Label(
            top,
            text="Analysis workspace",
            style="SectionTitle.TLabel",
        ).pack(side="left")

        ttk.Label(
            top,
            text="Select a parcel to update all plots",
            style="Muted.TLabel",
        ).pack(side="right")

        self.notebook = ttk.Notebook(self.right_panel)
        self.notebook.pack(fill="both", expand=True)

        self.tab_plot = ttk.Frame(
            self.notebook,
            style="Surface.TFrame",
            padding=10,
        )
        self.tab_water = ttk.Frame(
            self.notebook,
            style="Surface.TFrame",
            padding=10,
        )

        self.tab_spatial = ttk.Frame(
            self.notebook,
            style="Surface.TFrame",
            padding=10,
        )

        self.notebook.add(self.tab_plot, text="NDVI time series")
        self.notebook.add(self.tab_water, text="Kc · CWR · IWR")
        self.notebook.add(self.tab_spatial, text="Spatial view")

        # ---------------- NDVI tab ----------------
        ndvi_header = ttk.Frame(self.tab_plot, style="Surface.TFrame")
        ndvi_header.pack(fill="x", pady=(0, 7))

        ttk.Label(
            ndvi_header,
            text="Parcel NDVI trajectory",
            style="SectionTitle.TLabel",
        ).pack(side="left")

        ndvi_nav = ttk.Frame(
            ndvi_header,
            style="Surface.TFrame",
        )
        ndvi_nav.pack(side="right")

        ttk.Button(
            ndvi_nav,
            text="◀ Previous",
            command=lambda: self._navigate_main_parcel(-1),
            style="Secondary.TButton",
        ).pack(side="left")

        self.ndvi_nav_var = tk.StringVar(value="Parcel — / —")
        ttk.Label(
            ndvi_nav,
            textvariable=self.ndvi_nav_var,
            style="Muted.TLabel",
            width=18,
            anchor="center",
        ).pack(side="left", padx=8)

        ttk.Button(
            ndvi_nav,
            text="Next ▶",
            command=lambda: self._navigate_main_parcel(1),
            style="Secondary.TButton",
        ).pack(side="left")

        ndvi_subheader = ttk.Frame(
            self.tab_plot,
            style="Surface.TFrame",
        )
        ndvi_subheader.pack(fill="x", pady=(0, 6))
        ttk.Label(
            ndvi_subheader,
            text="Raw observations, QA filtering and temporal reconstruction",
            style="Muted.TLabel",
        ).pack(side="left")

        plot_card = ttk.Frame(
            self.tab_plot,
            style="Card.TFrame",
            padding=8,
        )
        plot_card.pack(fill="both", expand=True)

        fig = Figure(figsize=(8.5, 5.8), dpi=100, facecolor="white")
        self.ax = fig.add_subplot(111)
        self.ax.set_title("Load parcels and calculate NDVI", pad=12)
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("NDVI")
        self.ax.set_ylim(0.0, 1.0)
        self.ax.set_yticks(np.arange(0.0, 1.01, 0.2))
        self.ax.grid(True, alpha=0.22)
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)

        self.canvas = FigureCanvasTkAgg(fig, master=plot_card)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        toolbar = NavigationToolbar2Tk(
            self.canvas, plot_card, pack_toolbar=False
        )
        toolbar.update()
        toolbar.pack(fill="x", pady=(4, 0))

        # ---------------- Water tab ----------------
        water_header = ttk.Frame(self.tab_water, style="Surface.TFrame")
        water_header.pack(fill="x", pady=(0, 7))

        titlebox = ttk.Frame(water_header, style="Surface.TFrame")
        titlebox.pack(side="left")

        ttk.Label(
            titlebox,
            text="Kc and crop-water response",
            style="SectionTitle.TLabel",
        ).pack(anchor="w")

        ttk.Label(
            titlebox,
            text="The graph follows the parcel selected in either parcel table.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        controlbox = ttk.Frame(water_header, style="Surface.TFrame")
        controlbox.pack(side="right")

        ttk.Button(
            controlbox,
            text="◀ Previous",
            command=lambda: self._navigate_main_parcel(-1),
            style="Secondary.TButton",
        ).pack(side="left")

        self.water_nav_var = tk.StringVar(value="Parcel — / —")
        ttk.Label(
            controlbox,
            textvariable=self.water_nav_var,
            style="Muted.TLabel",
            width=18,
            anchor="center",
        ).pack(side="left", padx=8)

        ttk.Button(
            controlbox,
            text="Next ▶",
            command=lambda: self._navigate_main_parcel(1),
            style="Secondary.TButton",
        ).pack(side="left", padx=(0, 14))

        self._field_label(controlbox, "Variable").pack(side="left")

        self.water_plot_var = tk.StringVar(value="Kc")
        self.water_plot_combo = ttk.Combobox(
            controlbox,
            textvariable=self.water_plot_var,
            values=[
                "Kc",
                "ETc daily",
                "CWR cumulative",
                "IWR net daily",
                "IWR net cumulative",
            ],
            state="readonly",
            width=22,
        )
        self.water_plot_combo.pack(side="left", padx=(7, 0))
        self.water_plot_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._plot_selected_water(),
        )

        water_card = ttk.Frame(
            self.tab_water,
            style="Card.TFrame",
            padding=8,
        )
        water_card.pack(fill="both", expand=True)

        fig2 = Figure(figsize=(8.5, 5.8), dpi=100, facecolor="white")
        self.ax_water = fig2.add_subplot(111)
        self.ax_water.set_title("Kc / crop water requirements", pad=12)
        self.ax_water.set_xlabel("Date")
        self.ax_water.grid(True, alpha=0.22)
        self.ax_water.spines["top"].set_visible(False)
        self.ax_water.spines["right"].set_visible(False)

        self.canvas_water = FigureCanvasTkAgg(fig2, master=water_card)
        self.canvas_water.draw()
        self.canvas_water.get_tk_widget().pack(fill="both", expand=True)

        toolbar2 = NavigationToolbar2Tk(
            self.canvas_water, water_card, pack_toolbar=False
        )
        toolbar2.update()
        toolbar2.pack(fill="x", pady=(4, 0))

        # ---------------- Spatial tab ----------------
        spatial_header = ttk.Frame(self.tab_spatial, style="Surface.TFrame")
        spatial_header.pack(fill="x", pady=(0, 7))

        spatial_title = ttk.Frame(spatial_header, style="Surface.TFrame")
        spatial_title.pack(side="left")
        ttk.Label(spatial_title, text="Parcel-level spatial view", style="SectionTitle.TLabel").pack(anchor="w")
        ttk.Label(
            spatial_title,
            text="Polygon colours represent parcel statistics, not a pixel-level raster.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        spatial_controls = ttk.Frame(spatial_header, style="Surface.TFrame")
        spatial_controls.pack(side="right")

        self.spatial_metric_var = tk.StringVar(value="NDVI P50")
        self.spatial_metric_combo = ttk.Combobox(
            spatial_controls,
            textvariable=self.spatial_metric_var,
            values=["NDVI P50", "Processed NDVI", "Valid pixel fraction", "Crop", "Area (ha)"],
            state="readonly",
            width=20,
        )
        self.spatial_metric_combo.grid(row=0, column=0, padx=(0, 7))

        self.spatial_date_var = tk.StringVar(value="")
        self.spatial_date_combo = ttk.Combobox(
            spatial_controls,
            textvariable=self.spatial_date_var,
            values=[],
            state="disabled",
            width=13,
        )
        self.spatial_date_combo.grid(row=0, column=1, padx=(0, 7))

        ttk.Button(
            spatial_controls,
            text="Export GeoPackage",
            command=self.export_spatial_results,
            style="Secondary.TButton",
        ).grid(row=0, column=2)

        self.spatial_metric_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_spatial_controls())
        self.spatial_date_combo.bind("<<ComboboxSelected>>", lambda _e: self._plot_spatial_view())

        spatial_card = ttk.Frame(self.tab_spatial, style="Card.TFrame", padding=8)
        spatial_card.pack(fill="both", expand=True)

        fig3 = Figure(figsize=(8.5, 5.8), dpi=100, facecolor="white")
        self.ax_spatial = fig3.add_subplot(111)
        self.ax_spatial.set_title("Load parcel polygons", pad=12)
        self.ax_spatial.set_axis_off()

        self.canvas_spatial = FigureCanvasTkAgg(fig3, master=spatial_card)
        self.canvas_spatial.draw()
        self.canvas_spatial.get_tk_widget().pack(fill="both", expand=True)
        self.canvas_spatial.mpl_connect("button_press_event", self._on_spatial_click)

        self.spatial_info_var = tk.StringVar(
            value="Spatial view will update as parcel results become available."
        )
        ttk.Label(
            self.tab_spatial,
            textvariable=self.spatial_info_var,
            style="Info.TLabel",
            justify="left",
        ).pack(fill="x", pady=(7, 0))

        # QA remains internal only.
        self.info_text = None

    def _available_spatial_dates(self, metric):
        dates = set()
        if metric in {"NDVI P50", "Valid pixel fraction"}:
            for df in self.ndvi_results.values():
                if df is None or df.empty:
                    continue
                raw_dates = pd.to_datetime(df["date_start"], utc=True, errors="coerce").dropna()
                for d in raw_dates:
                    dates.add(d.tz_convert(None).normalize())
        elif metric == "Processed NDVI":
            for result in self.temporal_results.values():
                if not result:
                    continue
                df = result.get("daily")
                if df is None or df.empty:
                    continue
                for d in pd.to_datetime(df["date"], errors="coerce").dropna():
                    dates.add(pd.Timestamp(d).normalize())
        return sorted(dates)

    def _refresh_spatial_controls(self):
        if not hasattr(self, "spatial_date_combo"):
            return
        metric = self.spatial_metric_var.get()
        dates = self._available_spatial_dates(metric)

        if metric in {"Crop", "Area (ha)"}:
            self.spatial_date_combo.configure(state="disabled", values=[])
            self.spatial_date_var.set("")
        else:
            labels = [d.strftime("%Y-%m-%d") for d in dates]
            self.spatial_date_combo.configure(
                state="readonly" if labels else "disabled",
                values=labels,
            )
            if self.spatial_date_var.get() not in labels:
                self.spatial_date_var.set(labels[-1] if labels else "")

        self._plot_spatial_view()

    def _spatial_values(self):
        if self.gdf is None or self.gdf.empty:
            return None, None

        metric = self.spatial_metric_var.get()
        values = []
        date_value = None
        if self.spatial_date_var.get():
            try:
                date_value = pd.Timestamp(self.spatial_date_var.get()).normalize()
            except Exception:
                date_value = None

        for _, row in self.gdf.iterrows():
            pid = str(row["parcel_id"])
            value = np.nan

            if metric == "Area (ha)":
                value = float(row["area_ha"])
            elif metric == "Crop":
                value = str(row["crop"])
            elif metric in {"NDVI P50", "Valid pixel fraction"} and date_value is not None:
                df = self.ndvi_results.get(pid)
                if df is not None and not df.empty:
                    dates = (
                        pd.to_datetime(df["date_start"], utc=True, errors="coerce")
                        .dt.tz_convert(None)
                        .dt.normalize()
                    )
                    hit = df.loc[dates == date_value]
                    if not hit.empty:
                        col = "ndvi_p50" if metric == "NDVI P50" else "valid_fraction_pct"
                        value = pd.to_numeric(hit.iloc[-1][col], errors="coerce")
            elif metric == "Processed NDVI" and date_value is not None:
                result = self.temporal_results.get(pid)
                if result:
                    df = result.get("daily")
                    if df is not None and not df.empty:
                        dates = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
                        hit = df.loc[dates == date_value]
                        if not hit.empty:
                            value = pd.to_numeric(
                                hit.iloc[-1]["ndvi_reconstructed_daily"],
                                errors="coerce",
                            )
            values.append(value)

        return metric, values

    def _plot_spatial_view(self):
        if not hasattr(self, "ax_spatial"):
            return

        # IMPORTANT:
        # Clear the *whole figure*, not only the map axes. Previous colorbar
        # axes remain attached to the Matplotlib Figure when ax.clear() is used,
        # which was the cause of the accumulating legends/colorbars.
        fig = self.canvas_spatial.figure
        fig.clear()
        self.ax_spatial = fig.add_subplot(111)

        if self.gdf is None or self.gdf.empty:
            self.ax_spatial.set_title("Load parcel polygons", pad=12)
            self.ax_spatial.set_axis_off()
            self.canvas_spatial.draw_idle()
            return

        metric, values = self._spatial_values()
        plot_gdf = self.gdf.copy()
        plot_gdf["_display"] = values

        try:
            # ---------------------------------------------------------
            # Categorical variable: Crop
            # ---------------------------------------------------------
            if metric == "Crop":
                categories = [
                    str(v) for v in plot_gdf["_display"].dropna().unique()
                    if str(v).strip()
                ]

                if not categories:
                    plot_gdf.boundary.plot(
                        ax=self.ax_spatial,
                        edgecolor="#607D8B",
                        linewidth=1.1,
                    )
                else:
                    cmap = get_cmap("tab20", max(len(categories), 1))
                    category_to_code = {
                        cat: i for i, cat in enumerate(sorted(categories))
                    }
                    plot_gdf["_class_code"] = plot_gdf["_display"].map(
                        category_to_code
                    )

                    plot_gdf.plot(
                        column="_class_code",
                        categorical=True,
                        cmap=cmap,
                        legend=False,
                        ax=self.ax_spatial,
                        edgecolor="#455A64",
                        linewidth=0.9,
                        missing_kwds={"color": "#ECEFF1"},
                    )

                    handles = [
                        Patch(
                            facecolor=cmap(i),
                            edgecolor="#455A64",
                            label=cat,
                        )
                        for cat, i in category_to_code.items()
                    ]
                    self.ax_spatial.legend(
                        handles=handles,
                        title="Crop",
                        loc="upper right",
                        frameon=True,
                        fontsize=8,
                        title_fontsize=9,
                    )

            # ---------------------------------------------------------
            # Numeric variables: use ONE compact DISCRETE legend
            # ---------------------------------------------------------
            else:
                numeric = pd.to_numeric(
                    plot_gdf["_display"], errors="coerce"
                )
                plot_gdf["_display"] = numeric
                valid = numeric.dropna()

                if valid.empty:
                    plot_gdf.boundary.plot(
                        ax=self.ax_spatial,
                        edgecolor="#607D8B",
                        linewidth=1.1,
                    )
                else:
                    vmin = float(valid.min())
                    vmax = float(valid.max())

                    # For only one unique numeric value, draw one class.
                    if np.isclose(vmin, vmax):
                        boundaries = np.array(
                            [vmin - 0.5, vmax + 0.5], dtype=float
                        )
                    else:
                        # Four classes provide a compact legend while preserving
                        # meaningful differentiation for small parcel sets.
                        n_classes = min(4, max(2, int(valid.nunique())))
                        boundaries = np.linspace(
                            vmin, vmax, n_classes + 1
                        )

                    n_intervals = len(boundaries) - 1
                    cmap = get_cmap("viridis", n_intervals)
                    norm = BoundaryNorm(
                        boundaries, cmap.N, clip=True
                    )

                    plot_gdf.plot(
                        column="_display",
                        cmap=cmap,
                        norm=norm,
                        ax=self.ax_spatial,
                        edgecolor="#455A64",
                        linewidth=0.9,
                        missing_kwds={"color": "#ECEFF1"},
                    )

                    # One legend only: discrete colour swatches and intervals.
                    labels = []
                    handles = []

                    def _fmt_value(x):
                        if metric in {"NDVI P50", "Processed NDVI"}:
                            return f"{x:.2f}"
                        if metric == "Valid pixel fraction":
                            return f"{x:.0f}"
                        if metric == "Area (ha)":
                            return f"{x:.1f}"
                        return f"{x:.2f}"

                    for i in range(n_intervals):
                        lo = boundaries[i]
                        hi = boundaries[i + 1]
                        if n_intervals == 1:
                            label = _fmt_value(valid.iloc[0])
                        elif i == n_intervals - 1:
                            label = f"{_fmt_value(lo)}–{_fmt_value(hi)}"
                        else:
                            label = f"{_fmt_value(lo)}–<{_fmt_value(hi)}"

                        handles.append(
                            Patch(
                                facecolor=cmap(i),
                                edgecolor="#455A64",
                                label=label,
                            )
                        )
                        labels.append(label)

                    legend_title = {
                        "NDVI P50": "NDVI P50",
                        "Processed NDVI": "Reconstructed NDVI",
                        "Valid pixel fraction": "Valid pixels (%)",
                        "Area (ha)": "Area (ha)",
                    }.get(metric, metric)

                    self.ax_spatial.legend(
                        handles=handles,
                        title=legend_title,
                        loc="upper right",
                        frameon=True,
                        fontsize=8,
                        title_fontsize=9,
                        borderpad=0.7,
                        labelspacing=0.45,
                        handlelength=1.4,
                        handleheight=0.9,
                    )

            # Highlight selected parcel.
            selected = self._selected_main_parcel_id()
            if selected is not None:
                sel = plot_gdf[
                    plot_gdf["parcel_id"].astype(str)
                    == str(selected)
                ]
                if not sel.empty:
                    sel.boundary.plot(
                        ax=self.ax_spatial,
                        edgecolor="black",
                        linewidth=2.6,
                    )

            # Parcel labels.
            for _, row in plot_gdf.iterrows():
                try:
                    p = row.geometry.representative_point()
                    self.ax_spatial.text(
                        p.x,
                        p.y,
                        str(row["parcel_id"]),
                        fontsize=8,
                        ha="center",
                        va="center",
                    )
                except Exception:
                    pass

            date_txt = self.spatial_date_var.get()
            title = metric + (
                f" | {date_txt}" if date_txt else ""
            )
            self.ax_spatial.set_title(title, pad=10)
            self.ax_spatial.set_aspect(
                "equal", adjustable="datalim"
            )
            self.ax_spatial.set_axis_off()

            available_n = int(pd.Series(values).notna().sum())
            self.spatial_info_var.set(
                f"{available_n}/{len(plot_gdf)} parcel(s) have data "
                "for this view. Click a polygon to synchronize parcel "
                "selection."
            )

        except Exception as exc:
            logging.exception("Spatial plot failed")
            self.ax_spatial.set_title(
                f"Spatial view error: {exc}"
            )
            self.ax_spatial.set_axis_off()

        fig.tight_layout()
        self.canvas_spatial.draw_idle()

    def _on_spatial_click(self, event):
        if (
            self.gdf is None or self.gdf.empty
            or event.inaxes != self.ax_spatial
            or event.xdata is None or event.ydata is None
        ):
            return

        point = Point(event.xdata, event.ydata)
        for idx, row in self.gdf.iterrows():
            try:
                if row.geometry.covers(point):
                    self._select_parcel_by_id(str(row["parcel_id"]))
                    return
            except Exception:
                continue

    def _select_parcel_by_id(self, parcel_id):
        if self.gdf is None:
            return
        matches = self.gdf.index[
            self.gdf["parcel_id"].astype(str) == str(parcel_id)
        ].tolist()
        if not matches:
            return
        target = str(matches[0])
        if target in self.tree.get_children():
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
            self._on_parcel_selected()

    def _build_spatial_export_gdf(self):
        if self.gdf is None or self.gdf.empty:
            raise ValueError("No parcels are loaded.")

        out = self.gdf.copy()
        ndvi_mean, ndvi_last = [], []
        kc_mean, kc_last, kc_model = [], [], []
        cwr_total, iwr_total = [], []

        for _, row in out.iterrows():
            pid = str(row["parcel_id"])

            raw = self.ndvi_results.get(pid)
            if raw is not None and not raw.empty:
                accepted = raw.loc[
                    raw["accepted"] & raw["ndvi_p50"].notna(),
                    "ndvi_p50",
                ]
                ndvi_mean.append(float(accepted.mean()) if len(accepted) else np.nan)
                ndvi_last.append(float(accepted.iloc[-1]) if len(accepted) else np.nan)
            else:
                ndvi_mean.append(np.nan)
                ndvi_last.append(np.nan)

            kdf = self.kc_results.get(pid)
            if kdf is not None and not kdf.empty:
                kc_mean.append(float(kdf["Kc"].mean()))
                kc_last.append(float(kdf["Kc"].iloc[-1]))
            else:
                kc_mean.append(np.nan)
                kc_last.append(np.nan)

            mid = self.kc_assignments.get(pid)
            kc_model.append(KC_CATALOG[mid]["label"] if mid in KC_CATALOG else "")

            wdf = self.water_results.get(pid)
            if wdf is not None and not wdf.empty:
                cwr_total.append(float(wdf["ETc"].sum()))
                iwr_total.append(
                    float(wdf["IWR_net"].sum()) if "IWR_net" in wdf.columns else np.nan
                )
            else:
                cwr_total.append(np.nan)
                iwr_total.append(np.nan)

        out["ndvi_p50_mean"] = ndvi_mean
        out["ndvi_p50_last"] = ndvi_last
        out["kc_mean"] = kc_mean
        out["kc_last"] = kc_last
        out["kc_model"] = kc_model
        out["cwr_total_mm"] = cwr_total
        out["iwr_net_total_mm"] = iwr_total
        out["app_version"] = APP_VERSION
        return out

    def export_spatial_results(self):
        if self.gdf is None or self.gdf.empty:
            messagebox.showwarning("Spatial export", "Load parcels first.")
            return

        path = filedialog.asksaveasfilename(
            title="Export spatial results",
            defaultextension=".gpkg",
            initialfile="CropWater_RS_results.gpkg",
            filetypes=[("GeoPackage", "*.gpkg")],
        )
        if not path:
            return

        try:
            out = self._build_spatial_export_gdf()
            out.to_file(path, layer="cropwater_results", driver="GPKG")
            logging.info("Spatial results exported: %s", path)
            messagebox.showinfo("Spatial export", f"GeoPackage saved successfully:\n{path}")
        except Exception as exc:
            logging.exception("Spatial export failed")
            messagebox.showerror("Spatial export", str(exc))

    def _set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    def _set_progress(self, value, text=None):
        """Update progress bar and status text safely from the Tk main thread."""
        value = max(0.0, min(100.0, float(value)))
        self.progress_var.set(value)
        if text is not None:
            self.progress_text_var.set(text)
        self.update_idletasks()

    def _set_plot_period_from_inputs(self):
        """Synchronize the NDVI plot x-axis with the user-selected date range."""
        try:
            start = pd.Timestamp(self.start_var.get())
            end = pd.Timestamp(self.end_var.get())
            if end < start:
                return
            # Use exactly the date range selected by the user.
            self.ax.set_xlim(start, end)
        except Exception:
            pass

    def _refresh_plot_period(self):
        self._set_plot_period_from_inputs()
        self.canvas.draw_idle()

    def _recalculate_valid_threshold(self):
        """Reclassify stored NDVI intervals using the current valid-pixel threshold."""
        try:
            valid_min = float(self.valid_pct_var.get())
        except (tk.TclError, ValueError):
            return

        if not 0 <= valid_min <= 100:
            return

        # Recalculate all parcel results already stored in memory.
        for parcel_id, df in self.ndvi_results.items():
            if df is not None and not df.empty and "valid_fraction_pct" in df.columns:
                df["accepted"] = df["valid_fraction_pct"] >= valid_min
                self.temporal_results.clear()
                self.temporal_quality.clear()
                self.kc_results.clear()
                self.water_results.clear()

        # Refresh only the currently selected parcel on screen.
        idx = self._selected_index()
        if idx is None or self.gdf is None:
            return

        parcel_id = self.gdf.loc[idx, "parcel_id"]
        if parcel_id in self.ndvi_results:
            df = self.ndvi_results[parcel_id]
            if self.temporal_results:
                self._process_temporal_all_local(show_message=False)
            self._plot_ndvi(df)
            self._update_temporal_diagnostics(parcel_id)
            accepted = int(df["accepted"].sum()) if not df.empty else 0
            self._set_status(
                f"{parcel_id}: QA recalculated at {valid_min:.1f}% "
                f"({accepted}/{len(df)} intervals accepted)"
            )

    def _show_empty_parcel_plot(self, parcel_id, crop):
        """Clear the previous parcel curve when the new parcel has no NDVI result yet."""
        self.ax.clear()
        self.ax.set_ylim(0.0, 1.0)
        self.ax.set_yticks(np.linspace(0.0, 1.0, 6))
        self._set_plot_period_from_inputs()
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("NDVI")
        self.ax.set_title(
            f"{parcel_id} — {crop} | No NDVI series calculated yet"
        )
        self.ax.grid(True, alpha=0.25)
        start_plot = pd.Timestamp(self.start_var.get())
        end_plot = pd.Timestamp(self.end_var.get())
        span_days = max((end_plot - start_plot).days, 1)
        if span_days <= 100:
            self.ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%Y"))
        elif span_days <= 550:
            self.ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        else:
            self.ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        self.canvas.figure.tight_layout()
        self.canvas.draw_idle()

    def _show_empty_parcel_info(self, parcel_id, crop):
        """QA is retained internally; no separate QA panel is shown in v0.8."""
        if self.info_text is None:
            return
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert(
            "1.0",
            (
                f"Parcel: {parcel_id}\n"
                f"Crop: {crop}\n\n"
                "No Sentinel-2 NDVI series has been calculated for this parcel yet.\n"
                "Use 'Calculate NDVI for all parcels' to process the complete parcel set."
            ),
        )
        self.info_text.configure(state="disabled")

    @staticmethod
    def _find_column_case_insensitive(columns, candidates):
        """Return the first matching source column, ignoring case/whitespace."""
        lookup = {
            str(col).strip().casefold(): col
            for col in columns
        }
        for candidate in candidates:
            hit = lookup.get(str(candidate).strip().casefold())
            if hit is not None:
                return hit
        return None

    @staticmethod
    def _normalize_crop_name(value):
        """Normalize input crop labels to CropWater-RS controlled vocabulary."""
        if pd.isna(value):
            return "OTHER"

        raw = str(value).strip()
        if not raw:
            return "OTHER"

        # Normalize repeated spaces and uppercase before alias lookup.
        normalized = " ".join(raw.upper().split())
        return CROP_ALIASES.get(normalized, "OTHER")

    def _update_crop_labelling_mode(self):
        """Enable the controls appropriate to the selected crop-labelling mode."""
        mode = (
            self.crop_label_mode_var.get()
            if hasattr(self, "crop_label_mode_var")
            else "manual"
        )

        if mode == "attributes":
            if hasattr(self, "id_field_combo"):
                self.id_field_combo.configure(
                    state="readonly" if self.source_gdf is not None else "disabled"
                )
            if hasattr(self, "crop_field_combo"):
                self.crop_field_combo.configure(
                    state="readonly" if self.source_gdf is not None else "disabled"
                )
            if hasattr(self, "apply_fields_btn"):
                self.apply_fields_btn.configure(
                    state="normal" if self.source_gdf is not None else "disabled"
                )
            if hasattr(self, "crop_combo"):
                self.crop_combo.configure(state="disabled")
            if hasattr(self, "assign_crop_btn"):
                self.assign_crop_btn.configure(state="disabled")
            if hasattr(self, "crop_mode_info_var"):
                self.crop_mode_info_var.set(
                    "Attribute mode: select the vector columns containing parcel IDs "
                    "and crop labels, then apply them to all parcels."
                )
        else:
            if hasattr(self, "id_field_combo"):
                self.id_field_combo.configure(state="disabled")
            if hasattr(self, "crop_field_combo"):
                self.crop_field_combo.configure(state="disabled")
            if hasattr(self, "apply_fields_btn"):
                self.apply_fields_btn.configure(state="disabled")
            if hasattr(self, "crop_combo"):
                self.crop_combo.configure(state="readonly")
            if hasattr(self, "assign_crop_btn"):
                self.assign_crop_btn.configure(state="normal")
            if hasattr(self, "crop_mode_info_var"):
                self.crop_mode_info_var.set(
                    "Manual mode: the parcel list below remains visible. Select any parcel, "
                    "choose its crop, and press Assign. Parcel IDs are still imported "
                    "automatically when available."
                )

    def _populate_vector_field_controls(self):
        """Populate ID/crop field selectors from the original imported layer."""
        if self.source_gdf is None:
            return

        columns = [
            str(c)
            for c in self.source_gdf.columns
            if str(c).lower() != "geometry"
        ]

        id_values = ["<Auto>", "<Generate>"] + columns
        crop_values = ["<Auto>", "<Manual / OTHER>"] + columns

        self.id_field_combo.configure(values=id_values)
        self.crop_field_combo.configure(values=crop_values)

        detected_id = self._find_column_case_insensitive(
            self.source_gdf.columns,
            ["parcel_id", "ID"],
        )
        detected_crop = self._find_column_case_insensitive(
            self.source_gdf.columns,
            ["crop", "CROPS"],
        )

        self.id_field_var.set(
            str(detected_id) if detected_id is not None else "<Auto>"
        )
        self.crop_field_var.set(
            str(detected_crop) if detected_crop is not None else "<Auto>"
        )

        self._update_crop_labelling_mode()

    def _prepare_vector_attributes(
        self,
        gdf,
        id_field="<Auto>",
        crop_field="<Manual / OTHER>",
    ):
        """
        Prepare stable internal parcel ID and crop fields.

        ``id_field`` may be <Auto>, <Generate>, or a source attribute.
        ``crop_field`` may be <Auto>, <Manual / OTHER>, or a source attribute.

        Source crop text is retained in ``crop_source``. Internal crop labels
        are normalized to the CropWater-RS controlled vocabulary.
        """
        columns = list(gdf.columns)

        # -------------------------
        # ID field
        # -------------------------
        if id_field == "<Generate>":
            id_col = None
        elif id_field == "<Auto>":
            id_col = self._find_column_case_insensitive(
                columns,
                ["parcel_id", "ID"],
            )
        else:
            id_col = id_field if id_field in columns else None
            if id_col is None:
                raise ValueError(
                    f"Selected ID field '{id_field}' is not present in the vector layer."
                )

        if id_col is None:
            gdf["parcel_id"] = [
                f"P{i+1:05d}" for i in range(len(gdf))
            ]
            id_note = "Generated sequential parcel IDs"
        else:
            raw_ids = gdf[id_col].copy()
            ids = raw_ids.astype("string").str.strip()

            missing = (
                ids.isna()
                | (ids == "")
                | (ids.str.lower() == "nan")
                | (ids.str.lower() == "<na>")
            )

            if missing.any():
                used = set(
                    ids[~missing]
                    .astype(str)
                    .tolist()
                )
                counter = 1
                for idx in gdf.index[missing]:
                    while True:
                        candidate = f"P{counter:05d}"
                        counter += 1
                        if candidate not in used:
                            break
                    ids.loc[idx] = candidate
                    used.add(candidate)

            gdf["parcel_id"] = ids.astype(str)
            id_note = f"Parcel IDs imported from '{id_col}'"

        # -------------------------
        # Crop field
        # -------------------------
        if crop_field == "<Manual / OTHER>":
            crop_col = None
        elif crop_field == "<Auto>":
            crop_col = self._find_column_case_insensitive(
                columns,
                ["crop", "CROPS"],
            )
        else:
            crop_col = crop_field if crop_field in columns else None
            if crop_col is None:
                raise ValueError(
                    f"Selected crop field '{crop_field}' is not present in the vector layer."
                )

        if crop_col is None:
            gdf["crop_source"] = ""
            gdf["crop"] = "OTHER"
            crop_note = "Manual crop labelling selected"
        else:
            source_crop = (
                gdf[crop_col]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            gdf["crop_source"] = source_crop
            gdf["crop"] = gdf[crop_col].apply(
                self._normalize_crop_name
            )
            crop_note = f"Crop labels imported from '{crop_col}'"

        return gdf, id_note, crop_note

    def apply_vector_fields(self):
        """Apply user-selected ID and crop attributes to the loaded parcels."""
        if self.source_gdf is None:
            messagebox.showwarning(
                "Vector fields",
                "Load a parcel file first.",
            )
            return

        if self.crop_label_mode_var.get() != "attributes":
            messagebox.showwarning(
                "Vector fields",
                "Select 'Use vector attributes' first.",
            )
            return

        try:
            previous_gdf = self.gdf.copy() if self.gdf is not None else None

            # Rebuild from the untouched imported layer to avoid losing original
            # values when a source field itself is called 'crop' or 'parcel_id'.
            gdf = self.source_gdf.copy()
            gdf, id_note, crop_note = self._prepare_vector_attributes(
                gdf,
                id_field=self.id_field_var.get(),
                crop_field=self.crop_field_var.get(),
            )

            if gdf["parcel_id"].astype(str).duplicated().any():
                dup_ids = (
                    gdf.loc[
                        gdf["parcel_id"].astype(str).duplicated(keep=False),
                        "parcel_id",
                    ]
                    .astype(str)
                    .unique()
                    .tolist()
                )
                raise ValueError(
                    "Duplicate parcel IDs detected: " + ", ".join(dup_ids)
                )

            # Keep area already computed if possible; otherwise recompute.
            if previous_gdf is not None and "area_ha" in previous_gdf.columns:
                gdf["area_ha"] = previous_gdf["area_ha"].to_numpy()
            else:
                area_crs = gdf.estimate_utm_crs()
                if area_crs is None:
                    raise ValueError(
                        "Could not determine a projected CRS for area calculation."
                    )
                gdf["area_ha"] = (
                    gdf.to_crs(area_crs).geometry.area / 10000.0
                )

            self.gdf = gdf.reset_index(drop=True)

            # Attribute remapping changes parcel/crop identity. Downstream
            # results are invalidated to prevent accidental cross-assignment.
            self.ndvi_results.clear()
            self.temporal_results.clear()
            self.temporal_quality.clear()
            self.quant_results.clear()
            self.quant_water_summary.clear()
            self.kc_assignments.clear()
            self.kc_results.clear()
            self.water_results.clear()

            self._refresh_tree()
            self._refresh_kc_tree()
            self._refresh_spatial_controls()

            if len(self.gdf):
                first_id = str(self.gdf.loc[0, "parcel_id"])
                first_crop = str(self.gdf.loc[0, "crop"]).upper()
                self._show_empty_parcel_plot(first_id, first_crop)
                self._plot_selected_water()
                self._update_water_summary()

            other_count = int(
                (self.gdf["crop"].astype(str).str.upper() == "OTHER").sum()
            )

            msg = f"{id_note} | {crop_note}"
            if other_count:
                msg += f" | {other_count} crop label(s) mapped to OTHER"

            self._set_status(msg)
            logging.info("Vector field mapping applied | %s", msg)

            messagebox.showinfo(
                "Vector fields",
                "Vector attributes applied successfully.\n\n" + msg,
            )
        except Exception as exc:
            logging.exception("Applying vector field mapping failed")
            messagebox.showerror(
                "Vector fields",
                str(exc),
            )

    def import_parcels(self):
        path = filedialog.askopenfilename(
            title="Select polygon file",
            filetypes=[
                ("Geospatial vector", "*.shp *.gpkg *.geojson *.json"),
                ("Shapefile", "*.shp"),
                ("GeoPackage", "*.gpkg"),
                ("GeoJSON", "*.geojson *.json"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            gdf = gpd.read_file(path)
            if gdf.empty:
                raise ValueError("The vector file contains no features.")
            if gdf.crs is None:
                raise ValueError("The input layer has no CRS.")
            # No fixed parcel-count limit is imposed. Very large layers are
            # processed sequentially, so total runtime depends on parcel count,
            # date range, and CDSE response time.

            # Only polygonal features
            geom_types = set(gdf.geometry.geom_type.dropna().unique())
            allowed = {"Polygon", "MultiPolygon"}
            if not geom_types.issubset(allowed):
                raise ValueError(
                    "All input geometries must be Polygon or MultiPolygon. "
                    f"Found: {', '.join(sorted(geom_types))}"
                )

            gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
            if not gdf.geometry.is_valid.all():
                # Conservative repair supported by modern shapely/geopandas
                try:
                    gdf["geometry"] = gdf.geometry.make_valid()
                except Exception:
                    gdf["geometry"] = gdf.buffer(0)

            # Preserve untouched source attributes so users can later switch
            # between manual and attribute-based labelling without reloading.
            self.source_gdf = gdf.copy()
            self._populate_vector_field_controls()

            # Parcel IDs may still be auto-detected in manual crop mode.
            # Crop labels are imported only when the user explicitly chooses
            # the attribute-based labelling workflow.
            if self.crop_label_mode_var.get() == "attributes":
                selected_id_field = self.id_field_var.get()
                selected_crop_field = self.crop_field_var.get()
            else:
                selected_id_field = "<Auto>"
                selected_crop_field = "<Manual / OTHER>"

            gdf, id_note, crop_note = self._prepare_vector_attributes(
                gdf,
                id_field=selected_id_field,
                crop_field=selected_crop_field,
            )

            # parcel_id is the internal key for all result dictionaries.
            # Duplicates would silently overwrite parcel results.
            if gdf["parcel_id"].astype(str).duplicated().any():
                dup_ids = (
                    gdf.loc[
                        gdf["parcel_id"].astype(str).duplicated(keep=False),
                        "parcel_id",
                    ]
                    .astype(str)
                    .unique()
                    .tolist()
                )
                raise ValueError(
                    "Duplicate parcel IDs detected: " + ", ".join(dup_ids)
                )

            # Re-check geometry after make_valid()/buffer(0).
            bad_geom = (
                gdf.geometry.isna()
                | gdf.geometry.is_empty
                | ~gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
                | ~gdf.geometry.is_valid
            )
            if bad_geom.any():
                raise ValueError(
                    "All features must remain valid non-empty Polygon or MultiPolygon geometries after repair."
                )

            # Area in a locally appropriate projected CRS.
            area_crs = gdf.estimate_utm_crs()
            if area_crs is None:
                raise ValueError("Could not determine a projected CRS for area calculation.")
            areas = gdf.to_crs(area_crs).geometry.area / 10000.0
            gdf["area_ha"] = areas

            self.gdf = gdf.reset_index(drop=True)
            self.current_file = path
            self.file_var.set(path)
            self.ndvi_results.clear()
            self.temporal_results.clear()
            self.temporal_quality.clear()
            self.quant_results.clear()
            self.quant_water_summary.clear()
            self.kc_assignments.clear()
            self.kc_results.clear()
            self.water_results.clear()

            # Populate both parcel views before synchronizing any selection.
            self._refresh_tree()
            self._refresh_kc_tree()
            self._update_main_navigation_labels()

            if (
                self.crop_label_mode_var.get() == "manual"
                and len(self.gdf)
                and self.tree.get_children()
            ):
                first_item = self.tree.get_children()[0]
                self.tree.selection_set(first_item)
                self.tree.focus(first_item)
                self.tree.see(first_item)

            if len(self.gdf):
                first_id = str(self.gdf.loc[0, "parcel_id"])
                first_crop = str(self.gdf.loc[0, "crop"]).upper()

                # Set Kc table to the same initial parcel without invoking
                # handlers manually.
                if "0" in self.kc_tree.get_children():
                    self.kc_tree.selection_set("0")
                    self.kc_tree.focus("0")

                self._show_empty_parcel_plot(first_id, first_crop)
                self._plot_selected_water()
                self._update_water_summary()
            self._refresh_spatial_controls()

            other_count = int(
                (self.gdf["crop"].astype(str).str.upper() == "OTHER").sum()
            )
            mode_note = (
                "Attribute crop labelling"
                if self.crop_label_mode_var.get() == "attributes"
                else "Manual crop labelling"
            )
            status_msg = (
                f"{len(self.gdf)} parcel(s) loaded | "
                f"{mode_note} | {id_note} | {crop_note}"
            )
            if other_count:
                status_msg += f" | {other_count} crop label(s) mapped to OTHER"

            self._set_status(status_msg)
            logging.info(
                "Loaded %d parcel(s) from %s | %s | %s | OTHER=%d",
                len(self.gdf),
                path,
                id_note,
                crop_note,
                other_count,
            )

        except Exception as exc:
            messagebox.showerror("Import error", str(exc))

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if self.gdf is None:
            return

        for idx, row in self.gdf.iterrows():
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    row["parcel_id"],
                    f"{row['area_ha']:.2f}",
                    row["crop"],
                ),
            )

        if len(self.gdf):
            self.tree.selection_set("0")
            self.tree.focus("0")

        if hasattr(self, "ndvi_nav_var") or hasattr(self, "water_nav_var"):
            self._update_main_navigation_labels()

    def _navigate_main_parcel(self, step):
        """Move to previous/next parcel and synchronize every parcel view."""
        if self.gdf is None or len(self.gdf) == 0:
            return

        items = list(self.tree.get_children())
        if not items:
            return

        current = self.tree.selection()
        if current and current[0] in items:
            idx = items.index(current[0])
        else:
            idx = 0

        new_idx = (idx + int(step)) % len(items)
        target = items[new_idx]

        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)

        # Treeview normally fires <<TreeviewSelect>>, but update directly as
        # well if the target was already selected.
        if current == (target,):
            self._on_parcel_selected()

    def _update_main_navigation_labels(self, parcel_id=None):
        if self.gdf is None or len(self.gdf) == 0:
            label = "Parcel — / —"
        else:
            items = list(self.tree.get_children())
            if not items:
                label = "Parcel — / —"
            else:
                pid = str(parcel_id) if parcel_id is not None else None
                target = None

                if pid is not None:
                    matches = self.gdf.index[
                        self.gdf["parcel_id"].astype(str) == pid
                    ].tolist()
                    if matches:
                        candidate = str(matches[0])
                        if candidate in items:
                            target = candidate

                if target is None:
                    sel = self.tree.selection()
                    target = sel[0] if sel and sel[0] in items else items[0]

                pos = items.index(target) + 1
                display_pid = str(
                    self.gdf.loc[int(target), "parcel_id"]
                )
                label = f"{display_pid}  ({pos}/{len(items)})"

        if hasattr(self, "ndvi_nav_var"):
            self.ndvi_nav_var.set(label)
        if hasattr(self, "water_nav_var"):
            self.water_nav_var.set(label)

    def _selected_index(self):
        selected = self.tree.selection()
        if not selected:
            return None
        return int(selected[0])

    def _on_parcel_selected(self, _event=None):
        idx = self._selected_index()
        if idx is None or self.gdf is None:
            return

        crop = str(self.gdf.loc[idx, "crop"]).upper()
        if crop in CROPS:
            self.crop_var.set(crop)
        else:
            self.crop_var.set("OTHER")

        parcel_id = str(self.gdf.loc[idx, "parcel_id"])
        self._update_main_navigation_labels(parcel_id)

        if parcel_id in self.ndvi_results:
            self._plot_ndvi(self.ndvi_results[parcel_id])
            self._update_temporal_diagnostics(parcel_id)
        else:
            self._show_empty_parcel_plot(parcel_id, crop)
            self.temporal_diag_var.set("Fit diagnostics: not calculated")

        # Synchronize the Kc table only when its selection is actually different.
        # This avoids a Tkinter <<TreeviewSelect>> feedback loop.
        self._sync_kc_selection_to_parcel(parcel_id)

        self._plot_selected_water()
        self._update_water_summary()
        self._plot_spatial_view()

        if (
            hasattr(self, "quant_tree")
            and parcel_id in self.quant_tree.get_children()
        ):
            current = self.quant_tree.selection()
            if current != (parcel_id,):
                self.quant_tree.selection_set(parcel_id)
                self.quant_tree.focus(parcel_id)
            self._plot_quant_parcel(parcel_id)

    def assign_crop(self):
        if (
            hasattr(self, "crop_label_mode_var")
            and self.crop_label_mode_var.get() != "manual"
        ):
            messagebox.showwarning(
                "Crop",
                "Manual crop assignment is disabled while 'Use vector attributes' is selected.",
            )
            return

        idx = self._selected_index()
        if idx is None or self.gdf is None:
            messagebox.showwarning("Crop", "Select a parcel first.")
            return
        parcel_id = str(self.gdf.loc[idx, "parcel_id"])
        new_crop = self.crop_var.get()
        old_crop = str(self.gdf.loc[idx, "crop"]).upper()

        self.gdf.loc[idx, "crop"] = new_crop
        if "crop_source" in self.gdf.columns:
            self.gdf.loc[idx, "crop_source"] = new_crop

        if str(new_crop).upper() != old_crop:
            self.kc_assignments.pop(parcel_id, None)
            self._invalidate_from_kc(parcel_id)

        self._refresh_tree()
        self._refresh_kc_tree()
        self.tree.selection_set(str(idx))
        self.tree.focus(str(idx))
        self._sync_kc_selection_to_parcel(parcel_id)
        self._refresh_spatial_controls()

    def _make_config(self):
        client_id = self.client_id_var.get().strip()
        client_secret = self.client_secret_var.get().strip()

        if not client_id or not client_secret:
            raise ValueError(
                "Enter the CDSE Sentinel Hub Client ID and Client Secret."
            )

        config = SHConfig()
        config.sh_client_id = client_id
        config.sh_client_secret = client_secret
        config.sh_token_url = CDSE_TOKEN_URL
        config.sh_base_url = CDSE_BASE_URL
        return config

    def configure_cdse(self):
        try:
            self.config_cdse = self._make_config()

            # The first authenticated request is intentionally a lightweight
            # one-parcel/one-day statistics request only when data exist.
            # Here we validate the configuration object and credentials presence.
            # Actual authentication is performed by sentinelhub-py on run.
            self._set_status("CDSE configuration ready")
            messagebox.showinfo(
                "CDSE",
                "Configuration created successfully.\n\n"
                "The credentials will be authenticated when the first Sentinel Hub "
                "request is executed. Credentials are not written to the source code.",
            )
        except Exception as exc:
            messagebox.showerror("CDSE configuration", str(exc))

    def run_ndvi(self):
        if self.gdf is None or self.gdf.empty:
            messagebox.showwarning("NDVI", "Load a parcel file first.")
            return

        try:
            start_date = self.start_var.get().strip()
            end_date = self.end_var.get().strip()
            pd.Timestamp(start_date)
            pd.Timestamp(end_date)
            if pd.Timestamp(end_date) < pd.Timestamp(start_date):
                raise ValueError("End date must be equal to or later than start date.")

            interval = self.interval_var.get()
            valid_min = float(self.valid_pct_var.get())
            self.config_cdse = self._make_config()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return

        self.run_btn.configure(state="disabled")
        self.ndvi_results.clear()

        self._set_status(
            f"Processing Sentinel-2 NDVI for {len(self.gdf)} parcel(s)..."
        )
        self._set_progress(0, f"Starting 0/{len(self.gdf)} parcels...")
        self._set_plot_period_from_inputs()
        self.canvas.draw_idle()

        # Copy the required inputs before starting the worker thread.
        gdf_work = self.gdf.copy()
        config = self.config_cdse

        thread = threading.Thread(
            target=self._run_all_ndvi_worker,
            args=(gdf_work, start_date, end_date, interval, valid_min, config),
            daemon=True,
        )
        thread.start()

    def _run_all_ndvi_worker(
        self, gdf_work, start_date, end_date, interval, valid_min, config
    ):
        total = len(gdf_work)
        errors = []

        for position, (_, row) in enumerate(gdf_work.iterrows(), start=1):
            parcel_id = str(row["parcel_id"])
            crop = str(row["crop"])

            try:
                base_pct = ((position - 1) / total) * 100.0
                self.after(
                    0,
                    lambda p=base_pct, pos=position, pid=parcel_id: self._set_progress(
                        p,
                        f"Parcel {pos}/{total}: {pid} — preparing geometry..."
                    ),
                )

                geom_wgs84 = gpd.GeoSeries(
                    [row.geometry], crs=gdf_work.crs
                ).to_crs(4326).iloc[0]

                geometry = Geometry(geom_wgs84, CRS.WGS84)

                self.after(
                    0,
                    lambda p=base_pct + (20.0 / total), pos=position, pid=parcel_id:
                    self._set_progress(
                        p,
                        f"Parcel {pos}/{total}: {pid} — building request..."
                    ),
                )

                aggregation = SentinelHubStatistical.aggregation(
                    evalscript=NDVI_EVALSCRIPT,
                    time_interval=(start_date, end_date),
                    aggregation_interval=interval,
                    resolution=(10, 10),
                )

                calculations = {
                    "ndvi": {
                        "statistics": {
                            "default": {
                                "percentiles": {
                                    "k": [25, 50, 75]
                                }
                            }
                        }
                    }
                }

                request = SentinelHubStatistical(
                    aggregation=aggregation,
                    input_data=[
                        SentinelHubStatistical.input_data(
                            DataCollection.SENTINEL2_L2A.define_from(
                                name="s2l2a_cdse",
                                service_url=CDSE_BASE_URL,
                            ),
                            other_args={
                                "dataFilter": {
                                    "mosaickingOrder": "leastCC"
                                }
                            },
                        )
                    ],
                    geometry=geometry,
                    calculations=calculations,
                    config=config,
                )

                self.after(
                    0,
                    lambda p=base_pct + (50.0 / total), pos=position, pid=parcel_id:
                    self._set_progress(
                        p,
                        f"Parcel {pos}/{total}: {pid} — processing in CDSE..."
                    ),
                )

                last_exc = None
                responses = None
                for attempt, wait_s in enumerate((0, 2, 5), start=1):
                    try:
                        if wait_s:
                            time.sleep(wait_s)
                        responses = request.get_data()
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                if last_exc is not None:
                    raise last_exc
                if not responses:
                    raise RuntimeError("CDSE returned no statistics response.")

                df = self._stats_response_to_df(responses[0])

                if not df.empty:
                    df["parcel_id"] = parcel_id
                    df["crop"] = crop
                    df["accepted"] = df["valid_fraction_pct"] >= valid_min
                else:
                    # Keep a valid empty dataframe structure for this parcel.
                    df["parcel_id"] = pd.Series(dtype="object")
                    df["crop"] = pd.Series(dtype="object")
                    df["accepted"] = pd.Series(dtype="bool")

                self.ndvi_results[parcel_id] = df

                pct = (position / total) * 100.0
                self.after(
                    0,
                    lambda p=pct, pos=position, pid=parcel_id: self._set_progress(
                        p,
                        f"Completed {pos}/{total} parcels — {pid}"
                    ),
                )

            except Exception as exc:
                errors.append((parcel_id, str(exc)))
                self.ndvi_results[parcel_id] = pd.DataFrame()

                pct = (position / total) * 100.0
                self.after(
                    0,
                    lambda p=pct, pos=position, pid=parcel_id:
                    self._set_progress(
                        p,
                        f"Parcel {pos}/{total}: {pid} failed; continuing..."
                    ),
                )

        self.after(0, lambda: self._all_ndvi_finished(errors))

    def _all_ndvi_finished(self, errors):
        self.run_btn.configure(state="normal")
        self.temporal_results.clear()
        self.temporal_quality.clear()
        self.kc_results.clear()
        self.water_results.clear()
        self.temporal_diag_var.set("Fit diagnostics: not calculated")
        self._set_progress(100, "All parcel requests completed")

        # Show the currently selected parcel, or the first parcel if none is selected.
        idx = self._selected_index()
        if idx is None and self.gdf is not None and len(self.gdf):
            idx = 0
            self.tree.selection_set("0")
            self.tree.focus("0")

        if idx is not None and self.gdf is not None:
            parcel_id = self.gdf.loc[idx, "parcel_id"]
            crop = str(self.gdf.loc[idx, "crop"]).upper()
            df = self.ndvi_results.get(parcel_id)

            if df is not None and not df.empty:
                self._plot_ndvi(df)
            else:
                self._show_empty_parcel_plot(parcel_id, crop)
    
        ok = sum(
            1 for df in self.ndvi_results.values()
            if df is not None and not df.empty
        )
        failed = len(errors)

        self._set_status(
            f"NDVI processing finished: {ok}/{len(self.gdf)} parcel(s) with results"
        )

        if errors:
            details = "\n".join(f"{pid}: {msg}" for pid, msg in errors[:5])
            if len(errors) > 5:
                details += f"\n... and {len(errors) - 5} more."
            messagebox.showwarning(
                "NDVI processing completed with warnings",
                f"Processing finished, but {failed} parcel(s) failed.\n\n{details}",
            )

    @staticmethod
    def _stats_response_to_df(response):
        records = []

        for item in response.get("data", []):
            interval = item.get("interval", {})
            outputs = item.get("outputs", {})
            ndvi_obj = outputs.get("ndvi", {})
            bands = ndvi_obj.get("bands", {})
            b0 = bands.get("B0", {})
            stats = b0.get("stats", {})
            percentiles = stats.get("percentiles", {})

            sample_count = stats.get("sampleCount", np.nan)
            no_data_count = stats.get("noDataCount", np.nan)

            if pd.notna(sample_count) and sample_count:
                valid_fraction = (
                    100.0 * max(sample_count - no_data_count, 0) / sample_count
                )
            else:
                valid_fraction = np.nan

            records.append(
                {
                    "date_start": pd.to_datetime(interval.get("from")),
                    "date_end": pd.to_datetime(interval.get("to")),
                    "ndvi_mean": stats.get("mean", np.nan),
                    "ndvi_stdev": stats.get("stDev", np.nan),
                    "ndvi_min": stats.get("min", np.nan),
                    "ndvi_max": stats.get("max", np.nan),
                    "ndvi_p25": percentiles.get("25.0", percentiles.get("25", np.nan)),
                    "ndvi_p50": percentiles.get("50.0", percentiles.get("50", np.nan)),
                    "ndvi_p75": percentiles.get("75.0", percentiles.get("75", np.nan)),
                    "sample_count": sample_count,
                    "no_data_count": no_data_count,
                    "valid_fraction_pct": valid_fraction,
                }
            )

        df = pd.DataFrame(records)
        if df.empty:
            return df

        df = df.sort_values("date_start").reset_index(drop=True)
        return df

    def _ndvi_success(self, parcel_id, df):
        self.run_btn.configure(state="normal")
        self._set_progress(100, "Completed")
        if df.empty:
            self._set_status("No NDVI intervals returned")
            messagebox.showwarning(
                "NDVI",
                "The request completed, but no temporal intervals were returned.",
            )
            return

        accepted = int(df["accepted"].sum())
        self._set_status(
            f"{parcel_id}: {accepted}/{len(df)} intervals accepted"
        )
        self._plot_ndvi(df)
        self._update_info(parcel_id, df)

    def _ndvi_error(self, msg):
        self.run_btn.configure(state="normal")
        self._set_progress(0, "Request failed")
        self._set_status("NDVI request failed")
        messagebox.showerror("CDSE / NDVI error", msg)

    def _refresh_selected_plot(self):
        idx = self._selected_index()
        if idx is None or self.gdf is None:
            return
        parcel_id = self.gdf.loc[idx, "parcel_id"]
        df = self.ndvi_results.get(parcel_id)
        if df is not None and not df.empty:
            self._plot_ndvi(df)
            self._update_temporal_diagnostics(parcel_id)

    def process_temporal_all(self):
        """Reconstruct/smooth all parcel NDVI series locally."""
        if not self.ndvi_results:
            messagebox.showwarning(
                "Temporal processing",
                "Calculate Sentinel-2 NDVI for the parcels first.",
            )
            return
        self._process_temporal_all_local(show_message=True)

    def _process_temporal_all_local(self, show_message=True):
        method = self.temporal_method_var.get()
        if method in {"Whittaker", "Savitzky-Golay"} and not SCIPY_AVAILABLE:
            messagebox.showerror(
                "Missing dependency",
                "SciPy is required for Whittaker and Savitzky-Golay processing.\n\n"
                "Install it with:\n    pip install scipy",
            )
            return

        try:
            lam = float(self.whittaker_lambda_var.get())
            if lam <= 0:
                raise ValueError("Whittaker λ must be greater than zero.")
            sg_window = int(self.sg_window_var.get())
            if sg_window < 5:
                raise ValueError("Savitzky-Golay window must be at least 5 days.")
        except Exception as exc:
            if show_message:
                messagebox.showerror("Temporal processing", str(exc))
            return

        self.temporal_results.clear()
        self.temporal_quality.clear()

        # QUANT depends directly on reconstructed daily NDVI.
        self.quant_results.clear()
        self.quant_water_summary.clear()
        if hasattr(self, "quant_tree"):
            self._refresh_quant_tree()
        if hasattr(self, "quant_status_var"):
            self.quant_status_var.set(
                "Temporal processing changed. Recalculate QUANT."
            )

        self._invalidate_from_temporal()
        errors = []

        for parcel_id, df in self.ndvi_results.items():
            try:
                if df is None or df.empty:
                    continue
                result = self._process_one_temporal_series(
                    df=df,
                    method=method,
                    lam=lam,
                    sg_window=sg_window,
                )
                self.temporal_results[parcel_id] = result
                self.temporal_quality[str(parcel_id)] = result.get("quality", {})
            except Exception as exc:
                errors.append((parcel_id, str(exc)))

        self._refresh_selected_plot()
        self._refresh_spatial_controls()

        if errors and show_message:
            details = "\n".join(f"{pid}: {msg}" for pid, msg in errors[:5])
            messagebox.showwarning(
                "Temporal processing",
                f"Some parcels could not be processed:\n\n{details}",
            )
        elif show_message:
            messagebox.showinfo(
                "Temporal processing",
                f"{method} processing completed for "
                f"{len(self.temporal_results)} parcel(s).",
            )

    def _process_one_temporal_series(self, df, method, lam, sg_window):
        good = df.loc[
            df["accepted"] & df["ndvi_p50"].notna(),
            ["date_start", "ndvi_p50"],
        ].copy()

        good["ndvi_p50"] = pd.to_numeric(
            good["ndvi_p50"],
            errors="coerce",
        )
        good = good.loc[
            np.isfinite(good["ndvi_p50"].to_numpy(dtype=float))
        ].copy()

        # CDSE timestamps are timezone-aware (UTC), while the daily index
        # created from the date-entry widgets is timezone-naive.  If both are
        # compared directly, no acquisition date matches the daily grid and the
        # reconstructed series collapses to empty/zero values.  Convert both to
        # plain calendar dates before matching.
        good["date_start"] = (
            pd.to_datetime(good["date_start"], utc=True)
            .dt.tz_convert(None)
            .dt.normalize()
        )
        good = (
            good.groupby("date_start", as_index=False)["ndvi_p50"]
            .median()
            .sort_values("date_start")
        )

        if len(good) >= 2:
            _gaps = good["date_start"].diff().dt.days.dropna()
            longest_gap_days = int(_gaps.max()) if not _gaps.empty else 0
        else:
            longest_gap_days = None

        if len(good) < 2:
            raise ValueError("At least two accepted NDVI observations are required.")

        start = pd.Timestamp(self.start_var.get()).normalize()
        end = pd.Timestamp(self.end_var.get()).normalize()
        daily_index = pd.date_range(start, end, freq="D")

        observed = pd.Series(index=daily_index, dtype=float)
        valid_dates = good["date_start"].isin(daily_index)
        good = good.loc[valid_dates].copy()

        if good.empty:
            raise ValueError(
                "No accepted Sentinel-2 observations matched the selected date range."
            )
        if len(good) < 2:
            raise ValueError(
                "At least two accepted NDVI observations within the selected "
                "date range are required for temporal reconstruction."
            )

        observed.loc[good["date_start"]] = good["ndvi_p50"].to_numpy()

        # Linear interpolation supplies a complete baseline and endpoint values.
        linear = observed.interpolate(method="time", limit_direction="both")

        if method == "Raw observations":
            reconstructed = pd.Series(np.nan, index=daily_index, dtype=float)

        elif method == "Linear interpolation":
            reconstructed = linear.copy()

        elif method == "Whittaker":
            n = len(daily_index)
            y = observed.to_numpy(dtype=float)
            w = np.isfinite(y).astype(float)
            y0 = np.nan_to_num(y, nan=0.0)

            # Second-order difference penalty:
            # min Σ w_i(y_i-z_i)^2 + λ||D²z||²
            W = diags(w, 0, shape=(n, n), format="csc")
            D = diags(
                [np.ones(n), -2.0 * np.ones(n), np.ones(n)],
                [0, 1, 2],
                shape=(n - 2, n),
                format="csc",
            )
            A = W + lam * (D.T @ D)
            reconstructed = pd.Series(
                spsolve(A, w * y0),
                index=daily_index,
                dtype=float,
            )

        elif method == "Savitzky-Golay":
            # SG is applied to the complete daily linear-interpolation baseline.
            # ``mode="interp"`` in scipy performs polynomial least-squares fits
            # at both edges and, depending on the local LAPACK/NumPy/SciPy stack,
            # can raise "SVD did not converge in Linear Least Squares".
            # ``nearest`` avoids that auxiliary edge regression while preserving
            # the SG polynomial smoothing in the interior.
            vals = linear.to_numpy(dtype=float)

            if len(vals) < 5:
                raise ValueError(
                    "Selected period is too short for Savitzky-Golay."
                )

            # Guard against non-finite input before entering scipy.
            finite = np.isfinite(vals)
            if not finite.all():
                # Rebuild any residual missing/invalid positions robustly.
                safe = pd.Series(
                    np.where(finite, vals, np.nan),
                    index=daily_index,
                    dtype=float,
                ).interpolate(
                    method="time",
                    limit_direction="both",
                )
                vals = safe.to_numpy(dtype=float)

            if not np.isfinite(vals).all():
                raise ValueError(
                    "Savitzky-Golay could not be applied because the daily "
                    "baseline still contains non-finite NDVI values."
                )

            window = int(sg_window)
            if window % 2 == 0:
                window += 1

            max_window = (
                len(vals)
                if len(vals) % 2 == 1
                else len(vals) - 1
            )
            window = min(window, max_window)

            # Keep an odd window and guarantee polyorder < window_length.
            if window < 5:
                raise ValueError(
                    "Selected period is too short for Savitzky-Golay."
                )

            polyorder = min(2, window - 1)

            try:
                sg_values = savgol_filter(
                    vals,
                    window_length=window,
                    polyorder=polyorder,
                    mode="nearest",
                )
            except Exception as exc:
                raise ValueError(
                    "Savitzky-Golay smoothing failed. "
                    f"Window={window} days, polyorder={polyorder}. "
                    f"Original error: {exc}"
                ) from exc

            reconstructed = pd.Series(
                sg_values,
                index=daily_index,
                dtype=float,
            )

        elif method == "Kalman":
            reconstructed = pd.Series(
                self._kalman_smooth_local_level(observed.to_numpy(dtype=float)),
                index=daily_index,
                dtype=float,
            )

        else:
            raise ValueError(f"Unknown temporal method: {method}")

        if method != "Raw observations" and self.constrain_ndvi_var.get():
            reconstructed = reconstructed.clip(lower=0.0, upper=1.0)

        # Requested output resolution. Internal reconstruction remains daily.
        out = pd.DataFrame({
            "date": daily_index,
            "ndvi_observed": observed.to_numpy(dtype=float),
            "ndvi_reconstructed_daily": reconstructed.to_numpy(dtype=float),
        })

        resolution = self.output_resolution_var.get()
        if method == "Raw observations":
            output_dates = good["date_start"]
            output_values = good["ndvi_p50"].to_numpy(dtype=float)
        else:
            if resolution == "Daily":
                output_dates = daily_index
                output_values = reconstructed.to_numpy(dtype=float)
            else:
                step = 5 if resolution == "5 days" else 10
                sampled = reconstructed.iloc[::step]
                output_dates = sampled.index
                output_values = sampled.to_numpy(dtype=float)

        output = pd.DataFrame({
            "date": pd.to_datetime(output_dates),
            "ndvi_processed": output_values,
        })

        diagnostics = self._temporal_diagnostics(good, reconstructed, method)

        return {
            "method": method,
            "daily": out,
            "output": output,
            "diagnostics": diagnostics,
            "quality": {
                "n_accepted": int(len(good)),
                "longest_gap_days": longest_gap_days,
            },
        }

    @staticmethod
    def _kalman_smooth_local_level(y):
        """Simple local-level Kalman filter + RTS smoother with missing data."""
        y = np.asarray(y, dtype=float)
        n = len(y)
        finite = np.isfinite(y)
        if finite.sum() < 2:
            return np.full(n, np.nan)

        obs = y[finite]
        diffs = np.diff(obs)
        scale = np.nanvar(obs)
        if not np.isfinite(scale) or scale <= 1e-8:
            scale = 0.01

        r = max(scale * 0.05, 1e-5)
        q = max(np.nanvar(diffs) * 0.05 if len(diffs) else scale * 0.01, 1e-6)

        x_f = np.zeros(n, dtype=float)
        p_f = np.zeros(n, dtype=float)
        x_pred = np.zeros(n, dtype=float)
        p_pred = np.zeros(n, dtype=float)

        first = int(np.flatnonzero(finite)[0])
        x_prev = float(y[first])
        p_prev = 1.0

        for t in range(n):
            xp = x_prev
            pp = p_prev + q
            x_pred[t] = xp
            p_pred[t] = pp

            if finite[t]:
                k = pp / (pp + r)
                xf = xp + k * (y[t] - xp)
                pf = (1.0 - k) * pp
            else:
                xf = xp
                pf = pp

            x_f[t] = xf
            p_f[t] = pf
            x_prev, p_prev = xf, pf

        x_s = x_f.copy()
        p_s = p_f.copy()

        for t in range(n - 2, -1, -1):
            denom = p_pred[t + 1]
            c = p_f[t] / denom if denom > 0 else 0.0
            x_s[t] = x_f[t] + c * (x_s[t + 1] - x_pred[t + 1])
            p_s[t] = p_f[t] + c * c * (p_s[t + 1] - p_pred[t + 1])

        return x_s

    @staticmethod
    def _temporal_diagnostics(good, reconstructed, method):
        if method == "Raw observations" or reconstructed.isna().all():
            return {
                "n": len(good),
                "rmse": np.nan,
                "mae": np.nan,
                "r2": np.nan,
            }

        obs_dates = (
            pd.to_datetime(good["date_start"], utc=True)
            .dt.tz_convert(None)
            .dt.normalize()
        )
        obs = good["ndvi_p50"].to_numpy(dtype=float)
        pred = reconstructed.reindex(obs_dates).to_numpy(dtype=float)

        mask = np.isfinite(obs) & np.isfinite(pred)
        obs = obs[mask]
        pred = pred[mask]

        if len(obs) == 0:
            return {"n": 0, "rmse": np.nan, "mae": np.nan, "r2": np.nan}

        err = obs - pred
        rmse = float(np.sqrt(np.mean(err ** 2)))
        mae = float(np.mean(np.abs(err)))

        if len(obs) >= 2 and np.var(obs) > 0:
            ss_res = float(np.sum((obs - pred) ** 2))
            ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
            r2 = 1.0 - ss_res / ss_tot
        else:
            r2 = np.nan

        return {"n": len(obs), "rmse": rmse, "mae": mae, "r2": r2}

    def _update_temporal_diagnostics(self, parcel_id):
        result = self.temporal_results.get(parcel_id)
        if not result:
            self.temporal_diag_var.set("Fit diagnostics: not calculated")
            return

        d = result["diagnostics"]
        method = result["method"]
        q = result.get("quality", {})
        gap = q.get("longest_gap_days")
        gap_txt = "NA" if gap is None else str(gap)
        if method == "Raw observations":
            self.temporal_diag_var.set(
                f"{method} | accepted observations: {d['n']} | max gap={gap_txt} d"
            )
            return

        r2 = "NA" if not np.isfinite(d["r2"]) else f"{d['r2']:.3f}"
        rmse = "NA" if not np.isfinite(d["rmse"]) else f"{d['rmse']:.3f}"
        mae = "NA" if not np.isfinite(d["mae"]) else f"{d['mae']:.3f}"
        self.temporal_diag_var.set(
            f"{method} | n={d['n']} | RMSE={rmse} | MAE={mae} | R²={r2}"
        )

    def _plot_ndvi(self, df):
        self.ax.clear()
        if df.empty:
            self.ax.set_title("No NDVI data")
            self.ax.set_ylim(0.0, 1.0)
            self.canvas.draw_idle()
            return

        good = df[df["accepted"] & df["ndvi_p50"].notna()].copy()
        bad = df[(~df["accepted"]) & df["ndvi_p50"].notna()].copy()

        # Raw accepted observations are always preserved and shown as points.
        if not good.empty:
            self.ax.scatter(
                good["date_start"],
                good["ndvi_p50"],
                marker="o",
                s=34,
                label="Observed P50 NDVI — accepted",
                zorder=3,
            )

        if self.show_rejected_var.get() and not bad.empty:
            self.ax.scatter(
                bad["date_start"],
                bad["ndvi_p50"],
                marker="x",
                s=30,
                label="Rejected by valid-pixel threshold",
                zorder=2,
            )

        parcel_id = (
            str(df["parcel_id"].iloc[0])
            if "parcel_id" in df.columns and not df.empty
            else "Parcel"
        )
        crop = (
            str(df["crop"].iloc[0])
            if "crop" in df.columns and not df.empty
            else ""
        )

        temporal = self.temporal_results.get(parcel_id)
        if temporal and temporal["method"] != "Raw observations":
            output = temporal["output"].copy()
            output = output[
                pd.to_numeric(output["ndvi_processed"], errors="coerce").notna()
            ].copy()

            if not output.empty:
                self.ax.plot(
                    output["date"],
                    output["ndvi_processed"],
                    linewidth=2.2,
                    label=f"{temporal['method']} — {self.output_resolution_var.get()}",
                    zorder=2,
                )

        # Fixed display scale for inter-parcel comparability.
        self.ax.set_ylim(0.0, 1.0)
        y_ticks = np.arange(0.0, 1.01, 0.2)
        self.ax.set_yticks(y_ticks)
        self.ax.set_yticklabels([f"{v:.1f}" for v in y_ticks])

        self._set_plot_period_from_inputs()
        self.ax.set_ylabel("NDVI")
        self.ax.set_xlabel("Date")

        method_txt = (
            f" | {temporal['method']}" if temporal else ""
        )
        self.ax.set_title(
            f"{parcel_id} — {crop} | Sentinel-2 L2A NDVI{method_txt} | "
            f"{self.start_var.get()} to {self.end_var.get()}"
        )
        self.ax.grid(True, alpha=0.25)

        start_plot = pd.Timestamp(self.start_var.get())
        end_plot = pd.Timestamp(self.end_var.get())
        span_days = max((end_plot - start_plot).days, 1)

        if span_days <= 100:
            self.ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%Y"))
        elif span_days <= 550:
            self.ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        else:
            self.ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))

        if not good.empty or (self.show_rejected_var.get() and not bad.empty) or temporal:
            self.ax.legend()

        self.canvas.figure.tight_layout()
        self.canvas.draw_idle()

    def _update_info(self, parcel_id, df):
        # QA values remain in the dataframe, but the dedicated QA tab was removed.
        if self.info_text is None:
            return
        valid_min = float(self.valid_pct_var.get())
        accepted = df[df["accepted"]]
        rejected = df[~df["accepted"]]

        lines = [
            f"Parcel: {parcel_id}",
            f"Source: Sentinel-2 L2A / Copernicus Data Space Ecosystem",
            f"NDVI statistic used for display: P50 (median)",
            f"SCL mask excluded: 0, 1, 3, 8, 9, 10, 11",
            f"Minimum valid pixels: {valid_min:.1f} %",
            f"Returned intervals: {len(df)}",
            f"Accepted intervals: {len(accepted)}",
            f"Rejected intervals: {len(rejected)}",
            "",
            "Date        NDVI_P50    Valid_%    QA",
            "-" * 44,
        ]

        for _, r in df.iterrows():
            dt = r["date_start"]
            dt_str = dt.strftime("%Y-%m-%d") if pd.notna(dt) else "NA"
            ndvi = r["ndvi_p50"]
            val = r["valid_fraction_pct"]
            ndvi_str = f"{ndvi:.4f}" if pd.notna(ndvi) else "NA"
            val_str = f"{val:.1f}" if pd.notna(val) else "NA"
            qa = "OK" if bool(r["accepted"]) else "REJECT"
            lines.append(f"{dt_str}  {ndvi_str:>9}  {val_str:>8}  {qa}")

        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", "\n".join(lines))
        self.info_text.configure(state="disabled")

    def export_csv(self):
        idx = self._selected_index()
        if idx is None or self.gdf is None:
            messagebox.showwarning("Export", "Select a parcel.")
            return

        parcel_id = self.gdf.loc[idx, "parcel_id"]
        df = self.ndvi_results.get(parcel_id)
        if df is None or df.empty:
            messagebox.showwarning(
                "Export", "No NDVI series has been calculated for this parcel."
            )
            return

        path = filedialog.asksaveasfilename(
            title="Export NDVI series",
            defaultextension=".csv",
            initialfile=f"{parcel_id}_NDVI.csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return

        export_df = df.copy()

        temporal = self.temporal_results.get(parcel_id)
        if temporal and temporal["method"] != "Raw observations":
            processed = temporal["output"].copy()
            processed = processed.rename(columns={
                "date": "processed_date",
                "ndvi_processed": "ndvi_processed",
            })

            # Save the original acquisition table as requested and create a
            # companion processed file because both tables have different
            # temporal resolutions.
            export_df.to_csv(path, index=False)

            base, ext = os.path.splitext(path)
            processed_path = f"{base}_processed{ext}"
            processed.to_csv(processed_path, index=False)

            messagebox.showinfo(
                "Export",
                f"Saved raw/QA series:\n{path}\n\n"
                f"Saved processed series:\n{processed_path}",
            )
        else:
            export_df.to_csv(path, index=False)
            messagebox.showinfo("Export", f"Saved:\n{path}")

    # =============================================================
    # Scientific robustness / dependency helpers
    # =============================================================
    def _invalidate_from_temporal(self):
        self.kc_results.clear()
        self.water_results.clear()
        if hasattr(self, "water_summary_var"):
            self.water_summary_var.set("Water results: not calculated")
        if hasattr(self, "ax_water"):
            self._plot_selected_water()

    def _invalidate_from_kc(self, parcel_id=None):
        if parcel_id is None:
            self.kc_results.clear()
            self.water_results.clear()
        else:
            self.kc_results.pop(str(parcel_id), None)
            self.water_results.pop(str(parcel_id), None)
        if hasattr(self, "water_summary_var"):
            self.water_summary_var.set("Water results: not calculated")
        if hasattr(self, "ax_water"):
            self._plot_selected_water()

    def _invalidate_water(self):
        self.water_results.clear()
        if hasattr(self, "water_summary_var"):
            self.water_summary_var.set("Water results: not calculated")
        if hasattr(self, "ax_water"):
            self._plot_selected_water()

    def _build_run_metadata(self):
        meta = {
            "app_version": APP_VERSION,
            "satellite_product": "Sentinel-2 L2A",
            "spatial_resolution_m": 10,
            "parcel_statistic": "P50",
            "scl_excluded_classes": "0,1,3,8,9,10,11",
            "date_start": self.start_var.get() if hasattr(self, "start_var") else "",
            "date_end": self.end_var.get() if hasattr(self, "end_var") else "",
            "aggregation_interval": self.interval_var.get() if hasattr(self, "interval_var") else "",
            "minimum_valid_fraction_percent": self.valid_pct_var.get() if hasattr(self, "valid_pct_var") else "",
            "temporal_method": self.temporal_method_var.get() if hasattr(self, "temporal_method_var") else "",
            "whittaker_lambda": self.whittaker_lambda_var.get() if hasattr(self, "whittaker_lambda_var") else "",
            "sg_window_days": self.sg_window_var.get() if hasattr(self, "sg_window_var") else "",
            "temporal_output_resolution": self.output_resolution_var.get() if hasattr(self, "output_resolution_var") else "",
            "constrain_ndvi_0_1": self.constrain_ndvi_var.get() if hasattr(self, "constrain_ndvi_var") else "",
            "kc_ndvi_source": self.kc_ndvi_source_var.get() if hasattr(self, "kc_ndvi_source_var") else "",
            "kc_nonnegative_constraint": self.kc_clip_var.get() if hasattr(self, "kc_clip_var") else "",
            "water_mode": self.water_mode_var.get() if hasattr(self, "water_mode_var") else "",
            "meteorological_file": self.meteo_file or "",
            "generated_at": pd.Timestamp.now().isoformat(),
            "software_author": self.software_metadata.get("author", ""),
            "software_orcid": self.software_metadata.get("orcid", ""),
            "software_repository": self.software_metadata.get("repository_url", ""),
            "software_doi": self.software_metadata.get("zenodo_doi", ""),
            "software_license": self.software_metadata.get("license", "GPL-3.0"),
            "iwr_definition": "daily max(ETc - Pe, 0); simplified net requirement",
            "quant_reference": "French et al. (2023), Agricultural Water Management 290, 108582",
            "quant_doi": "10.1016/j.agwat.2023.108582",
            "quant_q1_percent": self.quant_q1_var.get() if hasattr(self, "quant_q1_var") else "",
            "quant_q2_percent": self.quant_q2_var.get() if hasattr(self, "quant_q2_var") else "",
            "quant_q3_percent": self.quant_q3_var.get() if hasattr(self, "quant_q3_var") else "",
            "quant_q4_percent": self.quant_q4_var.get() if hasattr(self, "quant_q4_var") else "",
        }
        self.run_metadata = meta
        return meta

    # =============================================================
    # Phase 2 — Direct Kc-NDVI, ETc/CWR and optional net IWR
    # =============================================================
    def _compatible_kc_models(self, crop):
        crop = str(crop).upper()
        model_ids = []
        for model_id, meta in KC_CATALOG.items():
            crops = [c.upper() for c in meta.get("crops", [])]
            if "ALL" in crops or crop in crops:
                model_ids.append(model_id)
        return model_ids

    def _kc_label_to_id(self, label):
        for model_id, meta in KC_CATALOG.items():
            if meta["label"] == label:
                return model_id
        return None

    def _refresh_kc_tree(self):
        if not hasattr(self, "kc_tree"):
            return
        for item in self.kc_tree.get_children():
            self.kc_tree.delete(item)
        if self.gdf is None:
            return

        for idx, row in self.gdf.iterrows():
            pid = str(row["parcel_id"])
            model_id = self.kc_assignments.get(pid)
            label = KC_CATALOG[model_id]["label"] if model_id in KC_CATALOG else "Not assigned"
            self.kc_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(pid, str(row["crop"]), label),
            )

    def _on_kc_parcel_selected(self, _event=None):
        selected = self.kc_tree.selection()
        if not selected or self.gdf is None:
            return

        idx = int(selected[0])
        row = self.gdf.loc[idx]
        pid = str(row["parcel_id"])
        crop = str(row["crop"]).upper()

        compatible = self._compatible_kc_models(crop)
        labels = [KC_CATALOG[mid]["label"] for mid in compatible]
        self.kc_model_combo["values"] = labels

        assigned = self.kc_assignments.get(pid)
        if assigned in compatible:
            self.kc_model_var.set(KC_CATALOG[assigned]["label"])
        elif labels:
            self.kc_model_var.set(labels[0])
        else:
            self.kc_model_var.set("")
        self._show_kc_model_info()

        # Synchronize the main parcel table ONLY if needed.
        # Do not manually call _on_parcel_selected(); Tkinter will emit
        # <<TreeviewSelect>> once for the real change.
        target = str(idx)
        current = self.tree.selection()
        if target in self.tree.get_children() and current != (target,):
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)

        self._plot_selected_water()
        self._update_water_summary()

    def _sync_kc_selection_to_parcel(self, parcel_id):
        if self.gdf is None or not hasattr(self, "kc_tree"):
            return

        matches = self.gdf.index[
            self.gdf["parcel_id"].astype(str) == str(parcel_id)
        ].tolist()
        if not matches:
            return

        target = str(matches[0])
        if target not in self.kc_tree.get_children():
            return

        current = self.kc_tree.selection()
        if current != (target,):
            self.kc_tree.selection_set(target)
            self.kc_tree.focus(target)
            self.kc_tree.see(target)

    def _show_kc_model_info(self, _event=None):
        model_id = self._kc_label_to_id(self.kc_model_var.get())
        if not model_id:
            self.kc_info_var.set("No compatible Kc relationship selected.")
            return
        m = KC_CATALOG[model_id]
        doi_txt = f" | DOI: {m['doi']}" if m.get("doi") else ""
        status = m.get("verification_status", "not specified")
        source = m.get("source_type", "built-in")
        self.kc_info_var.set(
            f"{m['equation']}\n{m['reference']}{doi_txt}\n{m['scope']}\n"
            f"Source: {source} | Verification: {status}"
        )

    def assign_kc_selected(self):
        selected = self.kc_tree.selection()
        if not selected or self.gdf is None:
            messagebox.showwarning("Kc model", "Select a parcel in the Kc table.")
            return

        model_id = self._kc_label_to_id(self.kc_model_var.get())
        if not model_id:
            messagebox.showwarning("Kc model", "Select a Kc relationship.")
            return

        idx = int(selected[0])
        pid = str(self.gdf.loc[idx, "parcel_id"])
        crop = str(self.gdf.loc[idx, "crop"]).upper()

        if model_id not in self._compatible_kc_models(crop):
            messagebox.showerror("Kc model", "This relationship is not compatible with the selected crop.")
            return

        self.kc_assignments[pid] = model_id
        self._invalidate_from_kc(pid)
        self._refresh_kc_tree()
        self.kc_tree.selection_set(str(idx))
        self.kc_tree.focus(str(idx))
        self.kc_tree.see(str(idx))
        self._show_kc_model_info()
        self._plot_selected_water()
        self._update_water_summary()

    def assign_kc_same_crop(self):
        selected = self.kc_tree.selection()
        if not selected or self.gdf is None:
            messagebox.showwarning("Kc model", "Select a parcel in the Kc table.")
            return

        model_id = self._kc_label_to_id(self.kc_model_var.get())
        if not model_id:
            messagebox.showwarning("Kc model", "Select a Kc relationship.")
            return

        idx = int(selected[0])
        crop = str(self.gdf.loc[idx, "crop"]).upper()

        if model_id not in self._compatible_kc_models(crop):
            messagebox.showerror("Kc model", "This relationship is not compatible with this crop.")
            return

        mask = self.gdf["crop"].astype(str).str.upper() == crop
        for _, row in self.gdf.loc[mask].iterrows():
            pid = str(row["parcel_id"])
            self.kc_assignments[pid] = model_id
            self._invalidate_from_kc(pid)

        self._refresh_kc_tree()
        messagebox.showinfo(
            "Kc model",
            f"{KC_CATALOG[model_id]['label']} assigned to all {crop} parcels.",
        )

    def _get_ndvi_for_kc(self, parcel_id):
        source = self.kc_ndvi_source_var.get()

        if source in {"Processed if available", "Processed only"}:
            temporal = self.temporal_results.get(parcel_id)
            if temporal:
                daily = temporal.get("daily")
                if daily is not None and not daily.empty:
                    df = daily[["date", "ndvi_reconstructed_daily"]].copy()
                    df = df.rename(columns={"ndvi_reconstructed_daily": "NDVI"})
                    df["NDVI_source"] = f"Processed — {temporal.get('method', 'unknown')}"
                    df = df[df["NDVI"].notna()].copy()
                    if not df.empty:
                        return df

            if source == "Processed only":
                raise ValueError(
                    "No processed NDVI series is available. Run temporal processing first."
                )

        raw = self.ndvi_results.get(parcel_id)
        if raw is None or raw.empty:
            raise ValueError("No raw NDVI series is available.")

        df = raw.loc[
            raw["accepted"] & raw["ndvi_p50"].notna(),
            ["date_start", "ndvi_p50"],
        ].copy()
        df["date"] = (
            pd.to_datetime(df["date_start"], utc=True)
            .dt.tz_convert(None)
            .dt.normalize()
        )
        df = df.rename(columns={"ndvi_p50": "NDVI"})
        df["NDVI_source"] = "Raw accepted P50 observations"
        return df[["date", "NDVI", "NDVI_source"]].sort_values("date")

    def calculate_kc_all(self):
        if self.gdf is None or self.gdf.empty:
            messagebox.showwarning("Kc", "Load parcels first.")
            return
        if not self.ndvi_results:
            messagebox.showwarning("Kc", "Calculate NDVI first.")
            return

        missing = [
            str(row["parcel_id"])
            for _, row in self.gdf.iterrows()
            if str(row["parcel_id"]) not in self.kc_assignments
        ]
        if missing:
            messagebox.showwarning(
                "Kc",
                "Assign a direct Kc–NDVI relationship to every parcel first.\n\n"
                + "Missing: " + ", ".join(missing),
            )
            return

        self.kc_results.clear()
        self.water_results.clear()
        errors = []

        for _, row in self.gdf.iterrows():
            pid = str(row["parcel_id"])
            crop = str(row["crop"])
            try:
                ndvi = self._get_ndvi_for_kc(pid)
                model_id = self.kc_assignments[pid]
                m = KC_CATALOG[model_id]

                out = ndvi.copy()
                out["parcel_id"] = pid
                out["crop"] = crop
                out["Kc_model_id"] = model_id
                out["Kc_model"] = m["label"]
                out["Kc_equation"] = m["equation"]
                out["Kc_reference"] = m["reference"]
                out["Kc"] = calculate_linear_kc(
                    out["NDVI"].to_numpy(),
                    m["a"],
                    m["b"],
                    constrain_nonnegative=self.kc_clip_var.get(),
                )

                ndvi_min = m.get("ndvi_min")
                ndvi_max = m.get("ndvi_max")
                if ndvi_min is not None and ndvi_max is not None:
                    out["Kc_extrapolated"] = ~out["NDVI"].between(
                        ndvi_min, ndvi_max, inclusive="both"
                    )
                else:
                    out["Kc_extrapolated"] = False

                cols = [
                    "date", "parcel_id", "crop", "NDVI", "NDVI_source",
                    "Kc", "Kc_extrapolated", "Kc_model_id", "Kc_model", "Kc_equation", "Kc_reference"
                ]
                self.kc_results[pid] = out[cols].reset_index(drop=True)

            except Exception as exc:
                errors.append((pid, str(exc)))

        self._plot_selected_water()

        if errors:
            details = "\n".join(f"{pid}: {msg}" for pid, msg in errors[:8])
            messagebox.showwarning(
                "Kc calculation",
                f"Kc was calculated for {len(self.kc_results)} parcel(s).\n\n"
                f"Problems:\n{details}",
            )
        else:
            messagebox.showinfo(
                "Kc calculation",
                f"Kc calculated for all {len(self.kc_results)} parcel(s).",
            )

    def load_meteo_csv(self):
        path = filedialog.askopenfilename(
            title="Select meteorological CSV",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            df = pd.read_csv(path, sep=None, engine="python")
            # Case-insensitive canonicalization
            mapping = {
                str(c).replace("\ufeff", "").strip().lower(): c
                for c in df.columns
            }
            if "date" not in mapping or "eto" not in mapping:
                raise ValueError("The CSV must contain at least Date and ETo columns.")

            rename = {
                mapping["date"]: "Date",
                mapping["eto"]: "ETo",
            }
            if "pe" in mapping:
                rename[mapping["pe"]] = "Pe"
            if "parcel_id" in mapping:
                rename[mapping["parcel_id"]] = "parcel_id"

            df = df.rename(columns=rename)
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
            if df["Date"].isna().any():
                raise ValueError("Some Date values could not be parsed.")

            df["ETo"] = pd.to_numeric(df["ETo"], errors="coerce")
            if df["ETo"].isna().any():
                raise ValueError("Some ETo values are missing or non-numeric.")
            if (df["ETo"] < 0).any():
                raise ValueError("ETo cannot contain negative values.")
            high_eto_n = int((df["ETo"] > 15).sum())

            if "Pe" in df.columns:
                df["Pe"] = pd.to_numeric(df["Pe"], errors="coerce")
                if df["Pe"].isna().any():
                    raise ValueError("Some Pe values are missing or non-numeric.")
                if (df["Pe"] < 0).any():
                    raise ValueError("Pe cannot contain negative values.")
                high_pe_n = int((df["Pe"] > 200).sum())

            subset = ["Date"] + (["parcel_id"] if "parcel_id" in df.columns else [])
            if df.duplicated(subset=subset).any():
                raise ValueError(
                    "Duplicate meteorological records detected for Date"
                    + (" + parcel_id." if "parcel_id" in df.columns else ".")
                )

            if "parcel_id" in df.columns:
                df["parcel_id"] = df["parcel_id"].astype(str)

            self._invalidate_water()
            self.meteo_df = df.sort_values(subset).reset_index(drop=True)
            self.meteo_file = path
            self.meteo_file_var.set(path)

            # If Pe is supplied, default to Net IWR for the test workflow.
            # The user can still switch back to "CWR / ETc only".
            if "Pe" in df.columns:
                self.water_mode_var.set("Net IWR")

            extra = "Pe available — Net IWR can be calculated" if "Pe" in df.columns else "Pe not present — CWR / ETc only"
            scope = "parcel-specific" if "parcel_id" in df.columns else "shared by all parcels"
            warnings = []
            if high_eto_n:
                warnings.append(f"{high_eto_n} ETo value(s) > 15 mm d⁻¹")
            if "Pe" in df.columns and high_pe_n:
                warnings.append(f"{high_pe_n} Pe value(s) > 200 mm d⁻¹")
            warning_txt = ""
            if warnings:
                warning_txt = "\nWarning: " + "; ".join(warnings)

            messagebox.showinfo(
                "Meteorological CSV",
                f"Loaded {len(df)} records.\n{extra}\nMeteorology: {scope}.\n"
                f"Expected units: ETo and Pe in mm d⁻¹."
                f"{warning_txt}",
            )

        except Exception as exc:
            messagebox.showerror("Meteorological CSV", str(exc))

    def calculate_water_all(self):
        if not self.kc_results:
            messagebox.showwarning("CWR / IWR", "Calculate Kc first.")
            return
        if self.meteo_df is None or self.meteo_df.empty:
            messagebox.showwarning("CWR / IWR", "Load the meteorological CSV first.")
            return

        mode = self.water_mode_var.get().strip()
        calculate_iwr = (mode == "Net IWR")

        # Kc from raw Sentinel-2 observations may be inspected/exported,
        # but seasonal CWR/IWR accumulation requires continuous daily Kc.
        invalid_daily = []
        for pid, kcdf in self.kc_results.items():
            if kcdf is None or kcdf.empty:
                invalid_daily.append(str(pid))
                continue

            sources = set(kcdf["NDVI_source"].astype(str).unique())
            processed_source = any(s.startswith("Processed") for s in sources)

            dates = pd.to_datetime(
                kcdf["date"], errors="coerce"
            ).dropna().sort_values().drop_duplicates()

            continuous_daily = (
                len(dates) >= 2
                and dates.diff().dt.days.dropna().eq(1).all()
            )

            if not processed_source or not continuous_daily:
                invalid_daily.append(str(pid))

        if invalid_daily:
            messagebox.showwarning(
                "CWR / IWR",
                "Accumulated CWR/IWR requires continuous DAILY processed NDVI/Kc.\n\n"
                "Raw Sentinel-2 observations remain valid for Kc inspection/export, "
                "but not for seasonal water accumulation.\n\n"
                "Process the temporal series and recalculate Kc for: "
                + ", ".join(invalid_daily)
            )
            return

        if calculate_iwr and "Pe" not in self.meteo_df.columns:
            messagebox.showerror(
                "Net IWR",
                "Net IWR was selected, but the meteorological CSV does not contain Pe.",
            )
            return

        self.water_results.clear()
        errors = []

        for pid, kc_df in self.kc_results.items():
            try:
                met = self.meteo_df.copy()

                if "parcel_id" in met.columns:
                    met = met[met["parcel_id"].astype(str) == str(pid)].copy()
                    if met.empty:
                        raise ValueError(
                            "No meteorological records were found for this parcel."
                        )

                merged = kc_df.copy()
                merged["date"] = pd.to_datetime(
                    merged["date"], errors="coerce"
                ).dt.normalize()

                met["Date"] = pd.to_datetime(
                    met["Date"], errors="coerce"
                ).dt.normalize()

                required_dates = pd.DatetimeIndex(
                    merged["date"].dropna().drop_duplicates().sort_values()
                )
                met_dates = pd.DatetimeIndex(
                    met["Date"].dropna().drop_duplicates().sort_values()
                )

                missing_dates = required_dates.difference(met_dates)
                if len(missing_dates):
                    preview = ", ".join(
                        d.strftime("%Y-%m-%d") for d in missing_dates[:8]
                    )
                    if len(missing_dates) > 8:
                        preview += f" ... (+{len(missing_dates) - 8} more)"
                    raise ValueError(
                        f"Incomplete meteorological coverage: "
                        f"{len(missing_dates)} required day(s) missing. {preview}"
                    )

                expected_dates = pd.date_range(
                    required_dates.min(), required_dates.max(), freq="D"
                )
                if len(expected_dates) != len(required_dates):
                    raise ValueError(
                        "The Kc series is not continuous daily data. "
                        "CWR/IWR accumulation was stopped."
                    )

                merged = merged.merge(
                    met,
                    left_on="date",
                    right_on="Date",
                    how="left",
                    suffixes=("", "_meteo"),
                    validate="one_to_one",
                )

                if merged["ETo"].isna().any():
                    raise ValueError("ETo contains missing values after date matching.")

                # Crop water requirement: CWR = ETc = Kc * ETo
                merged["ETc"] = calculate_etc(
                    merged["Kc"].to_numpy(),
                    merged["ETo"].to_numpy(),
                )
                merged["CWR"] = merged["ETc"]
                merged["CWR_cumulative"] = merged["CWR"].cumsum()

                # Net irrigation water requirement is calculated only when
                # explicitly requested by the user.
                if calculate_iwr:
                    if merged["Pe"].isna().any():
                        raise ValueError(
                            "Pe contains missing values on dates matched to the Kc series."
                        )

                    merged["IWR_net"] = (
                        merged["CWR"] - merged["Pe"]
                    ).clip(lower=0.0)

                    merged["IWR_net_cumulative"] = (
                        merged["IWR_net"].cumsum()
                    )

                merged["ETo_warning"] = merged["ETo"] > 15
                if "Pe" in merged.columns:
                    merged["Pe_warning"] = merged["Pe"] > 200

                self.water_results[str(pid)] = merged.reset_index(drop=True)

            except Exception as exc:
                errors.append((str(pid), str(exc)))

        self._plot_selected_water()
        self._update_water_summary()

        n_iwr = sum(
            1 for df in self.water_results.values()
            if "IWR_net" in df.columns
        )

        if errors:
            details = "\n".join(f"{pid}: {msg}" for pid, msg in errors[:8])
            messagebox.showwarning(
                "CWR / IWR",
                f"Results calculated for {len(self.water_results)} parcel(s).\n"
                f"Net IWR calculated for {n_iwr} parcel(s).\n\n"
                f"Problems:\n{details}",
            )
        else:
            if calculate_iwr:
                messagebox.showinfo(
                    "CWR / IWR",
                    f"CWR and net IWR calculated successfully for "
                    f"{len(self.water_results)} parcel(s).",
                )
            else:
                messagebox.showinfo(
                    "CWR / ETc",
                    f"CWR / ETc calculated successfully for "
                    f"{len(self.water_results)} parcel(s).",
                )

    def _selected_main_parcel_id(self):
        idx = self._selected_index()
        if idx is None or self.gdf is None:
            return None
        return str(self.gdf.loc[idx, "parcel_id"])

    def _plot_selected_water(self):
        if not hasattr(self, "ax_water"):
            return

        self.ax_water.clear()
        pid = self._selected_main_parcel_id()

        if pid is None:
            self.ax_water.set_title("Select a parcel")
            self.canvas_water.draw_idle()
            return

        variable = self.water_plot_var.get()

        if variable == "Kc":
            df = self.kc_results.get(pid)
            if df is None or df.empty:
                self.ax_water.set_title(f"{pid} | Kc not calculated")
                self.ax_water.set_ylabel("Kc")
            else:
                x = pd.to_datetime(df["date"])
                y = pd.to_numeric(df["Kc"], errors="coerce")
                mask = x.notna() & y.notna()
                self.ax_water.plot(x[mask], y[mask], linewidth=1.8)
                self.ax_water.set_title(f"{pid} | Estimated Kc")
                self.ax_water.set_ylabel("Kc")

        else:
            df = self.water_results.get(pid)
            if df is None or df.empty:
                self.ax_water.set_title(
                    f"{pid} | Water requirements not calculated"
                )
            else:
                mapping = {
                    "ETc daily": (
                        "ETc", "ETc / CWR (mm d⁻¹)", "Daily ETc / CWR"
                    ),
                    "CWR cumulative": (
                        "CWR_cumulative", "CWR (mm)", "Cumulative CWR"
                    ),
                    "IWR net daily": (
                        "IWR_net", "Net IWR (mm d⁻¹)", "Daily net IWR"
                    ),
                    "IWR net cumulative": (
                        "IWR_net_cumulative",
                        "Net IWR (mm)",
                        "Cumulative net IWR",
                    ),
                }

                col, ylabel, title = mapping[variable]

                if col not in df.columns:
                    self.ax_water.set_title(
                        f"{pid} | {variable} unavailable. "
                        f"Select Net IWR and recalculate if required."
                    )
                    self.ax_water.set_ylabel(ylabel)
                else:
                    x = pd.to_datetime(df["date"])
                    y = pd.to_numeric(df[col], errors="coerce")
                    mask = x.notna() & y.notna()
                    self.ax_water.plot(x[mask], y[mask], linewidth=1.8)
                    self.ax_water.set_title(f"{pid} | {title}")
                    self.ax_water.set_ylabel(ylabel)

        self.ax_water.set_xlabel("Date")
        self.ax_water.grid(True, alpha=0.25)

        # Recalculate limits every time the parcel changes.
        self.ax_water.relim()
        self.ax_water.autoscale_view()

        locator = mdates.AutoDateLocator()
        self.ax_water.xaxis.set_major_locator(locator)
        self.ax_water.xaxis.set_major_formatter(
            mdates.ConciseDateFormatter(locator)
        )

        self.canvas_water.figure.tight_layout()
        self.canvas_water.draw_idle()

    def _update_water_summary(self):
        pid = self._selected_main_parcel_id()
        if pid is None:
            self.water_summary_var.set("Water results: not calculated")
            return
        df = self.water_results.get(pid)
        if df is None or df.empty:
            self.water_summary_var.set(f"{pid}: water results not calculated")
            return

        etc = float(df["ETc"].sum())
        txt = f"{pid} | Total CWR/ETc = {etc:.1f} mm"
        if "IWR_net" in df.columns:
            iwr = float(df["IWR_net"].sum())
            pe = float(df["Pe"].sum())
            txt += f" | Total Pe = {pe:.1f} mm | Net IWR = {iwr:.1f} mm"
        self.water_summary_var.set(txt)

    def _write_analysis_summary(self, outdir):
        outdir = Path(outdir)
        meta = self._build_run_metadata()
        lines = [
            f"CropWater-RS v{APP_VERSION}",
            "=" * 48,
            "",
            f"Generated: {meta.get('generated_at', '')}",
            f"Author: {self.software_metadata.get('author', '')}",
            f"License: {self.software_metadata.get('license', '')}",
            "",
            "Scientific workflow",
            "-------------------",
            "Sentinel-2 L2A -> parcel NDVI -> temporal reconstruction -> "
            "direct literature Kc-NDVI -> ETc/CWR -> optional simplified net IWR",
            "",
        ]

        if self.gdf is not None:
            lines.extend([f"Parcels: {len(self.gdf)}", ""])

        lines.extend(["Processing parameters", "---------------------"])
        for k, v in meta.items():
            lines.append(f"{k}: {v}")

        if self.gdf is not None and not self.gdf.empty:
            lines.extend(["", "Parcel results", "--------------"])
            for _, row in self.gdf.iterrows():
                pid = str(row["parcel_id"])
                line = f"{pid} | crop={row['crop']} | area={row['area_ha']:.2f} ha"
                kdf = self.kc_results.get(pid)
                if kdf is not None and not kdf.empty:
                    line += f" | mean Kc={float(kdf['Kc'].mean()):.3f}"
                wdf = self.water_results.get(pid)
                if wdf is not None and not wdf.empty:
                    line += f" | CWR={float(wdf['ETc'].sum()):.1f} mm"
                    if "IWR_net" in wdf.columns:
                        line += f" | net IWR={float(wdf['IWR_net'].sum()):.1f} mm"
                lines.append(line)

        (outdir / "analysis_summary.txt").write_text("\n".join(lines), encoding="utf-8")

    def _write_spatial_export_to_folder(self, outdir):
        if self.gdf is None or self.gdf.empty:
            return
        try:
            spatial = self._build_spatial_export_gdf()
            spatial.to_file(
                Path(outdir) / "CropWater_RS_results.gpkg",
                layer="cropwater_results",
                driver="GPKG",
            )
        except Exception:
            logging.exception("Automatic GeoPackage export failed")

    def _write_quant_export_to_folder(self, outdir):
        if not self.quant_results:
            return
        try:
            qdf = self._quant_export_dataframe()
            qdf.to_csv(
                Path(outdir) / "QUANT_phenology_all_parcels.csv",
                index=False,
            )
        except Exception:
            logging.exception("Automatic QUANT export failed")

    def export_water_results(self):
        if not self.kc_results:
            messagebox.showwarning(
                "Export",
                "There are no Kc results to export.",
            )
            return

        folder = filedialog.askdirectory(
            title="Select output folder for Kc / CWR / IWR results"
        )
        if not folder:
            return

        outdir = Path(folder)
        try:
            # Kc
            kc_frames = []
            kc_dir = outdir / "Kc_by_parcel"
            kc_dir.mkdir(exist_ok=True)

            for pid, df in self.kc_results.items():
                if df is None or df.empty:
                    continue
                safe = str(pid).replace("/", "_").replace("\\", "_")
                df.to_csv(kc_dir / f"{safe}_Kc.csv", index=False)
                kc_frames.append(df)

            if kc_frames:
                pd.concat(kc_frames, ignore_index=True).to_csv(
                    outdir / "Kc_all_parcels.csv",
                    index=False,
                )

            # Water results only if calculated
            water_frames = []
            if self.water_results:
                water_dir = outdir / "Water_by_parcel"
                water_dir.mkdir(exist_ok=True)

                for pid, df in self.water_results.items():
                    if df is None or df.empty:
                        continue
                    safe = str(pid).replace("/", "_").replace("\\", "_")
                    df.to_csv(
                        water_dir / f"{safe}_CWR_IWR.csv",
                        index=False,
                    )
                    water_frames.append(df)

                if water_frames:
                    water_all = pd.concat(water_frames, ignore_index=True)
                    combined_name = (
                        "CWR_IWR_all_parcels.csv"
                        if "IWR_net" in water_all.columns
                        else "CWR_all_parcels.csv"
                    )
                    water_all.to_csv(
                        outdir / combined_name,
                        index=False,
                    )

            # Model assignments for reproducibility
            assignments = []
            if self.gdf is not None:
                for _, row in self.gdf.iterrows():
                    pid = str(row["parcel_id"])
                    mid = self.kc_assignments.get(pid)
                    if mid in KC_CATALOG:
                        m = KC_CATALOG[mid]
                        assignments.append({
                            "parcel_id": pid,
                            "crop": row["crop"],
                            "Kc_model_id": mid,
                            "Kc_model": m["label"],
                            "equation": m["equation"],
                            "reference": m["reference"],
                            "doi": m.get("doi", ""),
                            "scope": m.get("scope", ""),
                            "kc_type": m.get("kc_type", "Kc"),
                            "sensor": m.get("sensor", ""),
                            "study_region": m.get("study_region", ""),
                            "r2": m.get("r2", ""),
                            "ndvi_min": m.get("ndvi_min", ""),
                            "ndvi_max": m.get("ndvi_max", ""),
                            "kc_min": m.get("kc_min", ""),
                            "kc_max": m.get("kc_max", ""),
                            "calibration_note": m.get("calibration_note", ""),
                            "source_type": m.get("source_type", ""),
                            "verification_status": m.get("verification_status", ""),
                        })
            if assignments:
                pd.DataFrame(assignments).to_csv(
                    outdir / "Kc_model_assignments.csv",
                    index=False,
                )

            meta = self._build_run_metadata()
            pd.DataFrame(
                [{"parameter": k, "value": v} for k, v in meta.items()]
            ).to_csv(outdir / "run_metadata.csv", index=False)

            if self.temporal_quality:
                pd.DataFrame([
                    {
                        "parcel_id": pid,
                        "n_accepted": q.get("n_accepted"),
                        "longest_gap_days": q.get("longest_gap_days"),
                    }
                    for pid, q in self.temporal_quality.items()
                ]).to_csv(
                    outdir / "temporal_quality_summary.csv",
                    index=False,
                )

            self._write_spatial_export_to_folder(outdir)
            self._write_quant_export_to_folder(outdir)
            self._write_analysis_summary(outdir)

            msg = f"Export completed.\n\nFolder:\n{outdir}\n\nKc series: {len(kc_frames)}"
            if water_frames:
                msg += f"\nCWR/IWR series: {len(water_frames)}"
            else:
                msg += "\nCWR/IWR series: not calculated"

            messagebox.showinfo("Export Kc / CWR / IWR", msg)

        except Exception as exc:
            messagebox.showerror("Export Kc / CWR / IWR", str(exc))

    def export_all_results(self):
        """Export raw/QA and processed NDVI results for all parcels."""
        if not self.ndvi_results:
            messagebox.showwarning(
                "Export all",
                "There are no NDVI results to export yet.",
            )
            return

        folder = filedialog.askdirectory(
            title="Select output folder for all NDVI results"
        )
        if not folder:
            return

        outdir = Path(folder)

        try:
            # 1) Combined RAW/QA dataset for all parcels
            raw_frames = []
            for parcel_id, df in self.ndvi_results.items():
                if df is None or df.empty:
                    continue
                tmp = df.copy()
                if "parcel_id" not in tmp.columns:
                    tmp["parcel_id"] = parcel_id
                raw_frames.append(tmp)

            if raw_frames:
                raw_all = pd.concat(raw_frames, ignore_index=True)
                raw_all.to_csv(
                    outdir / "NDVI_all_parcels_raw.csv",
                    index=False,
                )

            # 2) Individual RAW/QA file for each parcel
            raw_dir = outdir / "raw_by_parcel"
            raw_dir.mkdir(exist_ok=True)

            for parcel_id, df in self.ndvi_results.items():
                if df is None or df.empty:
                    continue
                safe_id = str(parcel_id).replace("/", "_").replace("\\", "_")
                df.to_csv(
                    raw_dir / f"{safe_id}_NDVI_raw.csv",
                    index=False,
                )

            # 3) Processed datasets, only if temporal processing exists
            processed_count = 0
            if self.temporal_results:
                proc_dir = outdir / "processed_by_parcel"
                proc_dir.mkdir(exist_ok=True)

                processed_frames = []
                daily_frames = []

                for parcel_id, result in self.temporal_results.items():
                    if not result:
                        continue

                    safe_id = str(parcel_id).replace("/", "_").replace("\\", "_")
                    method = result.get("method", "Unknown")

                    # User-selected output resolution
                    output_df = result.get("output")
                    if output_df is not None and not output_df.empty:
                        tmp = output_df.copy()
                        tmp["parcel_id"] = parcel_id
                        tmp["method"] = method
                        processed_frames.append(tmp)

                        tmp.to_csv(
                            proc_dir / f"{safe_id}_NDVI_processed.csv",
                            index=False,
                        )
                        processed_count += 1

                    # Always preserve the internal daily reconstruction separately
                    daily_df = result.get("daily")
                    if daily_df is not None and not daily_df.empty:
                        tmp_daily = daily_df.copy()
                        tmp_daily["parcel_id"] = parcel_id
                        tmp_daily["method"] = method
                        daily_frames.append(tmp_daily)

                        tmp_daily.to_csv(
                            proc_dir / f"{safe_id}_NDVI_daily_internal.csv",
                            index=False,
                        )

                if processed_frames:
                    pd.concat(processed_frames, ignore_index=True).to_csv(
                        outdir / "NDVI_all_parcels_processed.csv",
                        index=False,
                    )

                if daily_frames:
                    pd.concat(daily_frames, ignore_index=True).to_csv(
                        outdir / "NDVI_all_parcels_daily_internal.csv",
                        index=False,
                    )

            # 4) Export a compact summary of parcel metadata
            if self.gdf is not None and not self.gdf.empty:
                summary_cols = [
                    c for c in ["parcel_id", "crop", "area_ha"]
                    if c in self.gdf.columns
                ]
                if summary_cols:
                    self.gdf[summary_cols].to_csv(
                        outdir / "parcel_summary.csv",
                        index=False,
                    )

            meta = self._build_run_metadata()
            pd.DataFrame(
                [{"parameter": k, "value": v} for k, v in meta.items()]
            ).to_csv(outdir / "run_metadata.csv", index=False)

            if self.temporal_quality:
                pd.DataFrame([
                    {
                        "parcel_id": pid,
                        "n_accepted": q.get("n_accepted"),
                        "longest_gap_days": q.get("longest_gap_days"),
                    }
                    for pid, q in self.temporal_quality.items()
                ]).to_csv(
                    outdir / "temporal_quality_summary.csv",
                    index=False,
                )

            self._write_spatial_export_to_folder(outdir)
            self._write_quant_export_to_folder(outdir)
            self._write_analysis_summary(outdir)

            msg = (
                f"Export completed successfully.\n\n"
                f"Folder:\n{outdir}\n\n"
                f"Raw parcel series: {len(raw_frames)}"
            )

            if processed_count:
                msg += f"\nProcessed parcel series: {processed_count}"
            else:
                msg += "\nProcessed parcel series: none"

            messagebox.showinfo("Export all NDVI results", msg)

        except Exception as exc:
            messagebox.showerror(
                "Export all NDVI results",
                str(exc),
            )


if __name__ == "__main__":
    app = CropWaterRSApp()
    app.mainloop()
