#!/usr/bin/env python3
"""
Pipeline de producao: vias + rodadas de captura + evidencias.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List


def run_cmd(args: List[str], cwd: Path) -> Dict:
    proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    return {
        "args": args,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--step", type=int, default=220)
    parser.add_argument("--radius", type=int, default=280)
    parser.add_argument("--sleep-ms", type=int, default=120)
    parser.add_argument("--stop-if-new-under", type=int, default=15)
    args = parser.parse_args()

    root = Path(".").resolve()
    out = root / "output"
    out.mkdir(parents=True, exist_ok=True)

    # Fase 1: vias via Overpass
    vias_res = run_cmd(["python", "extrair_vias_urbanova.py"], cwd=root)
    if vias_res["exit_code"] != 0:
        print("Falhou ao extrair logradouros via Overpass.")
        print(vias_res["stderr"] or vias_res["stdout"])
        raise SystemExit(1)

    history = []
    last_total = 0

    # Fase 2: rodadas de captura com saturacao
    for i in range(1, args.passes + 1):
        res = run_cmd(
            [
                "python",
                "coletar_empresas_urbanova.py",
                "--api-key",
                args.api_key,
                "--roads-file",
                "output/vias_urbanova.csv",
                "--step",
                str(args.step),
                "--radius",
                str(args.radius),
                "--sleep-ms",
                str(args.sleep_ms),
            ],
            cwd=root,
        )
        if res["exit_code"] != 0:
            print("Falhou durante captura de empresas.")
            print(res["stderr"] or res["stdout"])
            raise SystemExit(1)

        summary = read_json(out / "resumo_execucao.json")
        total = int(summary.get("total_unique_places", 0))
        new_items = max(0, total - last_total)
        last_total = total
        item = {"pass": i, "total": total, "new_items": new_items, "summary": summary}
        history.append(item)

        if i > 1 and new_items < args.stop_if_new_under:
            break
        time.sleep(0.4)

    # Fase 3: evidencias finais
    evidence = {
        "timestamp_unix": int(time.time()),
        "passes_executed": len(history),
        "history": history,
        "rule_stop": f"parar quando novos por rodada < {args.stop_if_new_under}",
        "outputs": {
            "vias": "output/vias_urbanova.csv",
            "empresas_ampla": "output/empresas_urbanova.csv",
            "empresas_filtrada": "output/empresas_urbanova_filtrada.csv",
            "resumo": "output/resumo_execucao.json",
            "cobertura_por_via": "output/cobertura_por_via.json",
        },
    }
    (out / "evidencias_pipeline_full.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

