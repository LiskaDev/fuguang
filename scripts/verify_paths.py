import sys
from pathlib import Path

# Add src to path just like run.py does
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from fuguang import config
    print("✅ Successfully imported config")
except ImportError as e:
    print(f"❌ Failed to import config: {e}")
    sys.exit(1)

print(f"ROOT: {config.PROJECT_ROOT}")
print(f"DATA: {config.DATA_DIR}")
print(f"CONFIG: {config.CONFIG_DIR}")
print(f"MEMORY: {config.MEMORY_FILE}")
print(f"SYS_PROMPT: {config.SYSTEM_PROMPT_FILE}")

errors = []

if not config.DATA_DIR.exists():
    errors.append("Data dir missing")
if not config.CONFIG_DIR.exists():
    errors.append("Config dir missing")

if not config.MEMORY_FILE.exists():
    print(f"⚠️ Memory file not found at {config.MEMORY_FILE} (Migration might have failed or it didn't exist)")
else:
    print("✅ Memory file found")

if not config.SYSTEM_PROMPT_FILE.exists():
    errors.append(f"System prompt missing at {config.SYSTEM_PROMPT_FILE}")
else:
    print("✅ System prompt found")

if errors:
    print("❌ Verification Failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("🚀 Verification Passed!")
