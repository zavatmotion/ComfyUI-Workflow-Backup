import os
import json
import shutil
import folder_paths
from pathlib import Path
from comfy.utils import ProgressBar

class WorkflowBackupNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "workflows_path": ("STRING", {"default": "Paste your path here", "multiline": False}),
                # CAMBIO AQUÍ: Default seguro dentro de ComfyUI para que funcione sin JSON
                "backup_destination": ("STRING", {"default": "output/workflow_backups", "multiline": False}),
                "mode": (["ANALYSIS_ONLY", "EXECUTE_BACKUP"],),
                "language": (["English", "Spanish"],),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status_report",)
    FUNCTION = "process_backup"
    OUTPUT_NODE = True
    CATEGORY = "utils/backup"

    def process_backup(self, workflows_path, backup_destination, mode, language):
        
        # --- SECURITY: LOAD WHITELIST ---
        def get_allowed_roots():
            """
            Reads 'extra_paths.json' from the node directory to find allowed external paths.
            Always includes the ComfyUI base directory as a safe default.
            """
            allowed = [os.path.abspath(folder_paths.base_path)]
            
            # Look for config file in the same folder as this script
            current_dir = os.path.dirname(os.path.realpath(__file__))
            config_file = os.path.join(current_dir, "extra_paths.json")
            
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        data = json.load(f)
                        for path in data.get("allowed_paths", []):
                            if os.path.exists(path):
                                allowed.append(os.path.abspath(path))
                except Exception as e:
                    print(f"[WorkflowBackup] Warning: Could not read extra_paths.json: {e}")
            
            return allowed

        def is_safe_path(path_str, allowed_roots):
            """
            Checks if the path is inside one of the allowed roots using commonpath.
            """
            if not path_str: return False
            
            try:
                # Handle relative paths by joining with base_path just for the check
                if not os.path.isabs(path_str):
                    clean_path = os.path.abspath(os.path.join(folder_paths.base_path, path_str.strip().strip('"').strip("'")))
                else:
                    clean_path = os.path.abspath(os.path.normpath(path_str.strip().strip('"').strip("'")))
                
                for root in allowed_roots:
                    root_clean = os.path.abspath(root)
                    try:
                        # Check if clean_path starts with root_clean
                        if os.path.commonpath([clean_path, root_clean]) == root_clean:
                            return True
                    except ValueError:
                        continue # Different drives
            except Exception:
                return False
                
            return False

        # --- VALIDATION ---
        
        # 1. Load Permissions
        allowed_roots = get_allowed_roots()
        
        # 2. Check Paths
        w_ok = is_safe_path(workflows_path, allowed_roots)
        d_ok = is_safe_path(backup_destination, allowed_roots)
        
        # Messages
        msgs = {
            "English": {
                "err_security": "⛔ SECURITY ERROR: Path not allowed. To use external drives, create 'extra_paths.json' in the node folder. Rejected: ",
                "err_path": "❌ ERROR: The workflows folder does not exist: ",
                "err_no_json": "⚠️ No .json files found in ",
                "analyzing": "🔍 Analyzing {count} workflows in: {path}",
                "err_read": "⚠️ Error reading {file}: {error}",
                "found": "✅ Found {count} unique models required.",
                "size": "📦 Estimated Total Size: {size:.2f} GB",
                "err_dest": "❌ Error creating destination folder: {path}",
                "copying": "Copying: {name}...",
                "err_copy": "Error copying {src}: {error}",
                "done": "🎉 BACKUP COMPLETED: {count} new models copied.",
                "location": "📁 Location: {path}",
                "analysis_mode": "ℹ️ ANALYSIS MODE: No files were copied. Switch mode to EXECUTE_BACKUP to perform the copy."
            },
            "Spanish": {
                "err_security": "⛔ ERROR DE SEGURIDAD: Ruta no permitida. Para usar discos externos, crea 'extra_paths.json' en la carpeta del nodo. Rechazada: ",
                "err_path": "❌ ERROR: La carpeta de workflows no existe: ",
                "err_no_json": "⚠️ No se encontraron archivos .json en ",
                "analyzing": "🔍 Analizando {count} workflows en: {path}",
                "err_read": "⚠️ Error leyendo {file}: {error}",
                "found": "✅ Se encontraron {count} modelos únicos necesarios.",
                "size": "📦 Tamaño total estimado: {size:.2f} GB",
                "err_dest": "❌ Error creando carpeta destino: {path}",
                "copying": "Copiando: {name}...",
                "err_copy": "Error copiando {src}: {error}",
                "done": "🎉 RESPALDO COMPLETADO: {count} modelos nuevos copiados.",
                "location": "📁 Ubicación: {path}",
                "analysis_mode": "ℹ️ MODO ANÁLISIS: No se copiaron archivos. Cambia el modo a EXECUTE_BACKUP para copiar."
            }
        }
        
        T = msgs[language] 

        if not w_ok:
            return (f"{T['err_security']} {workflows_path}",)
        if not d_ok:
            return (f"{T['err_security']} {backup_destination}",)

        # 3. Standard Logic
        # Handle relative vs absolute for execution
        raw_w = workflows_path.strip().strip('"').strip("'")
        raw_d = backup_destination.strip().strip('"').strip("'")
        
        if os.path.isabs(raw_w):
            w_path = Path(raw_w)
        else:
            w_path = Path(folder_paths.base_path) / raw_w
            
        if os.path.isabs(raw_d):
            dest_path = Path(raw_d)
        else:
            dest_path = Path(folder_paths.base_path) / raw_d

        comfy_root = Path(folder_paths.base_path)
        models_root = comfy_root / "models"
        
        if not w_path.exists():
            return (f"{T['err_path']}{workflows_path}",)

        workflows_found = list(w_path.rglob("*.json"))
        if not workflows_found:
            return (f"{T['err_no_json']}{workflows_path}",)

        report = []
        report.append(T['analyzing'].format(count=len(workflows_found), path=w_path))
        
        files_to_copy = {} # {source_path: category}
        
        # --- ANALYSIS PHASE ---
        for wf_file in workflows_found:
            try:
                with open(wf_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                nodes = data.get('nodes', [])
                if not nodes and isinstance(data, dict): 
                      nodes = list(data.values())

                for node in nodes:
                    if not isinstance(node, dict): continue
                    
                    valores = []
                    widgets = node.get('widgets_values', [])
                    inputs = node.get('inputs', {})
                    
                    if isinstance(widgets, list): valores.extend(widgets)
                    if isinstance(inputs, dict): valores.extend(inputs.values())

                    for val in valores:
                        if not isinstance(val, str): continue
                        
                        if any(ext in val.lower() for ext in ['.safetensors', '.pt', '.pth', '.ckpt', '.bin']):
                            ruta_real = self._find_model_file(models_root, val)
                            if ruta_real:
                                cat_detectada = Path(ruta_real).parent.name
                                files_to_copy[ruta_real] = cat_detectada
            except Exception as e:
                report.append(T['err_read'].format(file=wf_file.name, error=str(e)))

        total_files = len(files_to_copy)
        total_size = sum(os.path.getsize(f) for f in files_to_copy.keys()) / (1024**3)
        
        report.append(T['found'].format(count=total_files))
        report.append(T['size'].format(size=total_size))

        # --- EXECUTION PHASE ---
        if mode == "EXECUTE_BACKUP":
            if not dest_path.exists():
                try:
                    dest_path.mkdir(parents=True)
                except Exception:
                    return (f"{T['err_dest'].format(path=dest_path)}",)
            
            # 1. Backup Workflows
            wf_dest = dest_path / "workflows_backup"
            wf_dest.mkdir(exist_ok=True)
            for wf in workflows_found:
                try:
                    shutil.copy2(wf, wf_dest)
                except: pass
            
            # 2. Backup Models
            copied_count = 0
            pbar = ProgressBar(total_files)
            
            for src, cat in files_to_copy.items():
                try:
                    final_dest_folder = dest_path / "models" / cat
                    final_dest_folder.mkdir(parents=True, exist_ok=True)
                    
                    src_path = Path(src)
                    final_dest_file = final_dest_folder / src_path.name
                    
                    if not final_dest_file.exists():
                        print(T['copying'].format(name=src_path.name))
                        shutil.copy2(src_path, final_dest_file)
                        copied_count += 1
                    
                    pbar.update(1)
                    
                except Exception as e:
                    print(T['err_copy'].format(src=src, error=str(e)))
            
            report.append(T['done'].format(count=copied_count))
            report.append(T['location'].format(path=dest_path))
        
        else:
            report.append(T['analysis_mode'])

        return ("\n".join(report),)

    def _find_model_file(self, root_path, filename):
        possible_path = root_path / filename
        if possible_path.exists(): return str(possible_path)
        
        clean_name = Path(filename).name
        for file in root_path.rglob(clean_name):
            return str(file)
        return None
