"""Native QUANT phenology UI; calls the unchanged scientific core."""
import sys
from pathlib import Path
import pandas as pd
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox,QComboBox,QDoubleSpinBox,QTableWidget,QTableWidgetItem,QHeaderView,QCheckBox,QGroupBox,QGridLayout,QDateEdit,QSpinBox,QLineEdit,QDialog,QDialogButtonBox,QListWidget,QListWidgetItem,QAbstractItemView
from PySide6.QtCore import QDate,Qt
from qt_quant_scope import resolve_start, filter_daily, normalize_id
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from cropwater_rs.core.quant import calculate_quant_one,validate_quant_thresholds

class ParcelSelectionDialog(QDialog):
    """Searchable, scalable multi-parcel selector; edits committed only on Apply."""
    def __init__(self, ids, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select parcels for QUANT')
        self.resize(480, 570)
        layout=QVBoxLayout(self)
        self.search=QLineEdit();self.search.setPlaceholderText('Search parcel ID...')
        self.search.textChanged.connect(self._filter);layout.addWidget(self.search)
        self.list=QListWidget();self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for pid in ids:
            item=QListWidgetItem(str(pid));item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if pid in selected else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._update_count)
        layout.addWidget(self.list,1)
        self.count=QLabel();layout.addWidget(self.count)
        actions=QHBoxLayout()
        for label,fn in [('Select filtered',lambda:self._check_visible(True)),('Clear filtered',lambda:self._check_visible(False)),('Select all',lambda:self._check_all(True)),('Clear all',lambda:self._check_all(False))]:
            b=QPushButton(label);b.clicked.connect(fn);actions.addWidget(b)
        layout.addLayout(actions)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Apply selection')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self._update_count()
    def _filter(self,text):
        term=text.strip().casefold()
        for i in range(self.list.count()):
            item=self.list.item(i);item.setHidden(term not in item.text().casefold())
        self._update_count()
    def _check_visible(self,checked):
        for i in range(self.list.count()):
            item=self.list.item(i)
            if not item.isHidden():item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    def _check_all(self,checked):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    def _update_count(self,*args):
        selected=sum(self.list.item(i).checkState()==Qt.CheckState.Checked for i in range(self.list.count()))
        visible=sum(not self.list.item(i).isHidden() for i in range(self.list.count()))
        self.count.setText(f'{selected:,} selected · {visible:,} visible · {self.list.count():,} total')
    def selected_ids(self):
        return {self.list.item(i).text() for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked}

class QuantPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.data=None;self.results=None;self.parcel_store=None;self.start_overrides={};self.selected_ids=set();self.manual_selected_ids=set()
        lay=QVBoxLayout(self)
        title=QLabel('Time Series · QUANT phenological analysis');title.setStyleSheet('font-size:20px;font-weight:600;color:#173249');lay.addWidget(title)
        lay.addWidget(QLabel('Uses the original QUANT scientific core. Requires daily reconstructed NDVI; QC observations alone are not sufficient.'))
        top=QHBoxLayout();self.load=QPushButton('Open reconstructed daily NDVI CSV');self.load.clicked.connect(self.open_csv);top.addWidget(self.load)
        self.parcel=QComboBox();self.parcel.currentIndexChanged.connect(self.draw);top.addWidget(QLabel('Parcel'));top.addWidget(self.parcel)
        self.spins=[]
        for name,default in zip(('Q1','Q2','Q3','Q4'),(10,90,90,50)):
            spin=QDoubleSpinBox();spin.setRange(0.1,99.9);spin.setDecimals(1);spin.setValue(default);spin.setSuffix(' %');top.addWidget(QLabel(name));top.addWidget(spin);self.spins.append(spin)
        lay.addLayout(top)
        scope_box=QGroupBox('QUANT scope and analysis start');scope=QVBoxLayout(scope_box)
        sr=QHBoxLayout();sr.addWidget(QLabel('Analysis scope'))
        self.scope=QComboBox();self.scope.addItems(['All parcels','Selected parcels']);self.scope.currentIndexChanged.connect(self._scope_changed);sr.addWidget(self.scope)
        self.select_button=QPushButton('Select parcels...');self.select_button.clicked.connect(self._open_selector);sr.addWidget(self.select_button)
        self.selection_summary=QLabel('No parcels loaded');sr.addWidget(self.selection_summary,1)
        scope.addLayout(sr)
        st=QHBoxLayout();st.addWidget(QLabel('Analysis start'))
        self.start_mode=QComboBox();self.start_mode.addItems(['Full reconstructed series','Manual start','Vector attribute']);self.start_mode.currentIndexChanged.connect(self._start_changed);st.addWidget(self.start_mode)
        self.start_kind=QComboBox();self.start_kind.addItems(['Calendar date','DOY']);self.start_kind.currentIndexChanged.connect(self._start_changed);st.addWidget(self.start_kind)
        self.start_date=QDateEdit();self.start_date.setCalendarPopup(True);self.start_date.setDisplayFormat('yyyy-MM-dd');self.start_date.setDate(QDate.currentDate());st.addWidget(self.start_date)
        self.start_doy=QSpinBox();self.start_doy.setRange(1,366);self.start_doy.setValue(1);st.addWidget(self.start_doy)
        self.start_year=QSpinBox();self.start_year.setRange(1980,2200);self.start_year.setValue(QDate.currentDate().year());st.addWidget(QLabel('Year'));st.addWidget(self.start_year)
        self.vector_column=QComboBox();st.addWidget(QLabel('Vector column'));st.addWidget(self.vector_column)
        self.manual_target=QComboBox();self.manual_target.addItems(['All parcels','Selected parcels']);self.manual_target.currentIndexChanged.connect(self._manual_target_changed);st.addWidget(QLabel('Apply manual date to'));st.addWidget(self.manual_target)
        self.manual_select=QPushButton('Choose parcels...');self.manual_select.clicked.connect(self._choose_manual_parcels);st.addWidget(self.manual_select)
        self.manual_target_count=QLabel('');st.addWidget(self.manual_target_count)
        self.save_manual=QPushButton('Assign manual start...');self.save_manual.clicked.connect(self._save_manual);st.addWidget(self.save_manual)
        scope.addLayout(st)
        self.start_hint=QLabel('Full series: current QUANT behavior.');scope.addWidget(self.start_hint)
        lay.addWidget(scope_box);self._scope_changed();self._start_changed();self._manual_target_changed()
        buttons=QHBoxLayout();run=QPushButton('Run QUANT');run.setObjectName('primary');run.clicked.connect(self.run_quant);buttons.addWidget(run)
        export=QPushButton('Export QUANT CSV');export.clicked.connect(self.export);buttons.addWidget(export);self.export_btn=export;export.setEnabled(False);lay.addLayout(buttons)
        self.status=QLabel('Load a CSV with parcel_id, date, ndvi_reconstructed_daily.');lay.addWidget(self.status)
        self.figure=Figure(figsize=(10,4));self.canvas=FigureCanvasQTAgg(self.figure);lay.addWidget(self.canvas,3)
        self.table=QTableWidget();lay.addWidget(self.table,2)
    def set_data(self,df,source='Preprocessing'):
        needed={'parcel_id','date','ndvi_reconstructed_daily'}
        if not needed.issubset(df.columns):raise ValueError('Reconstruction columns missing')
        data=df.copy();data['date']=pd.to_datetime(data['date'],errors='coerce');data['ndvi_reconstructed_daily']=pd.to_numeric(data['ndvi_reconstructed_daily'],errors='coerce')
        data=data.dropna(subset=['parcel_id','date','ndvi_reconstructed_daily'])
        if data.empty:raise ValueError('No finite reconstructed daily NDVI')
        self.data=data;self.results=None;self.start_overrides={};self.manual_selected_ids=set();self.export_btn.setEnabled(False)
        self.parcel.blockSignals(True);self.parcel.clear();self.parcel.addItems(sorted(data['parcel_id'].astype(str).unique()));self.parcel.blockSignals(False)
        self._populate_checks();self.status.setText(f'{len(data):,} daily reconstructed observations received from {source}. Ready for QUANT.')
        self.draw()
    def invalidate_data(self):
        self.data=None;self.results=None;self.start_overrides={};self.manual_selected_ids=set();self.export_btn.setEnabled(False);self.parcel.clear();self._populate_checks()
        self.table.setRowCount(0);self.figure.clear();self.canvas.draw_idle()
        self.status.setText('Upstream QC or reconstruction changed. Reconstruct again to run QUANT.')
    def open_csv(self):
        path,_=QFileDialog.getOpenFileName(self,'Open daily reconstructed NDVI','','CSV (*.csv)')
        if not path:return
        try:
            df=pd.read_csv(path)
            needed={'parcel_id','date','ndvi_reconstructed_daily'}
            if not needed.issubset(df.columns):raise ValueError('Required columns: '+', '.join(sorted(needed)))
            df['date']=pd.to_datetime(df['date'],errors='coerce')
            df['ndvi_reconstructed_daily']=pd.to_numeric(df['ndvi_reconstructed_daily'],errors='coerce')
            df=df.dropna(subset=['parcel_id','date','ndvi_reconstructed_daily'])
            if df.empty:raise ValueError('No valid daily observations.')
            self.set_data(df,Path(path).name)
        except Exception as exc:QMessageBox.warning(self,'QUANT input error',str(exc))
    def run_quant(self):
        if self.data is None:QMessageBox.warning(self,'QUANT','Load reconstructed daily NDVI first.');return
        try:
            thresholds=tuple(s.value() for s in self.spins);validate_quant_thresholds(*thresholds)
            temporal={str(k):{'daily':g[['date','ndvi_reconstructed_daily']].copy()} for k,g in self.data.groupby(self.data['parcel_id'].astype(str))}
            ids=list(temporal) if self.scope.currentIndex()==0 else [pid for pid in temporal if pid in self.selected_ids]
            if not ids:raise ValueError('Select at least one parcel to analyze.')
            records=[]
            for pid in ids:
                source='full';start_date=None;original=temporal[pid]['daily']
                try:
                    if self.start_mode.currentIndex()==1:
                        if pid in self.start_overrides:
                            start_date=self.start_overrides[pid];source='manual_parcel'
                        else:
                            start_date=None;source='full_unassigned_manual'
                    elif self.start_mode.currentIndex()==2:
                        start_date=self._vector_start(pid,original);source='vector:'+self.vector_column.currentText()
                    subset=filter_daily(original,start_date)
                    rec=calculate_quant_one(pid,{pid:{'daily':subset}},thresholds=thresholds)
                except Exception as exc:rec={'parcel_id':pid,'status':'Error','error':str(exc)};subset=filter_daily(original,start_date) if start_date is not None else original
                rec.update({'analysis_start_date':str(pd.Timestamp(start_date).date()) if start_date is not None else str(pd.to_datetime(original['date']).min().date()),'analysis_start_DOY':int(pd.Timestamp(start_date).dayofyear) if start_date is not None else int(pd.to_datetime(original['date']).min().dayofyear),'start_source':source,'n_days_analyzed':len(subset)})
                records.append(rec)
            self.results=pd.DataFrame(records);self.export_btn.setEnabled(True)
            self.table.setColumnCount(len(self.results.columns));self.table.setRowCount(len(self.results));self.table.setHorizontalHeaderLabels(list(self.results.columns))
            for i,row in enumerate(self.results.itertuples(index=False,name=None)):
                for j,val in enumerate(row):self.table.setItem(i,j,QTableWidgetItem(str(val) if pd.notna(val) else ''))
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            ok=(self.results['status']=='Complete').sum();self.status.setText(f'QUANT: {ok} complete of {len(self.results)} parcels; see table for incomplete/error results.')
            self.draw()
        except Exception as exc:QMessageBox.warning(self,'QUANT execution error',str(exc))
    def set_parcel_store(self,store):
        self.parcel_store=store
        store.changed.connect(self._refresh_vector_columns)
        self._refresh_vector_columns()
    def _refresh_vector_columns(self):
        self.vector_column.clear()
        gdf=getattr(self.parcel_store,'parcels',None)
        if gdf is not None:self.vector_column.addItems([str(c) for c in gdf.columns if c!='geometry'])
    def _populate_checks(self):
        if self.data is None:
            self.selected_ids=set();self._update_selection_summary();return
        ids=sorted(self.data['parcel_id'].astype(str).unique())
        self.manual_selected_ids=set(ids)
        self._manual_target_changed()
        # New data defaults to all selected; no persistent stale IDs.
        self.selected_ids=set(ids)
        self._update_selection_summary()
    def _open_selector(self):
        if self.data is None:return
        ids=sorted(self.data['parcel_id'].astype(str).unique())
        dialog=ParcelSelectionDialog(ids,self.selected_ids,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.selected_ids=dialog.selected_ids()
            self._update_selection_summary()
    def _update_selection_summary(self):
        total=len(self.data['parcel_id'].astype(str).unique()) if self.data is not None else 0
        self.selection_summary.setText(f'{len(self.selected_ids):,} of {total:,} parcels selected')
    def _scope_changed(self,*args):
        enabled=self.scope.currentIndex()==1
        self.select_button.setVisible(enabled)
        self.selection_summary.setVisible(enabled)
    def _start_changed(self,*args):
        mode=self.start_mode.currentIndex();manual=mode==1;vector=mode==2
        self.start_kind.setVisible(manual);self.start_date.setVisible(manual and self.start_kind.currentIndex()==0)
        self.start_doy.setVisible(manual and self.start_kind.currentIndex()==1);self.start_year.setVisible(manual and self.start_kind.currentIndex()==1)
        self.manual_target.setVisible(manual);self.manual_select.setVisible(manual and self.manual_target.currentIndex()==1);self.manual_target_count.setVisible(manual);self.save_manual.setVisible(manual);self.vector_column.setVisible(vector)
        self.start_hint.setText('Manual: choose all parcels or a specific group, then confirm the date assignment.' if manual else 'Vector: start value is read separately for each parcel.' if vector else 'Full series: current QUANT behavior.')
    def _manual_start(self):
        if self.start_kind.currentIndex()==0:return pd.Timestamp(self.start_date.date().toString('yyyy-MM-dd'))
        return resolve_start(self.start_doy.value(),year=self.start_year.value(),kind='doy')
    def _manual_target_changed(self,*args):
        if not hasattr(self,'manual_target_count'):return
        total=len(self.data['parcel_id'].astype(str).unique()) if self.data is not None else 0
        count=total if self.manual_target.currentIndex()==0 else len(self.manual_selected_ids)
        self.manual_target_count.setText(f'{count}/{total} parcels')
        self.manual_select.setVisible(self.start_mode.currentIndex()==1 and self.manual_target.currentIndex()==1)
    def _choose_manual_parcels(self):
        if self.data is None:return
        ids=sorted(self.data['parcel_id'].astype(str).unique())
        dialog=ParcelSelectionDialog(ids,self.manual_selected_ids,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.manual_selected_ids=dialog.selected_ids();self._manual_target_changed()
    def _save_manual(self):
        if self.data is None:
            QMessageBox.information(self,'Manual QUANT start','Load daily reconstructed NDVI first.');return
        ids=sorted(self.data['parcel_id'].astype(str).unique())
        selected=ids if self.manual_target.currentIndex()==0 else [p for p in ids if p in self.manual_selected_ids]
        if not selected:
            QMessageBox.warning(self,'Manual QUANT start','Select at least one parcel.');return
        try:
            date=self._manual_start()
        except ValueError as exc:
            QMessageBox.warning(self,'Start date',str(exc));return
        msg=f'Assign analysis start {date.date()} to {len(selected)} of {len(ids)} parcels?\nThis is the QUANT analysis start, not necessarily the sowing date.'
        if QMessageBox.question(self,'Confirm QUANT start assignment',msg)!=QMessageBox.StandardButton.Yes:return
        for pid in selected:self.start_overrides[pid]=date
        self.results=None;self.export_btn.setEnabled(False)
        self.start_hint.setText(f'Saved QUANT analysis start {date.date()} for {len(selected)} parcels; rerun QUANT.')
    def _vector_start(self,pid,daily):
        gdf=getattr(self.parcel_store,'parcels',None)
        if gdf is None:raise ValueError('Import a parcel vector first.')
        col=self.vector_column.currentText()
        if not col:raise ValueError('Choose a vector attribute containing start dates or DOY.')
        ids=[c for c in gdf.columns if c.lower() in ('id','parcel_id','id_parcela','parcela','name')]
        if not ids:raise ValueError('No recognized parcel ID column in vector; cannot safely match records.')
        matches=gdf[gdf[ids[0]].map(normalize_id)==normalize_id(pid)]
        if len(matches)!=1:raise ValueError(f'Expected one vector record for parcel {pid}, found {len(matches)}.')
        val=matches.iloc[0][col]
        year=int(pd.to_datetime(daily['date']).min().year)
        return resolve_start(val,year=year,kind='auto')
    def draw(self,*args):
        self.figure.clear();ax=self.figure.add_subplot(111)
        if self.data is not None and self.parcel.currentText():
            pid=self.parcel.currentText();g=self.data[self.data['parcel_id'].astype(str)==pid].sort_values('date')
            g = g.copy();g['date'] = pd.to_datetime(g['date'], errors='coerce');g = g.dropna(subset=['date'])
            ax.plot(g['date'],g['ndvi_reconstructed_daily'],color='#16886b',label='Reconstructed NDVI')
            if self.results is not None:
                match=self.results[self.results['parcel_id'].astype(str)==pid]
                if not match.empty:
                    r=match.iloc[0]
                    for q in ('Q1','Q2','Q3','Q4'):
                        date=pd.to_datetime(r.get(q+'_date'),errors='coerce')
                        if pd.notna(date):ax.axvline(date,linestyle='--',label=q)
            ax.legend(loc='best')
        ax.set_ylabel('NDVI');ax.set_xlabel('Date');ax.grid(alpha=.2);self.figure.autofmt_xdate();self.canvas.draw_idle()
    def export(self):
        if self.results is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export QUANT results','quant_results.csv','CSV (*.csv)')
        if path:self.results.to_csv(path,index=False);self.status.setText('Exported QUANT results: '+path)
