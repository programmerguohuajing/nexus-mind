import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from nexusmind.core.indexer import rebuild_all_indices, find_broken_links, find_orphans

if __name__ == "__main__":
    print("🌐 Updating Hierarchical Index Tree...")
    res = rebuild_all_indices()
    print("Master Index Path:", res["master_index"])
    print("Sub Indices:", res["sub_indices"])
    bl = find_broken_links()
    orph = find_orphans()
    print(f"Broken Links: {bl['total_broken']}, Orphan Cards: {orph['total_orphans']}")
