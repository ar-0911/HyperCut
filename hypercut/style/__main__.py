"""Manual run: python -m hypercut.style ["style prompt"]"""

import sys

from hypercut.style import style_from_prompt

print(style_from_prompt(" ".join(sys.argv[1:])).model_dump_json(indent=2))
