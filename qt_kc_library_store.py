"""Persistent user formulations; built-ins are never edited."""
import json, os, re, tempfile
from pathlib import Path
from cropwater_rs.core.kc_library import KC_CATALOG

def library_path():
    base=Path(os.environ.get('APPDATA') or (Path.home()/'.config'))/'CropWater-RS'
    return base/'kc_ndvi_library.json'

class KcLibrary:
    def __init__(self,path=None):
        self.path=Path(path) if path else library_path()
        self.custom={}
        if self.path.exists():
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('schema')!=1:raise ValueError('Unsupported Kc library schema')
            for key,entry in data.get('formulations',{}).items():
                self._validate(key,entry)
                self.custom[key]=entry
    @staticmethod
    def _validate(key,entry):
        import math
        if not re.fullmatch(r'user_[a-z0-9_]+',key):raise ValueError('Invalid formulation ID')
        if not str(entry.get('label','')).strip():raise ValueError('Formulation name required')
        for c in ('a','b'):
            if not math.isfinite(float(entry[c])):raise ValueError('Coefficients must be finite')
        if not isinstance(entry.get('crops',[]),list):raise ValueError('Crops must be a list')
    def all(self):return {**KC_CATALOG,**self.custom}
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.kc_',suffix='.json',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump({'schema':1,'formulations':self.custom},f,ensure_ascii=False,indent=2)
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    def upsert(self,key,entry):
        self._validate(key,entry)
        if key in KC_CATALOG:raise ValueError('Built-in formulation cannot be modified')
        self.custom[key]=dict(entry);self.save()
    def delete(self,key):
        if key not in self.custom:raise ValueError('Only user formulations can be deleted')
        del self.custom[key];self.save()
    def export_json(self,path):
        Path(path).write_text(json.dumps({'schema':1,'formulations':self.custom},ensure_ascii=False,indent=2),encoding='utf-8')
    def import_json(self,path):
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('schema')!=1 or not isinstance(data.get('formulations'),dict):raise ValueError('Invalid library file')
        for key,entry in data['formulations'].items():self._validate(key,entry)
        self.custom.update(data['formulations']);self.save()
