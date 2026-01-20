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
                "backup_destination": ("STRING", {"default": "D:/ComfyUI_Backup", "multiline": False}),
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
        # 1. Path Cleaning (Sanitization)
        # Fixes requested by ComfyUI-Manager (Dr.Lt.Data)
        def sanitize_path(path_str):
            if not path_str:
                return None
            # Strip quotes and whitespace
            clean = path_str.strip().strip('"').strip("'")
            # Normalize path (fixes slashes and resolves '..') and make absolute
            return Path(os.path.abspath(os.path.normpath(clean)))

        w_path = sanitize_path(workflows_path)
        dest_path = sanitize_path(backup_destination)
        
        # 2. Setup Messages
        msgs = {
            "English": {
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

        # 3. ComfyUI Root Detection
        comfy_root = Path(folder_paths.base_path)
        models_root = comfy_root / "models"
        
        if not w_path or not w_path.exists():
            return (f"{T['err_path']}{workflows_path}",)

        # 4. Logic
        workflows_found = list(w_path.rglob("*.json"))
        if not workflows_found:
            return (f"{T['err_no_json']}{workflows_path}",)

        report = []
        report.append(T['analyzing'].format(count=len(workflows_found), path=w_path))
        
        files_to_copy = {} # {source_path: category}
        
        # Categories Map
        CATEGORIES_MAP = {
            'checkpoints': ['ckpt', 'checkpoint', 'model_name', 'load_checkpoint'],
            'loras': ['lora'],
            'vae': ['vae'],
            'controlnet': ['control', 'controlnet'],
            'upscale_models': ['upscale', 'esrgan', 'realesrgan'],
            'clip_vision': ['clip_vision'],
            'embeddings': ['embedding'],
            'ipadapter': ['ipadapter'],
            'unet': ['unet'],
            'clip': ['clip']
        }

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
                            ruta_real = self.buscar_archivo(models_root, val)
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
                except:
                    return (f"{T['err_dest'].format(path=dest_path)}",)
            
            # 1. Backup Workflows
            wf_dest = dest_path / "workflows_backup"
            wf_dest.mkdir(exist_ok=True)
            for wf in workflows_found:
                try:
                    shutil.copy2(wf, wf_dest)
                except: pass
            
            # 2. Backup Models (WITH PROGRESS BAR)
            copied_count = 0
            
            # Initialize progress bar
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
                    
                    # Update progress bar
                    pbar.update(1)
                    
                except Exception as e:
                    print(T['err_copy'].format(src=src, error=str(e)))
            
            report.append(T['done'].format(count=copied_count))
            report.append(T['location'].format(path=dest_path))
        
        else:
            report.append(T['analysis_mode'])

        return ("\n".join(report),)

    def buscar_archivo(self, root_path, filename):
        possible_path = root_path / filename
        if possible_path.exists(): return str(possible_path)
        
        clean_name = Path(filename).name
        for file in root_path.rglob(clean_name):
            return str(file)
        return None
