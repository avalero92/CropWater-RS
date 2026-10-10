"""Native PySide6 preprocessing of CDSE NDVI parcel statistics."""
from pathlib import Path
import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,
    QDoubleSpinBox,QSpinBox,QComboBox,QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QSplitter)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from qt_preprocessing_core import quality_control
from qt_reconstruction_core import reconstruct_qc, METHODS

class PreprocessingPage(QWidget):
    reconstructed_ready=Signal(object)
    reconstructed_invalidated=Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.raw=None;self.cleaned=None;self.summary=None;self.reconstructed=None;self.reconstruction_diagnostics=None;self.reconstruction_failures=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(18,16,18,16)
        heading=QLabel("Preprocessing · NDVI quality control");heading.setStyleSheet("font-size:20px;font-weight:600;color:#173249")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Inspect CDSE parcel statistics, flag invalid observations, and export traceable QC results."))
        row=QHBoxLayout()
        self.open_btn=QPushButton("Open NDVI CSV");self.open_btn.clicked.connect(self.open_csv);row.addWidget(self.open_btn)
        self.threshold=QDoubleSpinBox();self.threshold.setRange(0,100);self.threshold.setValue(50);self.threshold.setSuffix(" %");self.threshold.setToolTip("Minimum valid pixel fraction");row.addWidget(QLabel("Minimum valid pixels"));row.addWidget(self.threshold)
        self.samples=QSpinBox();self.samples.setRange(1,1000000);self.samples.setValue(1);row.addWidget(QLabel("Minimum samples"));row.addWidget(self.samples)
        self.run_btn=QPushButton("Run quality control");self.run_btn.setObjectName("primary");self.run_btn.clicked.connect(self.run_qc);row.addWidget(self.run_btn)
        layout.addLayout(row)
        second=QHBoxLayout();second.addWidget(QLabel("Parcel"));self.parcel=QComboBox();self.parcel.currentIndexChanged.connect(self.draw_plot);second.addWidget(self.parcel)
        self.export_btn=QPushButton("Export annotated CSV");self.export_btn.clicked.connect(self.export_csv);second.addWidget(self.export_btn)
        self.summary_btn=QPushButton("Export QC summary");self.summary_btn.clicked.connect(self.export_summary);second.addWidget(self.summary_btn)
        second.addStretch();layout.addLayout(second)
        self.status=QLabel("Load a CSV or transfer acquired statistics from Data Acquisition.");layout.addWidget(self.status)
        recon=QHBoxLayout()
        recon.addWidget(QLabel('Time-series reconstruction'))
        self.recon_method=QComboBox();self.recon_method.addItems(METHODS);self.recon_method.setCurrentText('Whittaker');self.recon_method.currentTextChanged.connect(self._update_method_controls);recon.addWidget(self.recon_method)
        self.lambda_label=QLabel('λ');recon.addWidget(self.lambda_label);self.recon_lambda=QDoubleSpinBox();self.recon_lambda.setRange(0.01,10000000);self.recon_lambda.setValue(100);self.recon_lambda.setDecimals(2);recon.addWidget(self.recon_lambda)
        self.window_label=QLabel('SG window');recon.addWidget(self.window_label);self.recon_window=QSpinBox();self.recon_window.setRange(5,365);self.recon_window.setSingleStep(2);self.recon_window.setValue(21);recon.addWidget(self.recon_window)
        self.recon_clip=QCheckBox('Constrain NDVI [0,1]');self.recon_clip.setChecked(True);recon.addWidget(self.recon_clip)
        self.recon_run=QPushButton('Reconstruct daily NDVI');self.recon_run.setObjectName('primary');self.recon_run.clicked.connect(self.run_reconstruction);recon.addWidget(self.recon_run)
        layout.addLayout(recon)
        self.method_hint=QLabel();layout.addWidget(self.method_hint)
        self.reset_params=QPushButton('Reset method defaults');self.reset_params.clicked.connect(self._reset_method_defaults)
        tools=QHBoxLayout();tools.addWidget(self.reset_params);self.recon_export=QPushButton('Export reconstructed CSV');self.recon_export.clicked.connect(self.export_reconstructed);self.recon_export.setEnabled(False);tools.addWidget(self.recon_export)
        self.recon_status=QLabel('Run quality control, then reconstruct. Results transfer to QUANT automatically.');tools.addWidget(self.recon_status,1);layout.addLayout(tools)
        split=QSplitter(Qt.Orientation.Vertical)
        self.figure=Figure(figsize=(9,3),dpi=100);self.canvas=FigureCanvasQTAgg(self.figure);split.addWidget(self.canvas)
        self.table=QTableWidget();self.table.setColumnCount(5);self.table.setHorizontalHeaderLabels(["Parcel","Date","NDVI P50","Accepted","QC reason"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);split.addWidget(self.table)
        split.setSizes([330,250]);layout.addWidget(split,1)
        self.export_btn.setEnabled(False);self.summary_btn.setEnabled(False)
        self.threshold.valueChanged.connect(self._invalidate_qc)
        self.samples.valueChanged.connect(self._invalidate_qc)
        self.recon_method.currentTextChanged.connect(self._invalidate_reconstruction)
        self.recon_lambda.valueChanged.connect(self._invalidate_reconstruction)
        self.recon_window.valueChanged.connect(self._invalidate_reconstruction)
        self.recon_clip.toggled.connect(self._invalidate_reconstruction)
        self._update_method_controls()
    def _update_method_controls(self,*args):
        method=self.recon_method.currentText()
        wh=method=='Whittaker';sg=method=='Savitzky-Golay'
        self.lambda_label.setVisible(wh);self.recon_lambda.setVisible(wh)
        self.window_label.setVisible(sg);self.recon_window.setVisible(sg)
        hints={'Whittaker':'λ controls smoothness (larger = smoother).','Savitzky-Golay':'Odd window length; original scientific core fixes polynomial order at 2.','Kalman':'Original core estimates process and observation noise automatically; no manual noise controls.','Linear interpolation':'No smoothing parameters.'}
        self.method_hint.setText(hints.get(method,''))
    def _reset_method_defaults(self):
        self.recon_lambda.setValue(100.0);self.recon_window.setValue(21)
    def _invalidate_reconstruction(self,*args):
        if self.reconstructed is not None:
            self.reconstructed=None;self.reconstruction_diagnostics=None;self.recon_export.setEnabled(False)
            self.recon_status.setText('Reconstruction parameters changed. Reconstruct again before QUANT.')
            self.reconstructed_invalidated.emit()
            if self.cleaned is not None:self.draw_plot()
    def _invalidate_qc(self,*args):
        if self.cleaned is not None:
            self.cleaned=None;self.summary=None;self.export_btn.setEnabled(False);self.summary_btn.setEnabled(False)
            self.status.setText('QC parameters changed. Run quality control again.')
            self._invalidate_reconstruction()
    def open_csv(self):
        path,_=QFileDialog.getOpenFileName(self,"Open NDVI statistics CSV","","CSV (*.csv)")
        if path:
            try:self.set_data(pd.read_csv(path),Path(path).name)
            except Exception as exc:QMessageBox.warning(self,"Cannot open CSV",str(exc))
    def set_data(self,df,source="Data Acquisition"):
        self._invalidate_reconstruction();self.raw=df.copy(deep=True);self.cleaned=None;self.summary=None;self.reconstructed=None;self.recon_export.setEnabled(False)
        self.status.setText(f"Loaded {len(df):,} observations · {source}. Run QC to review them.")
        self.export_btn.setEnabled(False);self.summary_btn.setEnabled(False)
        self.parcel.clear();self.table.setRowCount(0);self.figure.clear();self.canvas.draw_idle()
    def run_qc(self):
        if self.raw is None:
            QMessageBox.information(self,"Preprocessing","Load or acquire NDVI statistics first.");return
        try:
            self.cleaned,self.summary=quality_control(self.raw,self.threshold.value(),self.samples.value())
            self._invalidate_reconstruction()
            self.parcel.blockSignals(True);self.parcel.clear()
            self.parcel.addItems(sorted(self.cleaned["parcel_id"].dropna().astype(str).unique()))
            self.parcel.blockSignals(False)
            n=int(self.cleaned["accepted"].sum());total=len(self.cleaned)
            self.status.setText(f"QC completed · {total:,} observations · {n:,} accepted · {total-n:,} rejected · {len(self.summary)} parcels")
            self.export_btn.setEnabled(True);self.summary_btn.setEnabled(True);self.draw_plot()
        except Exception as exc:QMessageBox.warning(self,"Quality control failed",str(exc))
    def draw_plot(self,*args):
        if self.cleaned is None:return
        parcel=self.parcel.currentText()
        part=self.cleaned[self.cleaned["parcel_id"].astype(str).eq(parcel)].copy()
        self.figure.clear();ax=self.figure.add_subplot(111)
        # Always pass genuine datetime values to Matplotlib, not categorical strings.
        part["date_start"] = pd.to_datetime(part["date_start"], errors="coerce")
        part = part.dropna(subset=["date_start"])
        good=part[part["accepted"].fillna(False).astype(bool)];bad=part[~part["accepted"].fillna(False).astype(bool)]
        if not good.empty:ax.scatter(good["date_start"],good["ndvi_p50"],color="#19865c",label="Accepted",s=22)
        if not bad.empty:ax.scatter(bad["date_start"],bad["ndvi_p50"],color="#d6534d",marker="x",label="Rejected",s=28)
        if self.reconstructed is not None:
            r=self.reconstructed[self.reconstructed['parcel_id'].astype(str).eq(parcel)].sort_values('date')
            if not r.empty:
                r = r.copy();r['date'] = pd.to_datetime(r['date'], errors='coerce');r = r.dropna(subset=['date'])
            if not r.empty:ax.plot(r['date'],r['ndvi_reconstructed_daily'],color='#2166ac',lw=2,label='Reconstructed daily NDVI');ax.legend(loc='best')
        ax.set_ylabel("NDVI P50");ax.set_xlabel("Acquisition date");ax.grid(alpha=.2)
        if not good.empty or not bad.empty:ax.legend(loc="best")
        self.figure.autofmt_xdate();self.figure.tight_layout();self.canvas.draw_idle()
        self.table.setRowCount(len(part))
        for row,(_,r) in enumerate(part.iterrows()):
            d=r["date_start"];date=d.strftime("%Y-%m-%d") if pd.notna(d) else "INVALID"
            values=[str(r["parcel_id"]),date,str(round(r["ndvi_p50"],4)),"Yes" if r["accepted"] else "No",r["qc_reason"]]
            for col,value in enumerate(values):self.table.setItem(row,col,QTableWidgetItem(value))
    def _save(self,data,caption,default):
        if data is None:return
        path,_=QFileDialog.getSaveFileName(self,caption,default,"CSV (*.csv)")
        if path:
            try:data.to_csv(path,index=False);self.status.setText(f"Exported · {Path(path).name}")
            except Exception as exc:QMessageBox.warning(self,"Export failed",str(exc))
    def export_csv(self):self._save(self.cleaned,"Export QC observations","NDVI_QC_annotated.csv")
    def export_summary(self):self._save(self.summary,"Export QC summary","NDVI_QC_summary.csv")

    def run_reconstruction(self):
        if self.cleaned is None:
            QMessageBox.information(self,'Reconstruction','Run quality control first.');return
        try:
            self.reconstructed,diag,failures=reconstruct_qc(self.cleaned,self.recon_method.currentText(),self.recon_lambda.value(),self.recon_window.value(),self.recon_clip.isChecked())
            self.reconstruction_diagnostics=diag.copy();self.reconstruction_failures=list(failures)
            self.recon_export.setEnabled(True)
            self.recon_status.setText(f'{self.reconstructed.parcel_id.nunique()} parcels · {len(self.reconstructed):,} daily records · {len(failures)} failures · sent to QUANT')
            self.reconstructed_ready.emit(self.reconstructed.copy())
            self.draw_plot()
            if failures:QMessageBox.warning(self,'Partial reconstruction','Some parcels failed:\n'+'\n'.join(f'{p}: {e}' for p,e in failures[:8]))
        except Exception as exc:QMessageBox.warning(self,'Reconstruction failed',str(exc))
    def export_reconstructed(self):
        if self.reconstructed is not None:
            path,_=QFileDialog.getSaveFileName(self,'Export reconstructed daily NDVI','NDVI_reconstructed_daily.csv','CSV (*.csv)')
            if path:
                try:
                    self.reconstructed.to_csv(path,index=False)
                    metadata={'method':self.recon_method.currentText(),'lambda':self.recon_lambda.value() if self.recon_method.currentText()=='Whittaker' else None,'sg_window':self.recon_window.value() if self.recon_method.currentText()=='Savitzky-Golay' else None,'constrain_ndvi_0_1':self.recon_clip.isChecked(),'qc_min_valid_pixels_percent':self.threshold.value(),'qc_min_samples':self.samples.value()}
                    import json
                    Path(path).with_suffix('.parameters.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
                    self.recon_status.setText('Exported daily NDVI and processing parameters')
                except Exception as exc:QMessageBox.warning(self,'Export failed',str(exc))
