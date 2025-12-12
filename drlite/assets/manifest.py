import os
import json
from typing import Optional, Dict, Any

# ==============================================================================
#  PATHFINDER: El sistema de rutas dinámicas
# ==============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
IMG_DIR = os.path.join(PROJECT_ROOT, "img")
_ASSETS_MANIFEST: Dict[str, Any] = {}

def load_assets_manifest(filename: str = "assets_manifest.json") -> Dict[str, Any]:
    """
    Carga el JSON de configuración de assets desde la carpeta 'data/'.
    """
    global _ASSETS_MANIFEST
    
    full_path = os.path.join(DATA_DIR, filename)
    
    if not os.path.exists(full_path):
        print(f"[assets] WARNING: No se encontró el manifest en: {full_path}")
        return {}

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            _ASSETS_MANIFEST = json.load(f)
        
        # Debug info
        count = len(_ASSETS_MANIFEST.get('sources', {}))
        print(f"[assets] Manifest cargado correctamente desde {full_path}. Fuentes detectadas: {count}")
        return _ASSETS_MANIFEST
    except Exception as e:
        print(f"[assets] ERROR: El archivo {filename} está corrupto o es ilegible: {e}")
        return {}

def get_portrait_path(demon_id: str | Any, expression: str = "default") -> Optional[str]:
    """
    Devuelve la RUTA ABSOLUTA de la imagen del demonio para que Discord la pueda subir.
    
    Args:
        demon_id: El objeto Demon o su ID string.
    """
    if not _ASSETS_MANIFEST:
        load_assets_manifest()
        if not _ASSETS_MANIFEST:
            return None

    d_id = getattr(demon_id, "id", str(demon_id))

    mappings = _ASSETS_MANIFEST.get("mappings", {})
    entry = mappings.get(d_id)
    
    if not entry:
        return None

    source_key = entry.get("source") 
    img_key = entry.get("key")       
    

    sources = _ASSETS_MANIFEST.get("sources", {})
    src_config = sources.get(source_key)
    
    if not src_config:
        return None
    root_folder = src_config.get("root", "")
    ext = src_config.get("ext", ".png")

    full_path = os.path.join(IMG_DIR, root_folder, f"{img_key}{ext}")
    
    if os.path.exists(full_path):
        return full_path
    
    return None