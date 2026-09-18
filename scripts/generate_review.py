import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from nexusmind.core.review import generate_weekly_review

if __name__ == "__main__":
    res = generate_weekly_review()
    print(f"📊 Weekly Review generated: {res['path']} (Processed {res['logged_tasks_count']} log entries)")
