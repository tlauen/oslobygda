"""Kompatibel backup-inngang med .env-oppsett, utan shell-evaluering."""

import os
from pathlib import Path
import sys
from dotenv import load_dotenv
from backup import main

if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent / ".env")
    if "--directory" not in sys.argv and os.environ.get("BACKUP_DIR"):
        sys.argv.extend(["--directory", os.environ["BACKUP_DIR"]])
    main()
