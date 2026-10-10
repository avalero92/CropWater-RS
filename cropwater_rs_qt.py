"""CropWater-RS 1.0 RC1: native Qt scientific workspace with portable project files."""
from __future__ import annotations
import subprocess
import sys
import os
import logging
import json
import tempfile
import pandas as pd
from qt_project_io import save_archive, load_archive
from pathlib import Path

from qt_spatial_view import SpatialViewer
from qt_preprocessing_page import PreprocessingPage
from qt_quant_page import QuantPage
from qt_water_page import WaterPage
from qt_cdse_acquisition import CDSEWorker, CDSESettings, validate_cdse_inputs
from qt_cdse_raster import RasterWorker, RasterSettings, validate_raster_settings
from PySide6.QtCore import Qt, QObject, Signal, QDate
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget, QGroupBox,
    QLineEdit, QDateEdit, QSpinBox, QStatusBar, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar, QMenu
)

ROOT = Path(__file__).resolve().parent
NAV = ['Home', 'Data Acquisition', 'Preprocessing', 'Time Series',
       'Water Analysis', 'Spatial View']
STYLE = """
QMainWindow, QWidget#root {background:#edf2f6; color:#183044; font-family:Segoe UI,Arial; font-size:12px;}
QFrame#topbar {background:#102334; border:0;}
QFrame#sidebar, QFrame#inspector {background:#182b3e; border:0;}
QFrame#canvas {background:#f7fafc; border:1px solid #d4e0e9; border-radius:7px;}
QFrame#lightcard {background:#ffffff; border:1px solid #d9e4eb; border-radius:7px;}
QLabel#brand {color:#ffffff; font-size:20px; font-weight:700;}
QLabel#subbrand {color:#aac2d4; font-size:10px;}
QLabel#heading {color:#f1f7fb; font-size:14px; font-weight:600;}
QLabel#mutedDark {color:#b8c9d6;}
QLabel#canvasHeading {color:#173249; font-size:20px; font-weight:650;}
QLabel#canvasSub {color:#59748b; font-size:12px;}
QPushButton {border:1px solid #c8d6e2; border-radius:5px; padding:9px 12px; background:#fff; color:#183044;}
QPushButton:hover {background:#e6f3fa;}
QPushButton#nav {border:0; border-radius:5px; background:transparent; color:#bdcddd; padding:10px 13px; text-align:center;}
QPushButton#nav:checked {background:#144b6b; color:#ffffff; border-bottom:2px solid #1da3d4;}
QPushButton#primary {background:#087faf; color:white; border:0; font-weight:600;}
QPushButton#primary:hover {background:#0793c7;}
QFrame#sidebar QLabel, QFrame#inspector QLabel {color:#e4edf5;}
QFrame#sidebar QComboBox, QFrame#sidebar QLineEdit, QFrame#sidebar QDateEdit, QFrame#sidebar QSpinBox,
QFrame#inspector QComboBox {background:#263e54; color:#f5f9fd; border:1px solid #547087; border-radius:4px; padding:7px;}
QFrame#sidebar QCheckBox {color:#dceaf5; spacing:8px;}
QTabWidget::pane {border:1px solid #d7e1e9; background:white;}
QTabBar::tab {background:#e5edf3; padding:10px 18px; color:#2c526b;}
QTabBar::tab:selected {background:white; border-top:2px solid #0b89b8;}
QStatusBar {background:#102334; color:#e5eff7;}
"""

def label(text, object_name=None):
    w=QLabel(text)
    if object_name: w.setObjectName(object_name)
    w.setWordWrap(True)
    return w

def card(title, detail, button=None, action=None):
    box=QFrame(); box.setObjectName('lightcard')
    v=QVBoxLayout(box); v.setContentsMargins(22,20,22,20); v.setSpacing(13)
    v.addWidget(label(title,'canvasHeading'))
    v.addWidget(label(detail,'canvasSub'))
    if button:
        b=QPushButton(button); b.setObjectName('primary'); b.clicked.connect(action)
        v.addWidget(b,alignment=Qt.AlignmentFlag.AlignLeft)
    v.addStretch()
    return box

class ParcelStore(QObject):
    changed=Signal()
    def __init__(self):
        super().__init__(); self.parcels=None; self.path=None
    def set_parcels(self, parcels, path):
        self.parcels=parcels; self.path=str(path); self.changed.emit()

class AcquisitionPage(QWidget):
    """Native Qt parcel acquisition; no Tk dependency."""
    def load_credentials_txt(self):
        """Load optional CDSE credentials from a private text file (no persistence)."""
        path,_=QFileDialog.getOpenFileName(self,'Load CDSE credentials','','Text files (*.txt *.env);;All files (*)')
        if not path:return
        try:
            from qt_credentials import parse_credentials
            # UTF-8 BOM is accepted; never log file content or secrets.
            content=Path(path).read_text(encoding='utf-8-sig')
            cid,secret=parse_credentials(content)
            self.client_id.setText(cid)
            self.client_secret.setText(secret)
            self.cdse_status.setText('Credentials loaded from local file (not stored by CropWater-RS)')
        except (OSError,UnicodeError,ValueError) as exc:
            QMessageBox.warning(self,'CDSE credentials',str(exc))

    def __init__(self, store, parent=None):
        super().__init__(parent); self.store=store
        layout=QVBoxLayout(self); layout.setContentsMargins(18,18,18,18)
        layout.addWidget(label('Data Acquisition · Parcels','canvasHeading'))
        layout.addWidget(label('Import a georeferenced parcel vector once. It is shared automatically with Spatial View.','canvasSub'))
        controls=QHBoxLayout()
        self.import_button=QPushButton('Import parcel polygons'); self.import_button.setObjectName('primary')
        self.import_button.clicked.connect(self.open_parcels); controls.addWidget(self.import_button)
        self.to_map=QPushButton('Open Spatial View');controls.addWidget(self.to_map)
        controls.addStretch();layout.addLayout(controls)
        self.summary=QLabel('No parcel file loaded');layout.addWidget(self.summary)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Row','Parcel ID','Area (ha)','Attributes'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,1)
        # Native CDSE statistical acquisition; secrets are never persisted.
        cdse=QGroupBox('Copernicus Data Space · Sentinel-2 L2A NDVI statistics')
        form=QGridLayout(cdse)
        form.addWidget(QLabel('Client ID'),0,0)
        self.client_id=QLineEdit(os.getenv('CDSE_CLIENT_ID',''));form.addWidget(self.client_id,0,1)
        form.addWidget(QLabel('Client secret'),1,0)
        self.client_secret=QLineEdit(os.getenv('CDSE_CLIENT_SECRET',''))
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password);form.addWidget(self.client_secret,1,1)
        self.load_credentials_button=QPushButton('Load credentials (.txt)')
        self.load_credentials_button.setToolTip('Load a local text file; credentials are not copied to application settings.')
        self.load_credentials_button.clicked.connect(self.load_credentials_txt)
        form.addWidget(self.load_credentials_button,2,1)
        form.addWidget(QLabel('Start date'),3,0)
        self.start_date=QDateEdit(QDate(2023,1,1));self.start_date.setCalendarPopup(True);form.addWidget(self.start_date,3,1)
        form.addWidget(QLabel('End date'),4,0)
        self.end_date=QDateEdit(QDate.currentDate());self.end_date.setCalendarPopup(True);form.addWidget(self.end_date,4,1)
        form.addWidget(QLabel('Interval'),5,0)
        self.interval=QComboBox();self.interval.addItems(['P1D','P5D','P10D','P1M']);self.interval.setCurrentText('P10D');form.addWidget(self.interval,5,1)
        form.addWidget(QLabel('Parcel scope'),6,0)
        self.scope=QComboBox();self.scope.addItems(['Selected parcel','All parcels']);form.addWidget(self.scope,6,1)
        self.run_cdse=QPushButton('Acquire NDVI statistics');self.run_cdse.setObjectName('primary')
        self.run_cdse.clicked.connect(self.start_cdse);form.addWidget(self.run_cdse,7,0,1,2)
        self.progress=QProgressBar();self.progress.setValue(0);form.addWidget(self.progress,8,0,1,2)
        self.cdse_status=QLabel('Ready · CDSE credentials are used only for this request')
        form.addWidget(self.cdse_status,9,0,1,2)
        layout.addWidget(cdse)
        self.worker=None;self.cdse_results=None
        self.export_cdse=QPushButton('Export NDVI statistics CSV');self.export_cdse.setEnabled(False)
        self.export_cdse.clicked.connect(self.export_statistics);layout.addWidget(self.export_cdse)
        raster=QGroupBox('Sentinel-2 L2A · Pixel-level NDVI raster (Process API)')
        rg=QGridLayout(raster)
        rg.addWidget(QLabel('Resolution'),0,0)
        self.raster_resolution=QComboBox();self.raster_resolution.addItems(['10','20','30']);rg.addWidget(self.raster_resolution,0,1)
        rg.addWidget(QLabel('Scope'),1,0);rg.addWidget(QLabel('Selected parcel (one GeoTIFF per request)'),1,1)
        self.run_raster=QPushButton('Acquire NDVI GeoTIFF');self.run_raster.setObjectName('primary')
        self.run_raster.clicked.connect(self.start_raster);rg.addWidget(self.run_raster,2,0,1,2)
        self.raster_status=QLabel('Ready · select a parcel and specify a date window');rg.addWidget(self.raster_status,3,0,1,2)
        layout.addWidget(raster)
        self.raster_worker=None
        layout.addWidget(label('Raster is a least-cloud mosaic over the chosen dates, masked to the selected parcel. It is not a per-date raster series.','canvasSub'))
        self.store.changed.connect(self.update_table)
    def start_raster(self):
        try:
            if self.store.parcels is None:raise ValueError('Import parcels first.')
            index=self.table.currentRow()
            if index<0:raise ValueError('Select one parcel in the table.')
            path,_=QFileDialog.getSaveFileName(self,'Save NDVI GeoTIFF',f'CDSE_NDVI_parcel_{index+1}.tif','GeoTIFF (*.tif)')
            if not path:return
            if not path.lower().endswith(('.tif','.tiff')):path+='.tif'
            settings=RasterSettings(self.client_id.text().strip(),self.client_secret.text(),
                self.start_date.date().toString('yyyy-MM-dd'),self.end_date.date().toString('yyyy-MM-dd'),
                int(self.raster_resolution.currentText()),path)
            validate_raster_settings(settings)
            self.raster_worker=RasterWorker(self.store.parcels.iloc[index].geometry,settings)
            self.raster_worker.progress.connect(lambda percent,msg:self.raster_status.setText(f'{percent}% · {msg}'))
            self.raster_worker.completed.connect(self._raster_completed)
            self.raster_worker.failed.connect(self._raster_failed)
            self.run_raster.setEnabled(False);self.raster_status.setText('Requesting raster…')
            self.raster_worker.start()
        except Exception as exc:QMessageBox.warning(self,'Raster acquisition',str(exc))

    def _raster_completed(self,path,count):
        self.run_raster.setEnabled(True)
        self.raster_status.setText(f'Saved {Path(path).name} · {count:,} valid pixels')
        self.raster_ready.emit(path)

    def _raster_failed(self,message):
        self.run_raster.setEnabled(True);self.raster_status.setText('Raster acquisition failed')
        QMessageBox.warning(self,'CDSE Process API',message)

    raster_ready=Signal(str)
    statistics_ready=Signal(object)

    def start_cdse(self):
        try:
            if self.store.parcels is None:raise ValueError('Import parcels before acquiring NDVI statistics.')
            selected=self.table.currentRow()
            if self.scope.currentIndex()==0 and selected<0:raise ValueError('Select a parcel in the table, or choose All parcels.')
            settings=CDSESettings(self.client_id.text().strip(),self.client_secret.text(),
                self.start_date.date().toString('yyyy-MM-dd'),self.end_date.date().toString('yyyy-MM-dd'),self.interval.currentText())
            validate_cdse_inputs(settings)
            gdf=self.store.parcels.iloc[[selected]].copy() if self.scope.currentIndex()==0 else self.store.parcels.copy()
            self.worker=CDSEWorker(gdf,settings)
            self.worker.progress.connect(self._cdse_progress)
            self.worker.completed.connect(self._cdse_completed)
            self.worker.failed.connect(self._cdse_failed)
            self.run_cdse.setEnabled(False);self.export_cdse.setEnabled(False)
            self.progress.setValue(0);self.cdse_status.setText('Requesting Sentinel-2 NDVI statistics…')
            self.worker.start()
        except Exception as exc:QMessageBox.warning(self,'CDSE acquisition',str(exc))

    def _cdse_progress(self,value,message):
        self.progress.setValue(value);self.cdse_status.setText(message)

    def _cdse_completed(self,df):
        self.cdse_results=df
        self.statistics_ready.emit(df)
        self.run_cdse.setEnabled(True)
        self.export_cdse.setEnabled(not df.empty)
        self.progress.setValue(100)
        self.cdse_status.setText(f'Completed · {len(df)} observations; {len(df.attrs.get("errors", []))} parcel errors. Export CSV to save results.')

    def _cdse_failed(self,message):
        self.run_cdse.setEnabled(True)
        self.cdse_status.setText('CDSE acquisition failed; see details')
        QMessageBox.warning(self,'CDSE acquisition failed',message)

    def export_statistics(self):
        if self.cdse_results is None or self.cdse_results.empty:return
        path,_=QFileDialog.getSaveFileName(self,'Export CDSE NDVI statistics','CDSE_NDVI_statistics.csv','CSV (*.csv)')
        if path:
            try:
                self.cdse_results.to_csv(path,index=False)
                self.cdse_status.setText(f'Exported · {Path(path).name}')
            except Exception as exc:QMessageBox.warning(self,'Export failed',str(exc))

    def open_parcels(self):
        path,_=QFileDialog.getOpenFileName(self,'Import parcel polygons','','Vector (*.gpkg *.geojson *.json *.shp)')
        if not path:return
        try:
            import geopandas as gpd
            gdf=gpd.read_file(path)
            if gdf.empty:raise ValueError('Vector file contains no features')
            if gdf.crs is None:raise ValueError('Vector file has no CRS')
            gdf=gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy().to_crs(epsg=3857)
            if gdf.empty:raise ValueError('No valid geometries')
            self.store.set_parcels(gdf,path)
        except Exception as exc: QMessageBox.warning(self,'Cannot import parcels',str(exc))
    def update_table(self):
        gdf=self.store.parcels
        if gdf is None:return
        self.summary.setText(f'{len(gdf)} parcels · {Path(self.store.path).name} · CRS: EPSG:3857')
        self.table.setRowCount(min(len(gdf),500))
        ids=[c for c in gdf.columns if c.lower() in ('id','parcel_id','id_parcela','parcela','name')]
        key=ids[0] if ids else None
        for i,(_,r) in enumerate(gdf.head(500).iterrows()):
            vals=[str(i+1),str(r[key]) if key else str(i+1),f'{r.geometry.area/10000:.3f}',str(len(gdf.columns)-1)]
            for j,value in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(value))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('CropWater-RS — 2.0.0 | Untitled project')
        self.resize(1600,900)
        ico=ROOT/'assets'/'cropwater_rs.ico'
        if ico.exists(): self.setWindowIcon(QIcon(str(ico)))
        self._legacy=None
        self.project_path=None
        self.project_name="Untitled project"
        self._project_loading=False
        self._inspector_user_hidden=True
        self.parcel_store=ParcelStore()
        root=QWidget(); root.setObjectName('root'); self.setCentralWidget(root)
        outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        top=QFrame(); top.setObjectName('topbar'); row=QHBoxLayout(top); row.setContentsMargins(18,8,18,8)
        logo=QLabel(); logo.setStyleSheet('background: transparent; border: none;'); pm=QPixmap(str(ROOT/'assets'/'cropwater_rs_header_clean.png'))
        if not pm.isNull(): logo.setPixmap(pm.scaled(56,56,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        row.addWidget(logo)
        brand=QVBoxLayout(); brand.setSpacing(0); brand.addWidget(label('CropWater-RS','brand')); brand.addWidget(label('Remote Sensing · Phenology · Irrigation','subbrand'))
        row.addLayout(brand); row.addSpacing(12)
        project_menu=QMenu(self)
        for caption,handler in [('New Project',self.new_project),('Open Project...',self.open_project),('Save Project',self.save_project),('Save Project As...',self.save_project_as)]:
            project_menu.addAction(caption,handler)
        project_button=QPushButton('Project ▾');project_button.setMenu(project_menu);row.addWidget(project_button)
        row.addSpacing(12)
        self.buttons=[]
        for idx,name in enumerate(NAV):
            b=QPushButton(name); b.setObjectName('nav'); b.setCheckable(True)
            b.clicked.connect(lambda checked=False, i=idx:self.change_page(i))
            row.addWidget(b); self.buttons.append(b)
        row.addStretch()
        self.toggle_left=QPushButton('◧ Overview');self.toggle_left.setToolTip('Show or hide the live module overview')
        self.toggle_left.clicked.connect(lambda:self._toggle_panel(0));row.addWidget(self.toggle_left)
        self.toggle_right=QPushButton('◨ Details');self.toggle_right.setToolTip('Show or hide live project details')
        self.toggle_right.clicked.connect(lambda:self._toggle_panel(2));row.addWidget(self.toggle_right)
        outer.addWidget(top)
        self.main_splitter=QSplitter(Qt.Orientation.Horizontal); split=self.main_splitter; split.setChildrenCollapsible(True)
        self._saved_panel_sizes=[250,1100,225]
        self.sidebar=QFrame(); self.sidebar.setObjectName('sidebar'); self.side_layout=QVBoxLayout(self.sidebar)
        self.side_layout.setContentsMargins(15,17,15,15)
        self.side_title=label('Project Overview','heading'); self.side_layout.addWidget(self.side_title)
        self.side_content=QStackedWidget(); self.side_layout.addWidget(self.side_content)
        self._make_sidebar()
        split.addWidget(self.sidebar)
        self.workspace=QStackedWidget(); self._make_workspace(); split.addWidget(self.workspace)
        self.inspector=QFrame(); self.inspector.setObjectName('inspector')
        self.inspector_layout=QVBoxLayout(self.inspector); self.inspector_layout.setContentsMargins(14,17,14,15)
        self.inspector_layout.addWidget(label('Live session details','heading'))
        self.inspector_layout.addSpacing(20)
        self.inspector_hint=label('No parcels imported.','mutedDark')
        self.inspector_layout.addWidget(self.inspector_hint)
        self.inspector_layout.addStretch()
        split.addWidget(self.inspector)
        split.setStretchFactor(0,0);split.setStretchFactor(1,1);split.setStretchFactor(2,0)
        split.setSizes(self._saved_panel_sizes);outer.addWidget(split,1)
        self.inspector.hide()
        status=QStatusBar(); self.setStatusBar(status); status.showMessage('2.0.0 · Portable project workspace')
        self.setStyleSheet(STYLE); self._connect_overview_updates(); self.change_page(0)

    def _project_tables(self):
        p,q,w=self.preprocessing_page,self.quant_page,self.water_page
        return dict(pre_raw=p.raw,pre_cleaned=p.cleaned,pre_summary=p.summary,
                    pre_reconstructed=p.reconstructed,pre_diagnostics=p.reconstruction_diagnostics,
                    quant_data=q.data,quant_results=q.results,water_ndvi=w.ndvi,water_weather=w.weather,
                    water_results=w.results,water_phase_summary=w.phase_summary,water_phase_daily=w.phase_daily)

    def _project_state(self):
        p,q,w=self.preprocessing_page,self.quant_page,self.water_page
        return dict(project_name=self.project_name,parcel_source=self.parcel_store.path,
                    preprocessing=dict(threshold=p.threshold.value(),samples=p.samples.value(),
                    method=p.recon_method.currentText(),lam=p.recon_lambda.value(),window=p.recon_window.value(),clip=p.recon_clip.isChecked()),
                    quant=dict(start_overrides=q.start_overrides,selected_ids=sorted(q.selected_ids),
                    manual_selected_ids=sorted(q.manual_selected_ids),scope=q.scope.currentIndex(),
                    start_mode=q.start_mode.currentIndex(),spins=[x.value() for x in q.spins]),
                    water=dict(overrides=w.overrides,manual_crops=w.manual_crops,
                    crop_validated=w.crop_validated,relation_validated=w.relation_validated,
                    sowing_overrides=w.sowing_overrides,sowing_offsets=w.sowing_offsets,
                    analysis_scope=w.analysis_scope.currentIndex(),crop_field=w.crop_field.currentData(),
                    sowing_field=w.sowing_field.currentData(),plot_parcels=w.plot_parcels),
                    page=self.workspace.currentIndex())

    def _write_project(self,path):
        target=Path(path)
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=None
        try:
            with tempfile.NamedTemporaryFile(prefix='.cwrs_',suffix='.tmp',dir=target.parent,delete=False) as f:tmp=Path(f.name)
            save_archive(tmp,self._project_tables(),self._project_state(),self.parcel_store.parcels)
            os.replace(tmp,target)
        finally:
            if tmp and tmp.exists():tmp.unlink()
        self.project_path=str(target)
        self.project_name=target.stem
        self._update_project_label()
        self.statusBar().showMessage('Project saved: '+str(target),8000)

    def save_project(self):
        if not self.project_path:return self.save_project_as()
        try:self._write_project(self.project_path)
        except Exception as exc:QMessageBox.critical(self,'Save project failed',str(exc))

    def save_project_as(self):
        path,_=QFileDialog.getSaveFileName(self,'Save CropWater-RS project',self.project_path or 'CropWater_Project.cwrs','CropWater-RS project (*.cwrs)')
        if not path:return
        if not path.lower().endswith('.cwrs'):path+='.cwrs'
        try:self._write_project(path)
        except Exception as exc:QMessageBox.critical(self,'Save project failed',str(exc))

    def _update_project_label(self):
        self.setWindowTitle('CropWater-RS — 2.0.0 | '+self.project_name)
        if hasattr(self,'home_project_label'):
            self.home_project_label.setText(self.project_name+' · '+(self.project_path or 'Not saved'))

    def _restore_project(self,tables,state,parcels,path):
        p,q,w=self.preprocessing_page,self.quant_page,self.water_page
        self._project_loading=True
        try:
            # Clear old data and emit existing dependency signals in their normal order.
            p.set_data(tables['pre_raw'], 'Project archive') if 'pre_raw' in tables else p.set_data(pd.DataFrame(), 'Empty project')
            if parcels is not None:self.parcel_store.set_parcels(parcels,state.get('parcel_source') or 'Embedded GeoJSON')
            else:
                self.parcel_store.parcels=None;self.parcel_store.path=None;self.parcel_store.changed.emit()
            pp=state.get('preprocessing',{})
            for widget,value in [(p.threshold,pp.get('threshold',50)),(p.samples,pp.get('samples',1)),
                                 (p.recon_lambda,pp.get('lam',100)),(p.recon_window,pp.get('window',21))]:
                widget.blockSignals(True);widget.setValue(value);widget.blockSignals(False)
            p.recon_method.blockSignals(True);p.recon_method.setCurrentText(pp.get('method','Whittaker'));p.recon_method.blockSignals(False)
            p.recon_clip.blockSignals(True);p.recon_clip.setChecked(pp.get('clip',True));p.recon_clip.blockSignals(False)
            for key,attr in [('pre_cleaned','cleaned'),('pre_summary','summary'),('pre_reconstructed','reconstructed'),('pre_diagnostics','reconstruction_diagnostics')]:setattr(p,attr,tables.get(key))
            p.export_btn.setEnabled(p.cleaned is not None);p.summary_btn.setEnabled(p.summary is not None);p.recon_export.setEnabled(p.reconstructed is not None)
            if p.cleaned is not None and 'parcel_id' in p.cleaned:
                p.parcel.blockSignals(True);p.parcel.clear();p.parcel.addItems(sorted(p.cleaned.parcel_id.dropna().astype(str).unique()));p.parcel.blockSignals(False)
            if p.reconstructed is not None:
                q.set_data(p.reconstructed,'Project archive');w.set_data(p.reconstructed)
            elif 'quant_data' in tables:
                q.set_data(tables['quant_data'],'Project archive');w.set_data(tables['quant_data'])
            else:q.invalidate_data();w.invalidate_data()
            qq=state.get('quant',{})
            q.start_overrides=qq.get('start_overrides',{});q.selected_ids=set(qq.get('selected_ids',[]));q.manual_selected_ids=set(qq.get('manual_selected_ids',[]))
            for widget,val in zip(q.spins,qq.get('spins',[])):widget.setValue(val)
            q.scope.setCurrentIndex(qq.get('scope',0));q.start_mode.setCurrentIndex(qq.get('start_mode',0))
            q.results=tables.get('quant_results');q.export_btn.setEnabled(q.results is not None)
            if q.results is not None:
                q.table.setColumnCount(len(q.results.columns));q.table.setRowCount(len(q.results));q.table.setHorizontalHeaderLabels(list(q.results.columns))
                for i,row in enumerate(q.results.itertuples(index=False,name=None)):
                    for j,value in enumerate(row):q.table.setItem(i,j,QTableWidgetItem(str(value)))
            if 'water_weather' in tables:w.set_weather(tables['water_weather'])
            ww=state.get('water',{})
            for attr in ('overrides','manual_crops','crop_validated','relation_validated','sowing_overrides','sowing_offsets','plot_parcels'):
                if attr in ww:setattr(w,attr,ww[attr])
            w.analysis_scope.blockSignals(True);w.analysis_scope.setCurrentIndex(ww.get('analysis_scope',0));w.analysis_scope.blockSignals(False)
            for widget,key in [(w.crop_field,'crop_field'),(w.sowing_field,'sowing_field')]:
                idx=widget.findData(ww.get(key));widget.setCurrentIndex(max(idx,0))
            w.results=tables.get('water_results');w.phase_summary=tables.get('water_phase_summary');w.phase_daily=tables.get('water_phase_daily')
            w.export_button.setEnabled(w.results is not None);w.phase_export.setEnabled(w.phase_summary is not None)
            w.update_assignment_table()
            if w.results is not None:
                w.status.setText(f'Project restored · {len(w.results):,} daily water records')
                try:w.plot_results()
                except Exception:pass
            # Plotting is non-critical: a visualization error must not abort data restoration.
            for label, draw in (("QUANT", q.draw), ("Preprocessing", p.draw_plot)):
                try:
                    draw()
                except Exception as exc:
                    logging.exception("Project restored, but %s plot could not be rendered", label)
                    self.statusBar().showMessage(f"Project restored; {label} plot warning: {exc}", 12000)
            self.project_path=str(path);self.project_name=Path(path).stem
            self._update_project_label();self.change_page(min(max(state.get('page',0),0),len(NAV)-1))
            self.statusBar().showMessage('Project restored: '+str(path),8000)
        finally:self._project_loading=False

    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open CropWater-RS project','','CropWater-RS project (*.cwrs)')
        if not path:return
        try:
            tables,state,parcels=load_archive(path)
            self._restore_project(tables,state,parcels,path)
        except Exception as exc:QMessageBox.critical(self,'Open project failed',str(exc))

    def new_project(self):
        if QMessageBox.question(self,'New project','Discard the current session? Save the current project first if needed.',
                                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        p,q,w=self.preprocessing_page,self.quant_page,self.water_page
        p.set_data(pd.DataFrame(),'New project');q.invalidate_data();w.invalidate_data()
        w.weather=None;w.overrides.clear();w.manual_crops.clear();w.sowing_overrides.clear();w.crop_validated.clear();w.relation_validated.clear()
        self.parcel_store.parcels=None;self.parcel_store.path=None;self.parcel_store.changed.emit()
        self.project_path=None;self.project_name='Untitled project';self._update_project_label();self.change_page(0)

    def _toggle_panel(self, index):
        panel=self.sidebar if index==0 else self.inspector
        if panel.isVisible():
            if index==2:self._inspector_user_hidden=True
            sizes=self.main_splitter.sizes()
            if sizes[index]>0:self._saved_panel_sizes[index]=sizes[index]
            panel.hide()
        else:
            if index==2:self._inspector_user_hidden=False
            panel.show()
            sizes=self.main_splitter.sizes()
            sizes[index]=self._saved_panel_sizes[index]
            self.main_splitter.setSizes(sizes)

    def _make_sidebar(self):
        """Read-only live indicators, never simulated processing controls."""
        self.overview_pages=[]
        for _ in NAV:
            page=QWidget(); v=QVBoxLayout(page)
            v.setContentsMargins(0,12,0,0); v.setSpacing(14)
            state=label('Waiting for session data','mutedDark')
            v.addWidget(state)
            v.addStretch()
            self.side_content.addWidget(page)
            self.overview_pages.append(state)
        self.side_layout.addWidget(label('Live status only. Configure and run analyses in the active module.','mutedDark'))

    def _connect_overview_updates(self):
        self.parcel_store.changed.connect(self._refresh_overview)
        self.preprocessing_page.reconstructed_ready.connect(lambda _df:self._refresh_overview())
        self.preprocessing_page.reconstructed_invalidated.connect(self._refresh_overview)

    @staticmethod
    def _count_parcels(df):
        if df is None:return 0
        try:
            if 'parcel_id' in df.columns:return int(df['parcel_id'].nunique())
            return len(df)
        except (AttributeError,TypeError,KeyError):return 0

    def _session_counts(self):
        parcels=len(self.parcel_store.parcels) if self.parcel_store.parcels is not None else 0
        raw=self._count_parcels(self.preprocessing_page.raw)
        reconstructed=self._count_parcels(self.preprocessing_page.reconstructed)
        q=self.quant_page.results
        complete=int(q['status'].eq('Complete').sum()) if q is not None and 'status' in q else 0
        water=self._count_parcels(self.water_page.results)
        phase=self._count_parcels(self.water_page.phase_summary)
        return parcels,raw,reconstructed,complete,water,phase

    def _refresh_overview(self):
        parcels,raw,reconstructed,complete,water,phase=self._session_counts()
        entries=[
            f'Imported parcels: {parcels}\nNDVI available: {raw}\nReconstructed: {reconstructed}\nQUANT complete: {complete}\nWater analyzed: {water}',
            f'Imported parcel polygons: {parcels}\nNDVI parcels available: {raw}',
            f'NDVI input parcels: {raw}\nReconstructed parcels: {reconstructed}',
            f'Reconstructed parcels: {reconstructed}\nQUANT complete: {complete}',
            f'Water analyzed parcels: {water}\nValid phase summaries: {phase}',
            f'Imported parcel polygons: {parcels}\nSpatial layers are managed in Spatial View.',
        ]
        for widget,message in zip(self.overview_pages,entries):widget.setText(message)
        path=self.parcel_store.path
        self.inspector_hint.setText(
            f'Parcel source: {Path(path).name if path else "Not loaded"}\n'
            f'Parcels: {parcels}\nNDVI: {raw}\nReconstructed: {reconstructed}\n'
            f'QUANT complete: {complete}\nWater analyzed: {water}\nPhase summaries: {phase}'
        )
        if hasattr(self,'home_stats'):
            for widget,value in zip(self.home_stats,(parcels,raw,reconstructed,complete,water,phase)):
                widget.setText(str(value))

    def _make_home(self):
        page=QWidget(); lay=QVBoxLayout(page); lay.setContentsMargins(26,24,26,24); lay.setSpacing(18)
        lay.addWidget(label('Project Overview','canvasHeading'))
        lay.addWidget(label('Current project · Live scientific processing status. Use Project ▾ to save or reopen your work.','canvasSub'))
        self.home_project_label=label('Untitled project · Not saved','canvasSub');lay.addWidget(self.home_project_label)
        grid=QGridLayout(); self.home_stats=[]
        names=['Imported parcels','NDVI parcels','Reconstructed parcels','QUANT complete','Water analyzed','Phase summaries']
        for i,name in enumerate(names):
            tile=QFrame();tile.setObjectName('lightcard');v=QVBoxLayout(tile)
            v.addWidget(label(name,'canvasSub'))
            number=label('0','canvasHeading');v.addWidget(number);self.home_stats.append(number)
            grid.addWidget(tile,i//3,i%3)
        lay.addLayout(grid)
        lay.addWidget(label('Scientific workflow','canvasHeading'))
        for index,title,description in [
            (1,'1 · Data Acquisition','Import parcel boundaries and retrieve Sentinel-2 observations'),
            (2,'2 · Preprocessing','Quality control and daily NDVI reconstruction'),
            (3,'3 · Time Series / QUANT','Calculate phenological transitions Q1–Q4'),
            (4,'4 · Water Analysis','Evaluate Kc, ETc, IWR and phase statistics'),
            (5,'Spatial View','Inspect parcel geometries and raster layers')]:
            button=QPushButton(f'{title}  →  {description}')
            button.clicked.connect(lambda checked=False,i=index:self.change_page(i))
            lay.addWidget(button)
        lay.addStretch()
        return page

    def _make_workspace(self):
        descriptions=[
          ('Welcome to CropWater-RS','A unified workspace for satellite observations, crop phenology and irrigation assessment.'),
          ('Data acquisition','Copernicus Data Space Ecosystem · Sentinel-2 · parcel-based acquisition.'),
          ('Preprocessing','Quality control, time-series preparation and phenological reconstruction.'),
          ('Time series analysis','Observed NDVI, reconstructed vegetation dynamics and phenological transitions.'),
          ('Water analysis','Kc, ETc and irrigation water requirements with phase-based comparisons.'),
          ('Spatial view','Esri Satellite, parcel statistics and Sentinel-2 NDVI layers.')
        ]
        for idx,(title,desc) in enumerate(descriptions):
            wrapper=QWidget(); v=QVBoxLayout(wrapper); v.setContentsMargins(16,16,16,16)
            if idx==0:
                v.addWidget(self._make_home(),1)
            elif idx==1:
                self.acquisition_page=AcquisitionPage(self.parcel_store)
                self.acquisition_page.to_map.clicked.connect(lambda:self.change_page(5))
                self.acquisition_page.raster_ready.connect(self._show_acquired_raster)
                self.acquisition_page.statistics_ready.connect(self._receive_statistics)
                v.addWidget(self.acquisition_page,1)
            elif idx==2:
                self.preprocessing_page=PreprocessingPage()
                v.addWidget(self.preprocessing_page,1)
            elif idx==3:
                self.quant_page=QuantPage()
                self.quant_page.set_parcel_store(self.parcel_store)
                self.preprocessing_page.reconstructed_ready.connect(self._receive_reconstructed)
                self.preprocessing_page.reconstructed_invalidated.connect(self.quant_page.invalidate_data)
                v.addWidget(self.quant_page,1)
            elif idx==4:
                self.water_page=WaterPage()
                self.water_page.set_parcel_store(self.parcel_store)
                self.water_page.set_quant_page(self.quant_page)
                self.preprocessing_page.reconstructed_ready.connect(self.water_page.set_data)
                self.preprocessing_page.reconstructed_invalidated.connect(self.water_page.invalidate_data)
                v.addWidget(self.water_page,1)
            elif idx==5:
                self.spatial_viewer=SpatialViewer(parcel_store=self.parcel_store,cdse_provider=self._cdse_settings)
                v.addWidget(self.spatial_viewer,1)
            self.workspace.addWidget(wrapper)

    def _receive_reconstructed(self,df):
        self.quant_page.set_data(df)
        self.statusBar().showMessage(f'{len(df):,} daily NDVI observations transferred to QUANT')
        self._refresh_overview()

    def _receive_statistics(self,df):
        self.preprocessing_page.set_data(df)
        self.statusBar().showMessage(f"{len(df)} NDVI observations available in Preprocessing")
        self._refresh_overview()

    def _cdse_settings(self):
        page=self.acquisition_page
        return (page.client_id.text().strip(),page.client_secret.text(),
                page.start_date.date().toString('yyyy-MM-dd'),
                page.end_date.date().toString('yyyy-MM-dd'),
                int(page.raster_resolution.currentText()))

    def _show_acquired_raster(self,path):
        self.change_page(5)
        self.spatial_viewer.load_raster_file(path)
        self.statusBar().showMessage(f'CDSE NDVI raster loaded · {Path(path).name}')

    def change_page(self,index):
        self.workspace.setCurrentIndex(index); self.side_content.setCurrentIndex(index)
        self.side_title.setText(NAV[index]+' · Overview')
        self._refresh_overview()
        for i,b in enumerate(self.buttons): b.setChecked(i==index)
        if getattr(self,'_inspector_user_hidden',True):
            self.inspector.hide()
        else:
            self.inspector.show()

    def launch_legacy(self):
        script=ROOT/'cropwater_rs.py'
        try:
            self._legacy=subprocess.Popen([sys.executable,str(script)],cwd=str(ROOT))
            self.statusBar().showMessage('Classic CropWater-RS launched in a separate process')
        except OSError as exc:
            QMessageBox.critical(self,'Cannot launch classic UI',str(exc))

def main():
    app=QApplication(sys.argv)
    app.setApplicationName('CropWater-RS')
    w=MainWindow(); w.show()
    return app.exec()

if __name__=='__main__': raise SystemExit(main())
