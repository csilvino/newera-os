"""Quick benchmark & live verification of Qwen 2.5 3B CUDA + Newera OS Skills on RTX 3060."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("NEWERA_LLM_URL", "http://127.0.0.1:11434/v1")
os.environ.setdefault("NEWERA_LLM_MODEL", "qwen2.5:3b")

from kernel.continuum_udp_bridge import process_intent

t0 = time.perf_counter()
r1 = process_intent("Explique em 2 frases o que e um microkernel.")
t1 = time.perf_counter()
r2 = process_intent("Lembre na minha memoria que preciso revisar o projeto Newera amanha as 14h")
t2 = time.perf_counter()
r3 = process_intent("Abra o monitor de rede e hardware do sistema")
t3 = time.perf_counter()

print(f"=== 1. CHAT ({t1 - t0:.2f}s) ===\n{r1}\n")
print(f"=== 2. SKILL save_memory ({t2 - t1:.2f}s) ===\n{r2}\n")
print(f"=== 3. SKILL open_surface ({t3 - t2:.2f}s) ===\n{r3}\n")
