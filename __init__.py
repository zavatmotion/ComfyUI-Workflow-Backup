from .nodes import WorkflowBackupNode

NODE_CLASS_MAPPINGS = {
    "WorkflowBackup": WorkflowBackupNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WorkflowBackup": "📦 ComfyUI Backup & Packager"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']