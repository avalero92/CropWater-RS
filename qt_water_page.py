"""Beta 3.5: parcel-specific Kc catalog and comparative water explorer."""
import re
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
    QDoubleSpinBox,QFileDialog,QTableWidget,QTableWidgetItem,QMessageBox,QHeaderView,
    QDialog,QLineEdit,QFormLayout,QDialogButtonBox,QAbstractItemView,QListWidget,
    QListWidgetItem,QCheckBox,QSplitter,QGroupBox,QInputDialog,QDateEdit)
from PySide6.QtCore import Qt,QDate
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from cropwater_rs.core.water import calculate_linear_kc,calculate_etc,calculate_net_iwr
from qt_kc_library_store import KcLibrary
from qt_quant_scope import normalize_id
from qt_water_phase_core import summarize_water,PHASES

class MultiParcelDialog(QDialog):
    def __init__(self,ids,selected,parent=None):
        super().__init__(parent);self.setWindowTitle('Select parcels');self.resize(430,510)
        v=QVBoxLayout(self);self.search=QLineEdit();self.search.setPlaceholderText('Search parcel ID...');v.addWidget(self.search)
        self.list=QListWidget();self.list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for p in ids:self.list.addItem(p)
        for i in range(self.list.count()):self.list.item(i).setSelected(self.list.item(i).text() in selected)
        v.addWidget(self.list);self.count=QLabel();v.addWidget(self.count)
        buttons=QHBoxLayout()
        for label,method in [('Select filtered',True),('Clear filtered',False)]:
            b=QPushButton(label);b.clicked.connect(lambda _,m=method:self.select_visible(m));buttons.addWidget(b)
        v.addLayout(buttons)
        actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.accept);actions.rejected.connect(self.reject);v.addWidget(actions)
        self.search.textChanged.connect(self.filter);self.list.itemSelectionChanged.connect(self.update_count);self.update_count()
    def filter(self,term):
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(term.casefold() not in item.text().casefold())
        self.update_count()
    def select_visible(self,on):
        for i in range(self.list.count()):
            item=self.list.item(i)
            if not item.isHidden():item.setSelected(on)
        self.update_count()
    def update_count(self):self.count.setText(f'{len(self.list.selectedItems())} selected / {self.list.count()} total')
    def selected_ids(self):return [i.text() for i in self.list.selectedItems()]

class FormulationDialog(QDialog):
    def __init__(self,entry=None,parent=None):
        super().__init__(parent);self.setWindowTitle('Kc–NDVI formulation');v=QVBoxLayout(self);f=QFormLayout()
        self.name=QLineEdit((entry or {}).get('label',''));f.addRow('Name',self.name)
        self.crop=QLineEdit(', '.join((entry or {}).get('crops',[])));self.crop.setPlaceholderText('e.g. WHEAT, BARLEY');f.addRow('Crops (comma separated)',self.crop)
        self.a=QDoubleSpinBox();self.b=QDoubleSpinBox()
        for spin,key in [(self.a,'a'),(self.b,'b')]:spin.setRange(-1000,1000);spin.setDecimals(7);spin.setValue(float((entry or {}).get(key,0)))
        f.addRow('a (Kc = a·NDVI + b)',self.a);f.addRow('b',self.b)
        self.reference=QLineEdit((entry or {}).get('reference',''));f.addRow('Reference',self.reference)
        self.default=QCheckBox('Use as default for listed crops');self.default.setChecked(bool((entry or {}).get('is_default',False)));f.addRow('',self.default)
        self.notes=QLineEdit((entry or {}).get('scope',''));f.addRow('Notes / calibration scope',self.notes)
        v.addLayout(f);actions=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.accept);actions.rejected.connect(self.reject);v.addWidget(actions)
    def entry(self):return {'label':self.name.text().strip(),'crops':[c.strip().upper() for c in self.crop.text().split(',') if c.strip()], 'a':self.a.value(),'b':self.b.value(),'reference':self.reference.text().strip(),'scope':self.notes.text().strip(),'source_type':'user-defined','is_default':self.default.isChecked()}

class WaterPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.ndvi=None;self.weather=None;self.results=None;self.store=None
        self.overrides={};self.manual_crops={};self.plot_parcels=[]
        self.crop_validated={};self.relation_validated={};self.quant_page=None;self.sowing_overrides={};self.sowing_offsets={"BARLEY":30};self.phase_summary=None;self.phase_daily=None
        self.library=KcLibrary();lay=QVBoxLayout(self)
        heading=QLabel('Water Analysis · Crop Assignment / Kc Library / Results Explorer')
        heading.setStyleSheet('font-size:19px;font-weight:600;color:#173249');lay.addWidget(heading)
        lay.addWidget(QLabel('Daily observed ETo and effective precipitation required. Kc = a·NDVI + b; ETc = Kc·ETo; net IWR = max(ETc−Pe, 0).'))
        top=QHBoxLayout();self.weather_button=QPushButton('Load meteorology CSV');self.weather_button.clicked.connect(self.load_weather);top.addWidget(self.weather_button)
        self.crop_field=QComboBox();self.crop_field.addItem('No vector crop field',None);self.crop_field.currentIndexChanged.connect(self.on_crop_field_changed)
        top.addWidget(QLabel('Vector crop field'));top.addWidget(self.crop_field,1)
        self.add_formulation_button=QPushButton('+ Add Kc–NDVI');self.add_formulation_button.clicked.connect(self.quick_add_formulation);top.addWidget(self.add_formulation_button)
        self.library_button=QPushButton('Manage Library');self.library_button.clicked.connect(self.manage_library);top.addWidget(self.library_button)
        lay.addLayout(top)
        assign=QHBoxLayout();self.assignment_relation=QComboBox();self.refresh_library();assign.addWidget(QLabel('Relation'));assign.addWidget(self.assignment_relation,2)
        self.manual_crop=QLineEdit();self.manual_crop.setPlaceholderText('Crop name (optional)');assign.addWidget(self.manual_crop,1)
        self.crop_only_button=QPushButton('Assign & Validate Crop...');self.crop_only_button.clicked.connect(self.assign_crop_only);assign.addWidget(self.crop_only_button)
        self.assign_button=QPushButton('Validate Kc–NDVI...');self.assign_button.clicked.connect(self.assign_selected);assign.addWidget(self.assign_button)
        self.reset_button=QPushButton('Reset...');self.reset_button.clicked.connect(self.reset_selected);assign.addWidget(self.reset_button)
        lay.addLayout(assign)
        self.assignment_status=QLabel('Crop and Kc–NDVI assignments await validation.');lay.addWidget(self.assignment_status)
        self.assignment_table=QTableWidget();self.assignment_table.setMaximumHeight(185);lay.addWidget(self.assignment_table)
        phen=QHBoxLayout();self.analysis_scope=QComboBox();self.analysis_scope.addItems(['Full time series','QUANT phenological phases']);phen.addWidget(QLabel('Analysis scope'));phen.addWidget(self.analysis_scope)
        self.sowing_field=QComboBox();self.sowing_field.addItem('No sowing field',None);phen.addWidget(QLabel('Vector sowing date'));phen.addWidget(self.sowing_field)
        self.offset_button=QPushButton('Q1 → sowing offsets by crop...');self.offset_button.clicked.connect(self.configure_sowing_offsets);phen.addWidget(self.offset_button)
        self.sowing_button=QPushButton('Set sowing dates...');self.sowing_button.clicked.connect(self.assign_sowing);phen.addWidget(self.sowing_button)
        self.phase_export=QPushButton('Export phase summary CSV');self.phase_export.setEnabled(False);self.phase_export.clicked.connect(self.export_phase_summary);phen.addWidget(self.phase_export)
        lay.addLayout(phen)
        self.phase_status=QLabel('Full time series requires no QUANT transitions.');lay.addWidget(self.phase_status)
        self.coverage_button=QPushButton('Inspect parcel coverage / phase diagnostics...');self.coverage_button.clicked.connect(self.show_coverage_diagnostics);lay.addWidget(self.coverage_button)
        self.analysis_scope.currentIndexChanged.connect(self.invalidate_results)
        actions=QHBoxLayout();self.run=QPushButton('Calculate water requirements');self.run.clicked.connect(self.calculate);actions.addWidget(self.run)
        self.export_button=QPushButton('Export daily water CSV');self.export_button.setEnabled(False);self.export_button.clicked.connect(self.export);actions.addWidget(self.export_button)
        lay.addLayout(actions)
        explorer=QHBoxLayout();self.metric=QComboBox()
        for label,key in [('Kc','kc'),('ETc','etc_mm'),('Net IWR','iwr_net_mm')]:self.metric.addItem(label,key)
        self.metric.currentIndexChanged.connect(self.plot_results);explorer.addWidget(QLabel('Plot'));explorer.addWidget(self.metric)
        self.mode=QComboBox();self.mode.addItems(['Daily','Cumulative']);self.mode.currentIndexChanged.connect(self.plot_results);explorer.addWidget(self.mode)
        self.select_plot=QPushButton('Select comparison parcels...');self.select_plot.clicked.connect(self.select_plot_parcels);explorer.addWidget(self.select_plot)
        self.plot_count=QLabel('No results');explorer.addWidget(self.plot_count);explorer.addStretch();lay.addLayout(explorer)
        self.status=QLabel('Waiting for reconstructed NDVI and meteorology.');lay.addWidget(self.status)
        self.figure=Figure(figsize=(11,5),constrained_layout=False);self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(300);lay.addWidget(self.canvas,4)
        science=QHBoxLayout()
        self.export_figure_button=QPushButton('Export figure (PNG / SVG / PDF)...')
        self.export_figure_button.clicked.connect(self.export_scientific_figure)
        science.addWidget(self.export_figure_button)
        self.export_science_button=QPushButton('Export scientific results package...')
        self.export_science_button.clicked.connect(self.export_scientific_package)
        science.addWidget(self.export_science_button)
        self.crop_summary_button=QPushButton('Inspect crop / phase statistics...')
        self.crop_summary_button.clicked.connect(self.inspect_crop_summary)
        science.addWidget(self.crop_summary_button)
        lay.addLayout(science)
        self.table=QTableWidget();lay.addWidget(self.table,2)
    def set_parcel_store(self,store):
        self.store=store;store.changed.connect(self.refresh_vector_fields);self.refresh_vector_fields()
    def refresh_vector_fields(self):
        old_sowing=self.sowing_field.currentData();self.sowing_field.clear();self.sowing_field.addItem('No sowing field',None)
        old=self.crop_field.currentData();self.crop_field.blockSignals(True);self.crop_field.clear();self.crop_field.addItem('No vector crop field',None)
        if self.store is not None and self.store.parcels is not None:
            for col in self.store.parcels.columns:
                if col!='geometry':self.crop_field.addItem(str(col),col);self.sowing_field.addItem(str(col),col)
        si=self.sowing_field.findData(old_sowing)
        if si<0:
            si=next((i for i in range(self.sowing_field.count()) if str(self.sowing_field.itemData(i)).casefold() in ('sowing_date','sowing','planting_date','fecha_siembra')),0)
        self.sowing_field.setCurrentIndex(max(si,0))
        idx=self.crop_field.findData(old)
        if idx<0:
            for i in range(self.crop_field.count()):
                if str(self.crop_field.itemData(i)).casefold()=='crop':idx=i;break
        if idx<0 and self.store is not None and self.store.parcels is not None:
            for candidate in ('crop_source','CROPS'):
                for i in range(self.crop_field.count()):
                    if str(self.crop_field.itemData(i)).casefold()==candidate.casefold():idx=i;break
                if idx>=0:break
        self.crop_field.setCurrentIndex(max(0,idx));self.crop_field.blockSignals(False);self.on_crop_field_changed()
    def refresh_library(self):
        previous=self.assignment_relation.currentData() if self.assignment_relation.count() else None
        self.assignment_relation.clear()
        for key,e in self.library.all().items():self.assignment_relation.addItem(e['label']+(' [user]' if key in self.library.custom else ' [built-in]'),key)
        i=self.assignment_relation.findData(previous)
        if i>=0:self.assignment_relation.setCurrentIndex(i)
    def quick_add_formulation(self):
        """One-step create, persist, and optionally assign to parcels."""
        d=FormulationDialog(parent=self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        entry=d.entry()
        if not entry['label']:
            QMessageBox.warning(self,'Missing name','Enter a formulation name.');return
        import uuid
        key='user_'+uuid.uuid4().hex[:16]
        try:self.library.upsert(key,entry)
        except Exception as exc:
            QMessageBox.warning(self,'Library',str(exc));return
        self.refresh_library();self.assignment_relation.setCurrentIndex(self.assignment_relation.findData(key))
        self.relation_validated.clear();self.invalidate_results();self.update_assignment_table()
        if self.ndvi is not None and QMessageBox.question(self,'Assign formulation','Formulation saved. Assign it to selected parcels now?')==QMessageBox.StandardButton.Yes:
            chosen=self.select_ids([])
            if chosen:
                for parcel in chosen:self.overrides[parcel]=key
                self.update_assignment_table()
                self.status.setText(f'Saved formulation and assigned to {len(chosen)} parcels')
        else:self.status.setText('New Kc–NDVI formulation saved in your library')

    def on_crop_field_changed(self,*_):
        self.crop_validated.clear();self.relation_validated.clear()
        self.invalidate_results();self.update_assignment_table()

    def assign_crop_only(self):
        """Validate vector crops or apply one manual crop to selected parcels."""
        if not self.ids():
            QMessageBox.information(self,'No parcels','Run NDVI reconstruction first.');return
        chosen=self.select_ids(self.ids())
        if not chosen:return
        manual=self.manual_crop.text().strip();vector=self.vector_crops()
        missing=[p for p in chosen if not manual and not self.manual_crops.get(p,vector.get(normalize_id(p),'')).strip()]
        if missing:
            QMessageBox.warning(self,'Missing crop',f'{len(missing)} selected parcels have no crop. Enter a manual crop or choose a vector crop field.');return
        for parcel in chosen:
            if manual:
                if self.manual_crops.get(parcel)!=manual:
                    self.overrides.pop(parcel,None)
                self.manual_crops[parcel]=manual
            crop=self.manual_crops.get(parcel,vector.get(normalize_id(parcel),''))
            self.crop_validated[parcel]=crop
            self.relation_validated.pop(parcel,None)
        self.invalidate_results();self.update_assignment_table()
        self.status.setText(f'Crop validated for {len(chosen)} parcels; review proposed Kc–NDVI formulations next.')

    def manage_library(self):
        dlg=QDialog(self);dlg.setWindowTitle('Persistent Kc–NDVI Library');dlg.resize(700,450);v=QVBoxLayout(dlg)
        items=QListWidget();v.addWidget(items)
        def refresh():
            items.clear()
            for key,e in self.library.all().items():
                it=QListWidgetItem(f"{e['label']}   |   Kc = {e['a']} × NDVI + {e['b']}   |   {'User' if key in self.library.custom else 'Built-in'}")
                it.setData(Qt.ItemDataRole.UserRole,key);items.addItem(it)
        def chosen():return items.currentItem().data(Qt.ItemDataRole.UserRole) if items.currentItem() else None
        def add_edit(edit=False):
            key=chosen() if edit else None
            if edit and key not in self.library.custom:QMessageBox.information(dlg,'Read-only','Built-in formulations cannot be edited.');return
            d=FormulationDialog(self.library.custom[key] if edit else None,dlg)
            if d.exec()!=QDialog.DialogCode.Accepted:return
            entry=d.entry()
            if not entry['label']:QMessageBox.warning(dlg,'Missing name','Enter a formulation name.');return
            if not edit:
                import uuid
                key='user_'+uuid.uuid4().hex[:16]
            self.library.upsert(key,entry);refresh();self.refresh_library();self.relation_validated.clear();self.invalidate_results();self.update_assignment_table()
        def remove():
            key=chosen()
            if key not in self.library.custom:QMessageBox.information(dlg,'Read-only','Select a user-defined formulation.');return
            if QMessageBox.question(dlg,'Delete formulation','Delete this formulation from your persistent library?')==QMessageBox.StandardButton.Yes:
                self.library.delete(key);refresh();self.refresh_library();self.relation_validated.clear();self.invalidate_results();self.update_assignment_table()
        row=QHBoxLayout()
        for title,fn in [('Add',lambda:add_edit()),('Edit',lambda:add_edit(True)),('Delete',remove)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        def import_library():
            p,_=QFileDialog.getOpenFileName(dlg,'Import library','','JSON (*.json)')
            if p:
                try:self.library.import_json(p);refresh();self.refresh_library();self.relation_validated.clear();self.invalidate_results();self.update_assignment_table()
                except Exception as e:QMessageBox.warning(dlg,'Import failed',str(e))
        def export_library():
            p,_=QFileDialog.getSaveFileName(dlg,'Export library','kc_ndvi_library.json','JSON (*.json)')
            if p:self.library.export_json(p)
        for title,fn in [('Import JSON',import_library),('Export JSON',export_library)]:
            b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        v.addLayout(row);close=QPushButton('Close');close.clicked.connect(dlg.accept);v.addWidget(close);refresh();dlg.exec()
    def ids(self):return sorted(self.ndvi['parcel_id'].unique().tolist()) if self.ndvi is not None else []
    def select_ids(self,initial):
        d=MultiParcelDialog(self.ids(),initial,self)
        return d.selected_ids() if d.exec()==QDialog.DialogCode.Accepted else None
    def assign_selected(self):
        """Validate automatic proposals or selected library relation, independently of crop."""
        if not self.ids():
            QMessageBox.information(self,'No parcels','Run NDVI reconstruction first.');return
        chosen=self.select_ids(self.ids())
        if not chosen:return
        unvalidated=[p for p in chosen if p not in self.crop_validated]
        if unvalidated:
            QMessageBox.warning(self,'Crop not validated',f'Validate crops first ({len(unvalidated)} parcels pending).');return
        options=['Use automatic crop default','Use selected library formulation']
        choice,ok=QInputDialog.getItem(self,'Validate Kc–NDVI','Formulation source for selected parcels:',options,0,False)
        if not ok:return
        explicit=choice==options[1];key=self.assignment_relation.currentData()
        if explicit and key not in self.library.all():
            QMessageBox.warning(self,'Missing formulation','Choose a formulation from the library.');return
        vector=self.vector_crops();proposals={}
        try:
            for parcel in chosen:
                if explicit:proposals[parcel]=key
                else:
                    crop=self.crop_validated[parcel]
                    # Ignore previous override when requesting the crop default.
                    previous=self.overrides.pop(parcel,None)
                    try:proposals[parcel]=self.resolve_relation(parcel,vector)[0]
                    finally:
                        if previous is not None:self.overrides[parcel]=previous
        except ValueError as exc:
            QMessageBox.warning(self,'Formulation unavailable',str(exc));return
        catalog=self.library.all();summary='\n'.join(f'{p}: {catalog[k]["label"]}' for p,k in list(proposals.items())[:12])
        if len(proposals)>12:summary+=f'\n... and {len(proposals)-12} more'
        if QMessageBox.question(self,'Confirm Kc–NDVI',f'Validate these {len(proposals)} assignments?\n\n{summary}')!=QMessageBox.StandardButton.Yes:return
        for parcel,relation in proposals.items():
            if explicit:self.overrides[parcel]=relation
            else:self.overrides.pop(parcel,None)
            self.relation_validated[parcel]=relation
        self.invalidate_results();self.update_assignment_table()
        self.status.setText(f'Kc–NDVI validated for {len(chosen)} parcels.')

    def reset_selected(self):
        if not self.ids():return
        chosen=self.select_ids(self.ids())
        if not chosen:return
        modes=['Crop + Kc–NDVI','Only crop','Only Kc–NDVI']
        mode,ok=QInputDialog.getItem(self,'Reset assignments','Reset selected parcels:',modes,0,False)
        if not ok:return
        if QMessageBox.question(self,'Confirm reset',f'Reset {mode} for {len(chosen)} parcels? The formulation library and NDVI series will be preserved.')!=QMessageBox.StandardButton.Yes:return
        for parcel in chosen:
            if mode!='Only Kc–NDVI':
                self.manual_crops.pop(parcel,None);self.crop_validated.pop(parcel,None)
            if mode!='Only crop':self.overrides.pop(parcel,None)
            # A crop reset invalidates the dependent formulation validation too.
            self.relation_validated.pop(parcel,None)
        self.invalidate_results();self.update_assignment_table()
        self.status.setText(f'Reset {mode} for {len(chosen)} parcels.')

    def update_assignment_table(self):
        if not hasattr(self,'assignment_table'):return
        ids=self.ids();vector=self.vector_crops()
        self.assignment_table.setColumnCount(4);self.assignment_table.setHorizontalHeaderLabels(['Parcel','Crop','Crop status','Kc–NDVI status'])
        self.assignment_table.setRowCount(len(ids))
        for i,parcel in enumerate(ids):
            crop=self.manual_crops.get(parcel,vector.get(normalize_id(parcel),''))
            values=[parcel,crop or 'Unassigned','Validated' if self.crop_validated.get(parcel)==crop and crop else 'Pending','Validated' if parcel in self.relation_validated and parcel in self.crop_validated else 'Pending']
            for j,value in enumerate(values):self.assignment_table.setItem(i,j,QTableWidgetItem(str(value)))
        self.assignment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.assignment_status.setText(f'{sum(p in self.crop_validated for p in ids)}/{len(ids)} crops validated · {sum(p in self.relation_validated for p in ids)}/{len(ids)} Kc–NDVI formulations validated')

    def vector_crops(self):
        if self.store is None or self.store.parcels is None or self.crop_field.currentData() is None:return {}
        gdf=self.store.parcels;ids=[c for c in gdf.columns if c.lower() in ('parcel_id','id','id_parcela','parcela','name')]
        col=next((c for c in ids if c.lower()=='parcel_id'),ids[0] if ids else None);field=self.crop_field.currentData();out={}
        for pos,(_,row) in enumerate(gdf.iterrows(),1):
            value=row[field]
            if pd.notna(value) and str(value).strip() and str(value).strip().upper()!='OTHER':out[normalize_id(row[col] if col else pos)]=str(value).strip()
        return out
    @staticmethod
    def crop_match(crop,crops):
        def norm(s):return re.sub(r'[^A-Z0-9]','',str(s).upper())
        aliases={'TRIGO':'WHEAT','CEBADA':'BARLEY','MAIZ':'MAIZE','MAIZE':'MAIZE','SOJA':'SOYBEAN','ARROZ':'RICE','ALFALFA':'ALFALFA'}
        v=norm(crop);v=aliases.get(v,v)
        return any(v==norm(c) for c in crops if norm(c)!='ALL')
    def resolve_relation(self,parcel,vector):
        catalog=self.library.all()
        if parcel in self.overrides:
            key=self.overrides[parcel]
            if key not in catalog:raise ValueError(f'Parcel {parcel}: assigned formulation {key} was deleted')
            return key,self.manual_crops.get(parcel,vector.get(normalize_id(parcel),'')),'manual override'
        crop=self.manual_crops.get(parcel,vector.get(normalize_id(parcel),''))
        if not crop:raise ValueError(f'Parcel {parcel}: no crop or Kc formulation assigned; use vector crop field or manual assignment')
        matches=[key for key,e in catalog.items() if self.crop_match(crop,e.get('crops',[]))]
        if not matches:raise ValueError(f'Parcel {parcel}: no specific Kc–NDVI formulation for crop {crop!r}; assign one explicitly')
        defaults=[key for key in matches if catalog[key].get('is_default')]
        if len(defaults)>1:raise ValueError(f'Parcel {parcel}: multiple default formulations for {crop!r}; choose one explicitly')
        if defaults:key=defaults[0]
        else:
            builtins=[key for key in matches if key not in self.library.custom]
            if len(builtins)==1:key=builtins[0]
            elif len(matches)==1:key=matches[0]
            else:raise ValueError(f'Parcel {parcel}: ambiguous Kc–NDVI formulations for {crop!r}; choose a default or override')
        return key,crop,('manual crop' if parcel in self.manual_crops else 'vector crop')
    def invalidate_results(self,*_):
        self.phase_summary=None;self.phase_daily=None
        if hasattr(self,'phase_export'):self.phase_export.setEnabled(False)
        self.results=None
        if hasattr(self,'export_button'):self.export_button.setEnabled(False)
    def set_data(self,df):
        needed={'parcel_id','date','ndvi_reconstructed_daily'}
        if not needed.issubset(df.columns):raise ValueError('Missing reconstructed daily NDVI columns')
        x=df[['parcel_id','date','ndvi_reconstructed_daily']].copy();x['date']=pd.to_datetime(x['date'],errors='coerce').dt.normalize()
        x['ndvi_reconstructed_daily']=pd.to_numeric(x['ndvi_reconstructed_daily'],errors='coerce')
        x=x.dropna(subset=['parcel_id','date','ndvi_reconstructed_daily']);x['parcel_id']=x['parcel_id'].astype(str)
        if x.duplicated(['parcel_id','date']).any():raise ValueError('Duplicate parcel/date in reconstructed NDVI')
        self.ndvi=x;self.plot_parcels=[];self.crop_validated.clear();self.relation_validated.clear();self.invalidate_results();self.update_assignment_table();self.status.setText(f'{len(x):,} reconstructed NDVI rows ready')
    def invalidate_data(self):
        self.ndvi=None;self.crop_validated.clear();self.relation_validated.clear();self.invalidate_results();self.update_assignment_table();self.status.setText('Reconstruction changed; run it again.')
    def load_weather(self):
        path,_=QFileDialog.getOpenFileName(self,'Daily meteorological data','','CSV (*.csv)')
        if path:
            try:self.set_weather(pd.read_csv(path))
            except Exception as e:QMessageBox.warning(self,'Invalid meteorology CSV',str(e))
    def set_weather(self,df):
        required={'date','eto_mm','pe_mm'}
        if not required.issubset(df.columns):raise ValueError('CSV must contain date, eto_mm, pe_mm (daily mm)')
        cols=['date','eto_mm','pe_mm']+(['parcel_id'] if 'parcel_id' in df.columns else [])
        w=df[cols].copy();w['date']=pd.to_datetime(w['date'],errors='coerce').dt.normalize()
        for c in ('eto_mm','pe_mm'):w[c]=pd.to_numeric(w[c],errors='coerce')
        if w[['date','eto_mm','pe_mm']].isna().any().any():raise ValueError('Invalid meteorological values')
        if not np.isfinite(w[['eto_mm','pe_mm']].to_numpy()).all():raise ValueError('Non-finite meteorology')
        if (w[['eto_mm','pe_mm']]<0).any().any():raise ValueError('Negative ETo or Pe not permitted')
        keys=['date']
        if 'parcel_id' in w.columns:
            if w['parcel_id'].isna().any():raise ValueError('Missing parcel_id in meteorology')
            w['parcel_id']=w['parcel_id'].astype(str);keys=['parcel_id','date']
        if w.duplicated(keys).any():raise ValueError('Duplicate meteorological keys')
        self.weather=w;self.invalidate_results();self.status.setText(f'{len(w):,} meteorological rows loaded')
    def calculate(self):
        try:
            if self.ndvi is None or self.weather is None:raise ValueError('Load reconstructed NDVI and meteorology first')
            pending=[p for p in self.ids() if p not in self.crop_validated or p not in self.relation_validated]
            if pending:raise ValueError(f'{len(pending)} parcels require crop and Kc–NDVI validation before calculation. Use the two validation buttons.')
            keys=['date']+(['parcel_id'] if 'parcel_id' in self.weather.columns else [])
            merged=self.ndvi.merge(self.weather,on=keys,how='left',validate='many_to_one',indicator=True)
            if (merged['_merge']!='both').any():raise ValueError(f'Missing meteorology for {(merged["_merge"]!="both").sum()} parcel-days')
            merged=merged.drop(columns='_merge').sort_values(['parcel_id','date']).reset_index(drop=True)
            vector=self.vector_crops();catalog=self.library.all();frames=[]
            for parcel,group in merged.groupby('parcel_id',sort=True):
                key,crop,source=self.resolve_relation(parcel,vector)
                if crop!=self.crop_validated.get(parcel) or key!=self.relation_validated.get(parcel):raise ValueError(f'Parcel {parcel}: assignment changed after validation; validate again')
                entry=catalog[key];g=group.copy()
                g['kc']=calculate_linear_kc(g['ndvi_reconstructed_daily'],float(entry['a']),float(entry['b']))
                g['etc_mm']=calculate_etc(g['kc'],g['eto_mm']);g['iwr_net_mm']=calculate_net_iwr(g['etc_mm'],g['pe_mm'])
                g['etc_cumulative_mm']=g['etc_mm'].cumsum();g['iwr_cumulative_mm']=g['iwr_net_mm'].cumsum()
                g['crop']=crop;g['kc_relation']=key;g['kc_label']=entry['label'];g['kc_a']=float(entry['a']);g['kc_b']=float(entry['b'])
                g['kc_source']=source;g['kc_reference']=entry.get('reference','');frames.append(g)
            self.results=pd.concat(frames,ignore_index=True);self.export_button.setEnabled(True)
            mode='quant' if self.analysis_scope.currentIndex()==1 else 'full'
            if mode=='quant' and (self.quant_page is None or self.quant_page.results is None):raise ValueError('Run QUANT first to calculate phase-based water statistics.')
            sowing=self.sowing_dates() if mode=='quant' else None
            summary_ph,annotated,issues=summarize_water(self.results,mode, self.quant_page.results if mode=='quant' else None,sowing)
            if mode=='quant' and not summary_ph.empty:
                for col in ('sowing_date','sowing_source','q1_offset_days'):
                    if col in summary_ph:continue
                    summary_ph[col]=summary_ph['parcel_id'].map(lambda pid: self.sowing_provenance.get(str(pid),{}).get(col))
                for col in ('sowing_date','sowing_source','q1_offset_days'):
                    annotated[col]=annotated['parcel_id'].map(lambda pid: self.sowing_provenance.get(str(pid),{}).get(col))
            if issues:
                self.phase_status.setText(f'{len(issues)} parcel/phase issues: '+ ' | '.join(issues[:3]))
            else:self.phase_status.setText(f'{len(summary_ph)} phase/total records ready · {mode} analysis')
            if summary_ph.empty:raise ValueError('No valid phase statistics. '+ '; '.join(issues[:4]))
            self.phase_summary=summary_ph;self.phase_daily=annotated;self.phase_export.setEnabled(True)
            summary=self.results.groupby('parcel_id',sort=True).agg(crop=('crop','first'),relation=('kc_label','first'),days=('date','size'),etc_total_mm=('etc_mm','sum'),iwr_total_mm=('iwr_net_mm','sum')).reset_index()
            cols=['Parcel','Crop','Kc relation','Days','ETc total (mm)','Net IWR total (mm)'];self.table.setRowCount(len(summary));self.table.setColumnCount(len(cols));self.table.setHorizontalHeaderLabels(cols)
            for i,row in summary.iterrows():
                vals=[row['parcel_id'],row['crop'],row['relation'],str(int(row['days'])),f'{row["etc_total_mm"]:.2f}',f'{row["iwr_total_mm"]:.2f}']
                for j,val in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(str(val)))
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            if mode=='quant':
                # Phase totals and means in the main table; full-series totals remain available via daily CSV.
                display=self.phase_summary
                cols=['Parcel','Phase','Days','Mean Kc','Mean ETc (mm/day)','Total ETc (mm)','Mean IWR (mm/day)','Total IWR (mm)']
                self.table.setRowCount(len(display));self.table.setColumnCount(len(cols));self.table.setHorizontalHeaderLabels(cols)
                for i,(_,r) in enumerate(display.iterrows()):
                    vals=[r['parcel_id'],r['phase'],int(r['days']),f"{r['kc_mean']:.3f}",f"{r['etc_mm_mean']:.2f}",f"{r['etc_mm_total']:.2f}",f"{r['iwr_net_mm_mean']:.2f}",f"{r['iwr_net_mm_total']:.2f}"]
                    for j,val in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(str(val)))
            # Select every parcel with a valid phenological cycle by default.
            # The comparison dialog can still narrow this selection.
            if mode=='quant':
                self.plot_parcels=sorted(self.phase_summary['parcel_id'].astype(str).unique().tolist())
            else:
                self.plot_parcels=[str(self.results['parcel_id'].iloc[0])]
            self.plot_results()
            self.status.setText(f'{len(self.results):,} daily records · {len(summary)} parcels · parcel-specific Kc relations')
        except Exception as e:QMessageBox.warning(self,'Water analysis',str(e))
    def select_plot_parcels(self):
        if self.results is None or self.results.empty:
            QMessageBox.information(self,'No results','Calculate water requirements first.');return
        # Use the parcels in the calculated dataset, not the potentially stale
        # reconstruction list. Keep multi-selection across variable changes.
        available=sorted((self.phase_summary if self.analysis_scope.currentIndex()==1 and self.phase_summary is not None else self.results)['parcel_id'].astype(str).unique().tolist())
        d=MultiParcelDialog(available,self.plot_parcels,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        selected=d.selected_ids()
        if not selected:
            QMessageBox.information(self,'Comparison','Select at least one parcel.');return
        self.plot_parcels=selected
        self.plot_results()

    def plot_results(self,*_):
        if self.results is None:return
        self.figure.clear()
        ax=self.figure.add_subplot(111)
        key=self.metric.currentData()
        cumulative=self.mode.currentIndex()==1 and key!='kc'
        quant_mode=self.analysis_scope.currentIndex()==1
        source=self.phase_daily if quant_mode else self.results
        if source is None or source.empty:
            self.plot_count.setText('No data for selected scope')
            self.canvas.draw_idle();return
        palette=['#b6d5e8','#8cbacb','#83b9a1','#e6c69b']
        selected=list(dict.fromkeys(str(p) for p in self.plot_parcels))
        available=set(source['parcel_id'].astype(str))
        missing=[p for p in selected if p not in available]
        plotted=[];limits=[];handles=[]
        for parcel in selected:
            if parcel not in available:continue
            sub=source[source['parcel_id'].astype(str)==parcel].copy()
            if quant_mode:
                if 'growth_phase' not in sub.columns:continue
                sub=sub[sub['growth_phase'].isin(PHASES)].copy()
            if sub.empty:continue
            sub=sub.sort_values('date')
            values=sub[key].cumsum() if cumulative else sub[key]
            line,=ax.plot(sub['date'],values,label=f'Parcel {parcel}',linewidth=2.0)
            handles.append(line);plotted.append(parcel)
            limits.append((sub['date'].min(),sub['date'].max()))
        if quant_mode and len(plotted)==1:
            sub=source[source['parcel_id'].astype(str)==plotted[0]]
            for i,name in enumerate(PHASES):
                part=sub[sub['growth_phase']==name]
                if not part.empty:
                    ax.axvspan(part['date'].min(),part['date'].max()+pd.Timedelta(days=1),
                              alpha=.19,color=palette[i],zorder=0)
                    handles.append(Patch(facecolor=palette[i],alpha=.45,label=name,edgecolor='none'))
        if quant_mode and limits:
            ax.set_xlim(min(a for a,b in limits),max(b for a,b in limits)+pd.Timedelta(days=1))
        ax.set_ylabel('Kc (dimensionless)' if key=='kc' else ('Cumulative (mm)' if cumulative else 'mm/day'),fontsize=11)
        ax.set_xlabel('Date',fontsize=11,labelpad=8)
        ax.grid(alpha=.18,linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines['top'].set_visible(False);ax.spines['right'].set_visible(False)
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4,maxticks=9))
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
        ax.tick_params(axis='both',labelsize=10)
        # Dedicated legend strip outside the axes: fixed position and no overlap.
        # Its anchor is identical for Kc, ETc, IWR, daily and cumulative.
        if handles:
            ncol=min(5,max(1,len(handles)))
            self.figure.legend(handles=handles,loc='lower center',
                               bbox_to_anchor=(.5,.005),ncol=ncol,
                               frameon=False,fontsize=9.5,handlelength=2.2,
                               columnspacing=1.5)
        self.figure.subplots_adjust(left=.075,right=.985,top=.94,bottom=.29)
        self.canvas.draw_idle()
        label=f'{len(plotted)} parcels compared'
        if missing:label+=f' · {len(missing)} without phase data'
        self.plot_count.setText(label)
    def set_quant_page(self,page):
        self.quant_page=page
    def configure_sowing_offsets(self):
        """Batch-configure one Q1-to-sowing offset per crop; no fixed agronomic assumption."""
        if not self.ids():
            QMessageBox.information(self,'No parcels','Run NDVI reconstruction first.');return
        crops=sorted({str(self.manual_crops.get(pid,self.vector_crops().get(normalize_id(pid),''))).strip().upper() for pid in self.ids()})
        crops=[c for c in crops if c]
        if not crops:
            QMessageBox.warning(self,'Missing crops','Assign crops first.');return
        dlg=QDialog(self);dlg.setWindowTitle('Estimate sowing from QUANT Q1 · by crop');dlg.resize(530,350)
        v=QVBoxLayout(dlg);v.addWidget(QLabel('For each crop, enter days BEFORE Q1. Blank = no Q1 estimation.\nManual sowing dates override vector dates; vector dates override Q1 offsets.'))
        form=QFormLayout();editors={}
        for crop in crops:
            edit=QLineEdit(str(self.sowing_offsets[crop]) if crop in self.sowing_offsets else '')
            edit.setPlaceholderText('Days before Q1 (blank = disabled)')
            form.addRow(crop,edit);editors[crop]=edit
        v.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);v.addWidget(buttons)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        try:
            offsets=dict(self.sowing_offsets)
            for crop,edit in editors.items():
                value=edit.text().strip()
                if not value:offsets.pop(crop,None);continue
                if not re.fullmatch(r'\d+',value) or not 1<=int(value)<=365:
                    raise ValueError(f'{crop}: days must be an integer from 1 to 365')
                offsets[crop]=int(value)
            self.sowing_offsets=offsets;self.invalidate_results()
            self.phase_status.setText(f'Q1 sowing offsets configured for {len(offsets)} crop(s). Barley default: 30 days (editable).')
        except ValueError as exc:QMessageBox.warning(self,'Invalid Q1 offset',str(exc))

    def sowing_dates(self):
        """Resolve sowing dates with explicit priority: manual > vector > Q1 offset."""
        dates={};provenance={};field=self.sowing_field.currentData()
        if field and self.store is not None and self.store.parcels is not None:
            gdf=self.store.parcels
            idcols=[c for c in gdf.columns if str(c).lower() in ('parcel_id','id','id_parcela','parcela','name')]
            col=next((c for c in idcols if str(c).lower()=='parcel_id'),idcols[0] if idcols else None)
            for pos,(_,row) in enumerate(gdf.iterrows(),1):
                value=pd.to_datetime(row[field],errors='coerce')
                if pd.notna(value):
                    pid=normalize_id(row[col] if col else pos);dates[pid]=value.normalize()
                    provenance[pid]={'sowing_date':value.normalize(),'sowing_source':'vector','q1_offset_days':None}
        qmap={}
        if self.quant_page is not None and self.quant_page.results is not None:
            qmap={normalize_id(r['parcel_id']):r for _,r in self.quant_page.results.iterrows()}
        crops=self.vector_crops()
        for pid in self.ids():
            norm=normalize_id(pid)
            if norm not in dates:
                crop=str(self.manual_crops.get(pid,crops.get(norm,''))).strip().upper()
                offset=self.sowing_offsets.get(crop);q=qmap.get(norm)
                if offset is not None and q is not None and str(q.get('status'))=='Complete':
                    q1=pd.to_datetime(q.get('Q1_date'),errors='coerce')
                    if pd.notna(q1):
                        dt=q1.normalize()-pd.Timedelta(days=offset);dates[norm]=dt
                        provenance[norm]={'sowing_date':dt,'sowing_source':'Q1_offset','q1_offset_days':offset}
            if pid in self.sowing_overrides or norm in self.sowing_overrides:
                dt=pd.Timestamp(self.sowing_overrides.get(pid,self.sowing_overrides.get(norm))).normalize()
                dates[norm]=dt;provenance[norm]={'sowing_date':dt,'sowing_source':'manual','q1_offset_days':None}
        self.sowing_provenance={pid:provenance.get(normalize_id(pid),{'sowing_date':None,'sowing_source':'missing','q1_offset_days':None}) for pid in self.ids()}
        return {pid:dates.get(normalize_id(pid)) for pid in self.ids()}

    def assign_sowing(self):
        selected=self.select_ids(list(self.sowing_overrides))
        if not selected:return
        value,ok=QInputDialog.getText(self,'Sowing date','Date (YYYY-MM-DD); manual value overrides vector date:')
        if not ok:return
        try:
            date=pd.Timestamp(value.strip())
            if pd.isna(date) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value.strip()):raise ValueError('Use YYYY-MM-DD')
            for pid in selected:self.sowing_overrides[pid]=date.normalize()
            self.invalidate_results();self.phase_status.setText(f'Manual sowing date assigned to {len(selected)} parcels')
        except Exception as e:QMessageBox.warning(self,'Sowing date',str(e))
    def show_coverage_diagnostics(self):
        """Inspect source dates without changing data or silently truncating cycles."""
        if self.ndvi is None:
            QMessageBox.information(self,'Coverage','Load reconstructed NDVI first.');return
        sowing=self.sowing_dates()
        qmap={}
        if self.quant_page is not None and self.quant_page.results is not None:
            for _,r in self.quant_page.results.iterrows():qmap[normalize_id(r['parcel_id'])]=r
        rows=[]
        for pid,g in self.ndvi.groupby('parcel_id',sort=True):
            pid=str(pid);q=qmap.get(normalize_id(pid));start=sowing.get(pid)
            dates=pd.to_datetime(g['date']).dt.normalize()
            lo=dates.min();hi=dates.max()
            q1=pd.to_datetime(q.get('Q1_date'),errors='coerce') if q is not None else pd.NaT
            q4=pd.to_datetime(q.get('Q4_date'),errors='coerce') if q is not None else pd.NaT
            missing_before=max(0,(lo-pd.Timestamp(start)).days) if start is not None and pd.notna(start) else None
            missing_after=max(0,(q4-hi).days) if pd.notna(q4) else None
            missing_inside=None
            if start is not None and pd.notna(start) and pd.notna(q4) and pd.Timestamp(start)<=q4:
                expected=pd.date_range(max(pd.Timestamp(start),lo),min(q4,hi),freq='D')
                missing_inside=int((~expected.isin(dates)).sum())
            if q is None:status='Missing QUANT'
            elif str(q.get('status','')).casefold()!='complete':status='Incomplete QUANT'
            elif start is None or pd.isna(start):status='Missing sowing date'
            elif pd.isna(q1) or pd.isna(q4) or not pd.Timestamp(start)<q1<q4:status='Invalid chronology'
            elif missing_before or missing_after or missing_inside:status='Insufficient coverage'
            else:status='Ready'
            fmt=lambda x:pd.Timestamp(x).strftime('%Y-%m-%d') if x is not None and pd.notna(x) else '—'
            rows.append([pid,fmt(start),self.sowing_provenance.get(pid,{}).get('sowing_source','—'),fmt(q1),fmt(q4),fmt(lo),fmt(hi),str(missing_before) if missing_before is not None else '—',str(missing_after) if missing_after is not None else '—',str(missing_inside) if missing_inside is not None else '—',status])
        dlg=QDialog(self);dlg.setWindowTitle('QUANT / Water Analysis · Coverage diagnostics');dlg.resize(1180,440)
        layout=QVBoxLayout(dlg);layout.addWidget(QLabel('Dates are parcel-specific. Missing days before/after the available daily series are reported separately.'))
        table=QTableWidget(len(rows),11);table.setHorizontalHeaderLabels(['Parcel','Sowing','Sowing source','Q1','Q4','Daily start','Daily end','Days before','Days after','Gaps inside','Status'])
        for i,row in enumerate(rows):
            for j,val in enumerate(row):table.setItem(i,j,QTableWidgetItem(str(val)))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table);close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(dlg.reject);close.accepted.connect(dlg.accept);layout.addWidget(close);dlg.exec()
    def _scientific_summary(self):
        """Aggregate independent parcels, never pool daily observations as replicates."""
        if self.phase_summary is None or self.phase_summary.empty:
            raise ValueError('Calculate water requirements first.')
        d=self.phase_summary.copy()
        metrics=[c for c in ('days','kc_mean','ndvi_reconstructed_daily_mean',
            'eto_mm_total','pe_mm_total','etc_mm_total','iwr_net_mm_total',
            'etc_mm_mean','iwr_net_mm_mean') if c in d.columns]
        keys=['crop','analysis_mode','phase']
        agg={'parcel_id':'nunique'}
        for col in metrics:
            agg[col]=['mean','median','std','min','max']
        result=d.groupby(keys,dropna=False).agg(agg)
        result.columns=['n_parcels' if col=='parcel_id' else f'{col}_{stat}' for col,stat in result.columns]
        return result.reset_index()

    def _provenance_table(self):
        if self.results is None or self.results.empty:
            raise ValueError('Calculate water requirements first.')
        cols=['parcel_id','crop','kc_relation','kc_label','kc_a','kc_b','kc_source','kc_reference']
        present=[c for c in cols if c in self.results.columns]
        d=self.results[present].drop_duplicates('parcel_id').copy()
        d['analysis_mode']='QUANT phenological phases' if self.analysis_scope.currentIndex()==1 else 'Full time series'
        if self.phase_summary is not None and 'sowing_source' in self.phase_summary:
            ph=self.phase_summary.drop_duplicates('parcel_id')
            for col in ('sowing_date','sowing_source','q1_offset_days'):
                if col in ph:d=d.merge(ph[['parcel_id',col]],on='parcel_id',how='left',validate='one_to_one')
        if self.quant_page is not None and self.quant_page.results is not None and self.analysis_scope.currentIndex()==1:
            q=self.quant_page.results.copy()
            q['_id']=q['parcel_id'].map(normalize_id)
            for col in ('status','Q1_date','Q2_date','Q3_date','Q4_date','q1_percent','q2_percent','q3_percent','q4_percent'):
                if col in q:
                    mapping=dict(zip(q['_id'],q[col]))
                    d['quant_'+col]=d['parcel_id'].map(lambda x:mapping.get(normalize_id(x)))
        return d

    def inspect_crop_summary(self):
        try:d=self._scientific_summary()
        except Exception as e:QMessageBox.warning(self,'Scientific statistics',str(e));return
        dialog=QDialog(self);dialog.setWindowTitle('Scientific statistics · independent parcels by crop and phase');dialog.resize(1200,520)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('Mean, median, SD, min and max across parcels; n = number of parcels. No pooling of daily records.'))
        table=QTableWidget(len(d),len(d.columns));table.setHorizontalHeaderLabels(d.columns.tolist())
        for i,(_,r) in enumerate(d.iterrows()):
            for j,col in enumerate(d.columns):
                value=r[col]
                table.setItem(i,j,QTableWidgetItem(f'{value:.3f}' if isinstance(value,(float,np.floating)) and pd.notna(value) else str(value)))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(dialog.reject);layout.addWidget(close)
        dialog.exec()

    def export_scientific_figure(self):
        if self.results is None or self.results.empty:
            QMessageBox.information(self,'Export figure','Calculate water requirements first.');return
        path,fmt=QFileDialog.getSaveFileName(self,'Export scientific figure',
            'CropWater_RS_water_explorer.png','PNG (*.png);;SVG (*.svg);;PDF (*.pdf)')
        if not path:return
        ext=Path(path).suffix.lower()
        if ext not in ('.png','.svg','.pdf'):
            ext={0:'.png',1:'.svg',2:'.pdf'}.get(['PNG','SVG','PDF'].index(fmt.split(' ')[0]),'.png')
            path+=ext
        try:
            # Save the current plot without changing axes, selected parcels or calculations.
            self.figure.savefig(path,dpi=300,facecolor='white',bbox_inches='tight',pad_inches=.18)
            QMessageBox.information(self,'Figure exported',f'Figure saved:\n{path}')
        except Exception as e:QMessageBox.warning(self,'Figure export',str(e))

    def export_scientific_package(self):
        if self.results is None or self.phase_summary is None or self.phase_summary.empty:
            QMessageBox.information(self,'Scientific export','Calculate water requirements first.');return
        folder=QFileDialog.getExistingDirectory(self,'Choose output folder for scientific results')
        if not folder:return
        try:
            target=Path(folder)/('CropWater_RS_scientific_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
            target.mkdir(parents=True,exist_ok=False)
            self.phase_summary.to_csv(target/'parcel_phase_statistics.csv',index=False,date_format='%Y-%m-%d')
            self._scientific_summary().to_csv(target/'crop_phase_statistics.csv',index=False)
            self._provenance_table().to_csv(target/'parcel_provenance.csv',index=False,date_format='%Y-%m-%d')
            self.results.to_csv(target/'daily_water_full_series.csv',index=False,date_format='%Y-%m-%d')
            if self.phase_daily is not None and not self.phase_daily.empty:
                self.phase_daily.to_csv(target/'daily_water_phase_annotated.csv',index=False,date_format='%Y-%m-%d')
            self.figure.savefig(target/'water_explorer.png',dpi=300,facecolor='white',bbox_inches='tight',pad_inches=.18)
            self.figure.savefig(target/'water_explorer.svg',facecolor='white',bbox_inches='tight',pad_inches=.18)
            manifest={'software':'CropWater-RS','release':'Beta 3.7',
                'generated_utc':datetime.now(timezone.utc).isoformat(),
                'analysis_mode':'QUANT phenological phases' if self.analysis_scope.currentIndex()==1 else 'Full time series',
                'n_parcels_daily':int(self.results['parcel_id'].nunique()),
                'n_parcels_valid_phase':int(self.phase_summary['parcel_id'].nunique()),
                'plot_variable':self.metric.currentData(),'plot_cumulative':bool(self.mode.currentIndex()==1 and self.metric.currentData()!='kc'),
                'plot_parcels':list(self.plot_parcels),
                'definitions':{'kc':'a * NDVI + b','etc_mm':'Kc * ETo','iwr_net_mm':'max(ETc - Pe, 0)',
                    'phase_intervals':'[sowing,Q1), [Q1,Q2), [Q2,Q3), [Q3,Q4]'},
                'aggregation':'Each parcel contributes one value per phase; across-parcel SD uses sample standard deviation (ddof=1).'}
            (target/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
            QMessageBox.information(self,'Scientific export',f'Exported results to:\n{target}')
        except Exception as e:QMessageBox.warning(self,'Scientific export',str(e))

    def export_phase_summary(self):
        if self.phase_summary is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export phase summary','CropWater_RS_phase_summary.csv','CSV (*.csv)')
        if path:self.phase_summary.to_csv(path,index=False,date_format='%Y-%m-%d')
    def export(self):
        if self.results is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export water analysis','CropWater_RS_daily_water.csv','CSV (*.csv)')
        if path:self.results.to_csv(path,index=False,date_format='%Y-%m-%d')
