import sys
import runpy
from pathlib import Path

# Add src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if __name__ == "__main__":
    print(f"🚀 Launching Fuguang (IDE Mode)...")
    # Run the module as __main__, which triggers the if __name__ == "__main__": block in ide.py
    try:
        runpy.run_module("fuguang.ide", run_name="__main__")
    except ImportError as e:
        print(f"❌ Startup Error: {e}")
        print("Please check if 'src/fuguang/ide.py' exists.")
