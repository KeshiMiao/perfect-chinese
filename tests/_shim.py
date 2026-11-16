"""让测试能以包的形式导入插件，而不执行 __init__.py（不依赖 bpy）。"""

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent.parent

package = types.ModuleType("perfect_chinese")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("perfect_chinese", package)
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
