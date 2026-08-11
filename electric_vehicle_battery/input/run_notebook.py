#!/usr/bin/env python3
"""
Jupyter 없이 .ipynb 코드셀을 순서대로 실행하는 러너.

KISTI Neuron 로그인 노드에는 jupyter/nbformat이 없어서, 노트북을 헤드리스로
돌리려면 이게 필요하다. 셀을 순서대로 exec 하므로 노트북과 동일한 결과를 낸다.
(마지막 표현식 자동 출력까지 흉내낸다.)

사용법:
    python3 run_notebook.py build_fds_input.ipynb
    python3 run_notebook.py build_fds_input.ipynb --upto 12
"""
import argparse
import ast
import json
import sys
import traceback
from pathlib import Path
from typing import Optional


def run(nb_path: Path, upto: Optional[int] = None) -> int:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    g = {"__name__": "__main__", "__file__": str(nb_path)}
    n = 0
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        n += 1
        if upto is not None and n > upto:
            break
        src = "".join(cell["source"])
        if not src.strip():
            continue
        print(f"\n{'─'*72}\n[cell {n}]\n{'─'*72}")
        try:
            block = ast.parse(src, mode="exec")
            # 마지막 문장이 표현식이면 노트북처럼 값을 출력한다.
            if block.body and isinstance(block.body[-1], ast.Expr):
                last = ast.Expression(block.body.pop().value)
                exec(compile(block, str(nb_path), "exec"), g)
                val = eval(compile(last, str(nb_path), "eval"), g)
                if val is not None:
                    print(val)
            else:
                exec(compile(block, str(nb_path), "exec"), g)
        except Exception:
            traceback.print_exc()
            print(f"\n!! cell {n} 실패", file=sys.stderr)
            return 1
    print(f"\n{'─'*72}\n{n} code cells OK\n{'─'*72}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("notebook", type=Path)
    ap.add_argument("--upto", type=int, default=None, help="이 번호까지의 코드셀만 실행")
    a = ap.parse_args()
    sys.exit(run(a.notebook, a.upto))
