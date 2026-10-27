"""Package only the extension build directory, with deterministic relative paths."""
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(sys.argv[1])
with ZipFile(sys.argv[2], "w", ZIP_DEFLATED) as archive:
    for path in sorted(root.iterdir()):
        if path.is_file():
            archive.write(path, path.name)
