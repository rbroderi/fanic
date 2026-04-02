from datetime import datetime
from pathlib import Path


def resolve_log_path(template: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved = template.replace("%TIMESTAMP%", timestamp).strip()
    value = resolved if resolved else f"logs/{timestamp}.log"
    path = Path(value).expanduser().resolve()
    if path.suffix:
        return path
    return path.with_suffix(".log")
