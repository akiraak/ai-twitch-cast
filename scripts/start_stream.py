"""配信を開始するスクリプト"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from src.obs_controller import OBSController

load_dotenv()

with OBSController() as obs_ctrl:
    obs_ctrl.start_stream()
