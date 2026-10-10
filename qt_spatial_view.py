"""Native Qt spatial viewer. No dependency on the legacy Tk application.

Vector polygons and local georeferenced rasters are loaded in EPSG:3857.
Esri imagery is optional and refreshed after navigation, not during drag.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date, timedelta
import hashlib
import os
from PySide6.QtCore import QStandardPaths
from qt_cdse_dates import DateCatalogWorker
from qt_cdse_raster import RasterWorker, RasterSettings
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QFileDialog, QLabel, QMessageBox, QComboBox, QCheckBox)
from matplotlib.figure import Figure
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'


def bounds_with_padding(bounds, pad=0.08):
    x0,y0,x1,y1 = map(float,bounds)
    dx=max(x1-x0,10.0);dy=max(y1-y0,10.0)
    return (x0-dx*pad,x1+dx*pad,y0-dy*pad,y1+dy*pad)


class SpatialViewer(QWidget):
    def __init__(self, parent=None, parcel_store=None, cdse_provider=None):
        super().__init__(parent)
        self.parcels=None;self.raster=None;self.raster_path=None
        self.parcel_store=parcel_store
        self.cdse_provider=cdse_provider
        self._catalog_worker=None;self._ndvi_worker=None
        self._retired_workers=[];self._closing=False
        self._dates=[];self._date_parcel_index=None;self._active_request=None
        if parcel_store is not None: parcel_store.changed.connect(self._from_store)
        self._basemap_artist=None;self._last_basemap_extent=None
        self._selected=None
        self._raster_stats=None
        self._view_initialized=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        bar=QHBoxLayout()
        self.load_vector=QPushButton('Import parcels');self.load_vector.clicked.connect(self.open_parcels)
        self.load_vector.setVisible(parcel_store is None)
        self.load_raster=QPushButton('Open NDVI GeoTIFF');self.load_raster.clicked.connect(self.open_raster)
        self.background=QComboBox();self.background.addItems(['None','Satellite (Esri)']);self.background.currentIndexChanged.connect(self.refresh)
        self.show_parcels=QCheckBox('Show parcels');self.show_parcels.setChecked(True);self.show_parcels.toggled.connect(self.refresh)
        self.fit_button=QPushButton('Fit all');self.fit_button.clicked.connect(self.fit_extent)
        self.fit_parcel_button=QPushButton('Fit parcel');self.fit_parcel_button.clicked.connect(self.fit_selected_parcel)
        self.refresh_button=QPushButton('Refresh imagery');self.refresh_button.clicked.connect(self.refresh_basemap)
        for w in (self.load_vector,self.load_raster,self.background,self.show_parcels,self.fit_button,self.fit_parcel_button,self.refresh_button):bar.addWidget(w)
        layout.addLayout(bar)
        temporal=QHBoxLayout()
        temporal.addWidget(QLabel('Parcel'))
        self.parcel_selector=QComboBox();self.parcel_selector.setMinimumWidth(100)
        self.parcel_selector.currentIndexChanged.connect(self._parcel_changed)
        temporal.addWidget(self.parcel_selector)
        self.search_dates=QPushButton('Find S2 dates');self.search_dates.clicked.connect(self.discover_dates)
        temporal.addWidget(self.search_dates)
        self.previous_date=QPushButton('◀');self.previous_date.clicked.connect(lambda:self.step_date(1))
        temporal.addWidget(self.previous_date)
        self.date_selector=QComboBox();self.date_selector.setMinimumWidth(125)
        self.date_selector.currentIndexChanged.connect(self._date_changed)
        temporal.addWidget(self.date_selector)
        self.next_date=QPushButton('▶');self.next_date.clicked.connect(lambda:self.step_date(-1))
        temporal.addWidget(self.next_date)
        self.ndvi_status=QLabel('Select parcel and find Sentinel-2 dates')
        temporal.addWidget(self.ndvi_status,1)
        layout.addLayout(temporal)
        self._sync_temporal_controls()
        self.figure=Figure(figsize=(12,7),dpi=100,facecolor='#f7fafc')
        self.ax=self.figure.add_axes([0.012,0.045,0.92,0.935]);self.ax.set_facecolor('#edf2f6')
        self._colorbar_ax=self.figure.add_axes([0.945,0.15,0.018,0.70])
        self._colorbar=self.figure.colorbar(ScalarMappable(norm=Normalize(-1,1),cmap='RdYlGn'),cax=self._colorbar_ax)
        self._colorbar.set_label('NDVI',fontsize=10)
        self._colorbar.set_ticks([-1,-0.5,0,0.2,0.4,0.6,0.8,1])
        self._colorbar_ax.set_visible(False)
        self.canvas=FigureCanvasQTAgg(self.figure);layout.addWidget(self.canvas,1)
        self.toolbar=NavigationToolbar2QT(self.canvas,self);layout.addWidget(self.toolbar)
        self.message=QLabel('Import a parcel vector or a georeferenced NDVI raster to begin.');layout.addWidget(self.message)
        self.stats_label=QLabel('NDVI statistics: no raster loaded');layout.addWidget(self.stats_label)
        self.canvas.mpl_connect('button_release_event',self._navigation_finished)
        self.canvas.mpl_connect('scroll_event',self._wheel_zoom)
        self.canvas.mpl_connect('button_press_event',self._select_parcel)
        self.refresh()

    def open_parcels(self):
        path,_=QFileDialog.getOpenFileName(self,'Import parcel polygons','','Vector (*.gpkg *.geojson *.json *.shp)')
        if path:self.load_parcels(path)

    def load_parcels(self,path):
        try:
            import geopandas as gpd
            gdf=gpd.read_file(path)
            if gdf.empty:raise ValueError('The vector layer contains no features.')
            if gdf.crs is None:raise ValueError('The vector has no CRS. Assign a valid CRS before importing.')
            gdf=gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
            gdf=gdf.to_crs(epsg=3857)
            if gdf.empty:raise ValueError('No valid geometries found.')
            self.parcels=gdf;self._selected=None
            self._sync_temporal_controls()
            if self.parcel_store is not None: self.parcel_store.set_parcels(gdf,path)
            self.fit_extent();self.message.setText(f'{len(gdf)} parcels · {Path(path).name}')
        except Exception as exc:self._error('Cannot load parcels',exc)

    def _from_store(self):
        self.parcels=self.parcel_store.parcels
        self._selected=None
        self._sync_temporal_controls()
        self.fit_extent()
        if self.parcels is not None:
            self.message.setText(f'{len(self.parcels)} parcels loaded from Data Acquisition')

    def open_raster(self):
        path,_=QFileDialog.getOpenFileName(self,'Open georeferenced NDVI raster','','GeoTIFF (*.tif *.tiff)')
        if path:self.load_raster_file(path)

    def load_raster_file(self,path):
        try:
            import rasterio
            from rasterio.warp import calculate_default_transform,reproject,Resampling
            from rasterio.transform import array_bounds
            with rasterio.open(path) as src:
                if src.crs is None:raise ValueError('Raster has no CRS.')
                if src.count<1:raise ValueError('Raster has no bands.')
                transform,w,h=calculate_default_transform(src.crs,'EPSG:3857',src.width,src.height,*src.bounds)
                if w*h>30_000_000:raise ValueError('Raster too large for preview (>30 million pixels).')
                data=np.full((h,w),np.nan,dtype=np.float32)
                reproject(source=rasterio.band(src,1),destination=data,src_transform=src.transform,
                          src_crs=src.crs,dst_transform=transform,dst_crs='EPSG:3857',
                          src_nodata=src.nodata,dst_nodata=np.nan,resampling=Resampling.nearest)
            data[~np.isfinite(data)]=np.nan
            data[(data < -1) | (data > 1)]=np.nan
            x0,y0,x1,y1=array_bounds(h,w,transform)
            self.raster=(data,(x0,x1,y0,y1));self.raster_path=path
            valid=data[np.isfinite(data)]
            if valid.size:
                self.stats_label.setText(f'NDVI · valid pixels: {valid.size:,}  |  mean: {valid.mean():.3f}  |  min: {valid.min():.3f}  |  max: {valid.max():.3f}')
            else:
                self.stats_label.setText('NDVI · no valid pixels')
            # Preserve current viewport when switching acquisition date or product.
            self.refresh(preserve=self._view_initialized)
            self.message.setText(f'NDVI raster · {Path(path).name}')
        except Exception as exc:self._error('Cannot load raster',exc)

    def _extent(self):
        if self.parcels is not None:return bounds_with_padding(self.parcels.total_bounds)
        if self.raster is not None:
            _,(x0,x1,y0,y1)=self.raster
            return bounds_with_padding((x0,y0,x1,y1))
        return None

    def fit_selected_parcel(self):
        # Explicit navigation only: date/product changes preserve the current view.
        if self.parcels is None or self.parcels.empty:return
        idx=self.parcel_selector.currentIndex()
        if idx<0 or idx>=len(self.parcels):return
        bounds=self.parcels.iloc[idx].geometry.bounds
        ext=bounds_with_padding(bounds,0.16)
        self.ax.set_xlim(ext[0],ext[1]);self.ax.set_ylim(ext[2],ext[3])
        self._view_initialized=True
        self.refresh(preserve=True)

    def fit_extent(self):
        ext=self._extent()
        if ext:
            self.ax.set_xlim(ext[0],ext[1]);self.ax.set_ylim(ext[2],ext[3])
            self._view_initialized=True
        self.refresh(preserve=bool(ext))

    def refresh(self,*_args,preserve=True):
        limits=(self.ax.get_xlim(),self.ax.get_ylim()) if preserve and self._extent() else None
        self.ax.clear();self.ax.set_facecolor('#edf2f6')
        self._colorbar_ax.set_visible(self.raster is not None)
        self.ax.set_aspect('equal',adjustable='box')
        if self.raster is not None:
            arr,extent=self.raster
            self.ax.imshow(arr,extent=extent,origin='upper',vmin=-1,vmax=1,cmap='RdYlGn',
                           interpolation='nearest',alpha=0.82,zorder=2)
        if self.parcels is not None and self.show_parcels.isChecked():
            self.parcels.boundary.plot(ax=self.ax,color='#263b50',linewidth=1.1,zorder=3)
            if self._selected is not None:
                self.parcels.iloc[[self._selected]].boundary.plot(ax=self.ax,color='#e547ba',linewidth=2.4,zorder=4)
        if limits:
            self.ax.set_xlim(*limits[0]);self.ax.set_ylim(*limits[1])
        else:
            ext=self._extent()
            if ext:self.ax.set_xlim(ext[0],ext[1]);self.ax.set_ylim(ext[2],ext[3])
            else:
                self.ax.set_xlim(0,1);self.ax.set_ylim(0,1)
                self.ax.text(.5,.5,'Import parcel polygons or NDVI GeoTIFF',ha='center',va='center',transform=self.ax.transAxes)
        self.ax.set_xticks([]);self.ax.set_yticks([])
        if self._extent():self._view_initialized=True
        self.canvas.draw_idle()
        if self.background.currentIndex()==1 and self._extent():self.refresh_basemap()

    def refresh_basemap(self):
        if self.background.currentIndex()!=1 or self._extent() is None:return
        try:
            import contextily as cx
            xlim=self.ax.get_xlim();ylim=self.ax.get_ylim()
            # Remove previous tiles before downloading new coverage.
            for artist in list(self.ax.images):
                if getattr(artist,'_cw_basemap',False):artist.remove()
            before=set(self.ax.images)
            cx.add_basemap(self.ax,source=ESRI,crs='EPSG:3857',attribution=False,
                           reset_extent=True,zorder=0)
            for artist in set(self.ax.images)-before:artist._cw_basemap=True
            self.ax.set_xlim(*xlim);self.ax.set_ylim(*ylim)
            self.message.setText('Satellite imagery updated · Esri')
            self.canvas.draw_idle()
        except Exception as exc:
            self.message.setText(f'Esri imagery unavailable: {exc}')
            self.canvas.draw_idle()

    def _navigation_finished(self,event):
        if event.inaxes is self.ax and self.background.currentIndex()==1 and self._extent():
            self.refresh_basemap()

    def _select_parcel(self,event):
        if event.inaxes is not self.ax or self.parcels is None or event.xdata is None:return
        if self.toolbar.mode:return
        from shapely.geometry import Point
        matches=self.parcels.geometry.intersects(Point(event.xdata,event.ydata))
        if matches.any():
            self._selected=int(np.flatnonzero(matches.to_numpy())[0]);self.parcel_selector.setCurrentIndex(self._selected);self.refresh()
            self.message.setText(f'Parcel selected · row {self._selected+1} / {len(self.parcels)}')

    def _sync_temporal_controls(self):
        self.parcel_selector.blockSignals(True)
        self.parcel_selector.clear()
        if self.parcels is not None:
            for i in range(len(self.parcels)):
                self.parcel_selector.addItem(f'P{i+1:05d}',i)
        self.parcel_selector.blockSignals(False)
        self._clear_dates()

    def _clear_dates(self):
        self._dates=[];self._date_parcel_index=None
        self.date_selector.blockSignals(True);self.date_selector.clear();self.date_selector.blockSignals(False)
        self._update_date_buttons()

    def _update_date_buttons(self):
        valid=bool(self._dates) and self._ndvi_worker is None
        self.previous_date.setEnabled(valid and self.date_selector.currentIndex()<len(self._dates)-1)
        self.next_date.setEnabled(valid and self.date_selector.currentIndex()>0)

    def _parcel_changed(self,index):
        self._selected=index if index>=0 else None
        self._clear_dates()
        if self.parcels is not None and index>=0:self.refresh()
        self.ndvi_status.setText('Find available dates for this parcel')

    def _credentials(self):
        if self.cdse_provider is None:raise ValueError('CDSE settings are unavailable.')
        cid,secret,start,end,resolution=self.cdse_provider()
        if not cid or not secret:raise ValueError('Enter CDSE credentials in Data Acquisition.')
        if start>end:raise ValueError('Start date must precede end date.')
        return cid,secret,start,end,resolution

    def discover_dates(self):
        try:
            idx=self.parcel_selector.currentIndex()
            if self.parcels is None or idx<0:raise ValueError('Import and select a parcel first.')
            cid,secret,start,end,_=self._credentials()
            if self._catalog_worker is not None and self._catalog_worker.isRunning():return
            self._clear_dates()
            self._date_parcel_index=idx
            self.search_dates.setEnabled(False)
            self.ndvi_status.setText(f'Searching CDSE STAC ({start} to {end})…')
            self._catalog_worker=DateCatalogWorker(self.parcels.iloc[idx].geometry,cid,secret,start,end)
            self._catalog_worker.completed.connect(self._dates_ready)
            self._catalog_worker.failed.connect(self._dates_failed)
            self._catalog_worker.finished.connect(self._catalog_finished)
            self._catalog_worker.finished.connect(lambda worker=self._catalog_worker:self._retire_worker(worker))
            self._catalog_worker.start()
        except Exception as exc:self._error('Sentinel-2 dates',exc)

    def _catalog_finished(self):
        self.search_dates.setEnabled(True)
        if self.ndvi_status.text().startswith('Searching CDSE'):
            self.ndvi_status.setText('Date search finished; no response received')

    def _dates_ready(self,dates):
        self._dates=list(dates)
        self.date_selector.blockSignals(True)
        self.date_selector.clear();self.date_selector.addItems(self._dates)
        self.date_selector.blockSignals(False)
        self.ndvi_status.setText(f'{len(dates)} acquisition dates found' if dates else 'No Sentinel-2 scenes in the selected interval')
        self._update_date_buttons()
        if dates:self._date_changed(0)

    def _dates_failed(self,message):
        self.search_dates.setEnabled(True)
        self.ndvi_status.setText(f'Date search failed: {message[:120]}')
        self._error('CDSE Catalog',message)

    def step_date(self,offset):
        index=self.date_selector.currentIndex()+offset
        if 0<=index<len(self._dates):self.date_selector.setCurrentIndex(index)

    def _date_changed(self,index):
        self._update_date_buttons()
        if index<0 or self._date_parcel_index!=self.parcel_selector.currentIndex():return
        if self._ndvi_worker is not None:return
        try:
            cid,secret,_,_,resolution=self._credentials()
            parcel_index=self.parcel_selector.currentIndex()
            acquisition=self._dates[index]
            geom=self.parcels.iloc[parcel_index].geometry
            fingerprint=hashlib.sha256(geom.wkb+str(resolution).encode()).hexdigest()[:16]
            cache_root=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
            cache=Path(cache_root or str(Path.home()/'.cache'/'CropWater-RS'))/'ndvi'
            cache.mkdir(parents=True,exist_ok=True)
            output=cache/f'{fingerprint}_{acquisition}_{resolution}m.tif'
            if output.exists():
                self.load_raster_file(str(output))
                self.ndvi_status.setText(f'{acquisition} · cached NDVI')
                return
            end=(date.fromisoformat(acquisition)+timedelta(days=1)).isoformat()
            settings=RasterSettings(cid,secret,acquisition,end,int(resolution),str(output))
            self._active_request=(parcel_index,acquisition)
            self._ndvi_worker=RasterWorker(geom,settings)
            self._ndvi_worker.progress.connect(lambda value,msg:self.ndvi_status.setText(f'{value}% · {msg}'))
            self._ndvi_worker.completed.connect(self._ndvi_completed)
            self._ndvi_worker.finished.connect(lambda worker=self._ndvi_worker:self._ndvi_finished(worker))
            self._ndvi_worker.failed.connect(self._ndvi_failed)
            self._ndvi_worker.start()
            self._update_date_buttons()
        except Exception as exc:self._error('NDVI acquisition',exc)

    def _ndvi_completed(self,path,count):
        if self._active_request and self._active_request[0]==self.parcel_selector.currentIndex() and self._active_request[1]==self.date_selector.currentText():
            self.load_raster_file(path)
            self.ndvi_status.setText(f'{self._active_request[1]} · {count:,} valid pixels')
        self._update_date_buttons()
        # The next request starts only after QThread.finished.

    def _ndvi_failed(self,message):
        self.ndvi_status.setText('NDVI download failed')
        self._update_date_buttons()
        self._error('CDSE Process API',message)

    def _retire_worker(self,worker):
        # Keep a Python reference until Qt has emitted finished.
        if worker is self._catalog_worker:self._catalog_worker=None
        if worker is self._ndvi_worker:self._ndvi_worker=None
        if worker in self._retired_workers:self._retired_workers.remove(worker)
        worker.deleteLater()

    def _ndvi_finished(self,worker):
        self._retire_worker(worker)
        if not self._closing:
            self._update_date_buttons()
            self._load_pending_date()

    def _wheel_zoom(self,event):
        if event.inaxes is not self.ax or event.xdata is None or event.ydata is None:return
        direction=getattr(event,'step',0)
        if not direction:return
        factor=1.0/(1.25**direction)
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        cx,cy=float(event.xdata),float(event.ydata)
        self.ax.set_xlim(cx+(x0-cx)*factor,cx+(x1-cx)*factor)
        self.ax.set_ylim(cy+(y0-cy)*factor,cy+(y1-cy)*factor)
        self.canvas.draw_idle()
        # Avoid synchronous tile downloads on every wheel event; use Refresh imagery.

    def closeEvent(self,event):
        self._closing=True
        running=[w for w in (self._catalog_worker,self._ndvi_worker) if w is not None and w.isRunning()]
        if running:
            for worker in running:worker.requestInterruption()
            # Never destroy a live QThread: wait for requests to finish before closing.
            if any(not worker.wait(1500) for worker in running):
                event.ignore()
                self.ndvi_status.setText('Finishing CDSE request before closing; please retry shortly')
                self._closing=False
                return
        super().closeEvent(event)

    def _load_pending_date(self):
        idx=self.date_selector.currentIndex()
        if idx>=0 and self._active_request!=(self.parcel_selector.currentIndex(),self._dates[idx]):
            self._date_changed(idx)

    def _error(self,title,exc):
        self.message.setText(str(exc));QMessageBox.warning(self,title,str(exc))
