from pathlib import Path
import os
import sys

cli = Path(__file__).resolve().parents[1] / "df-fintechterm"
os.execv(cli, [str(cli), *sys.argv[1:]])
