"""Windows environment readiness check; does not claim to test actual GUI interaction."""
import importlib, platform, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
print('Platform:',platform.platform())
print('Python:',sys.version.split()[0])
required=['numpy','pandas','geopandas','shapely','matplotlib','scipy','sentinelhub','tkinter','pyproj','pyogrio']
missing=[]
for name in required:
    try: importlib.import_module(name)
    except Exception as exc:
        missing.append(name)
        print('FAIL',name,type(exc).__name__,str(exc))
    else: print('OK',name)
print('Launcher:', 'OK' if (root/'cropwater_rs.py').exists() else 'MISSING')
if missing:
    print('Dependencies missing:',', '.join(missing))
    sys.exit(1)
print('READY FOR MANUAL GUI ACCEPTANCE (not yet executed)')
