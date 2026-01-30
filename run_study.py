import sys
import runpy
from pathlib import Path

# Add src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

if __name__ == "__main__":
    print(f"🧪 Launching Fuguang (Study Mode)...")
    try:
        # Run the study module
        runpy.run_module("fuguang.fuguang_study", run_name="__main__")
    except ImportError as e:
        print(f"❌ Startup Error: {e}")
    except Exception as e:
        print(f"❌ Runtime Error: {e}")
