#!/usr/bin/env python3
"""
CRUD simples das buscas do Google Maps (config/buscas_urbanova.json).

  python3 gerenciar_buscas.py init
  python3 gerenciar_buscas.py list
  python3 gerenciar_buscas.py add "chaveiro" "serralheria"
  python3 gerenciar_buscas.py remove "termo antigo"
  python3 gerenciar_buscas.py set-bairro "Urbanova"
  python3 gerenciar_buscas.py set-cidade "São José dos Campos"
  python3 gerenciar_buscas.py amplas on
  python3 gerenciar_buscas.py menu   # modo interativo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from urbanova_buscas_defaults import estado_inicial_dict


def default_config_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "buscas_urbanova.json"


def load_cfg(path: Path) -> Dict[str, Any]:
    if not path.exists():
        print(f"Arquivo não existe: {path}", file=sys.stderr)
        print("Execute: python3 gerenciar_buscas.py init", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def save_cfg(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    path: Path = args.config
    if path.exists() and not args.force:
        print(f"Já existe: {path} (use --force para sobrescrever)", file=sys.stderr)
        return 1
    save_cfg(path, estado_inicial_dict())
    print(f"OK: criado {path}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    data = load_cfg(args.config)
    segs: List[str] = data.get("segmentos", [])
    print(f"bairro: {data.get('bairro')}")
    print(f"cidade: {data.get('cidade')}")
    print(f"buscas amplas (empresas/comércio/serviços/lojas): {data.get('incluir_buscas_amplas', True)}")
    print(f"total de segmentos: {len(segs)}")
    for i, s in enumerate(segs, 1):
        print(f"  {i:3}. {s}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    data = load_cfg(args.config)
    segs: List[str] = list(data.get("segmentos", []))
    seen = {x.strip() for x in segs}
    for term in args.termos:
        t = term.strip()
        if not t:
            continue
        if t not in seen:
            segs.append(t)
            seen.add(t)
            print(f"+ adicionado: {t}")
        else:
            print(f"(já existe: {t})")
    data["segmentos"] = segs
    save_cfg(args.config, data)
    print(f"OK: {len(segs)} segmentos salvos em {args.config}")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    data = load_cfg(args.config)
    segs: List[str] = list(data.get("segmentos", []))
    drop = {t.strip() for t in args.termos}
    nova = [s for s in segs if s not in drop]
    rem = len(segs) - len(nova)
    data["segmentos"] = nova
    save_cfg(args.config, data)
    print(f"OK: removidos {rem} itens; restam {len(nova)} segmentos")
    return 0


def cmd_set_bairro(args: argparse.Namespace) -> int:
    data = load_cfg(args.config)
    data["bairro"] = args.valor.strip()
    save_cfg(args.config, data)
    print(f"OK: bairro = {data['bairro']}")
    return 0


def cmd_set_cidade(args: argparse.Namespace) -> int:
    data = load_cfg(args.config)
    data["cidade"] = args.valor.strip()
    save_cfg(args.config, data)
    print(f"OK: cidade = {data['cidade']}")
    return 0


def cmd_amplas(args: argparse.Namespace) -> int:
    data = load_cfg(args.config)
    on = args.estado.lower() in ("on", "1", "true", "sim", "yes")
    data["incluir_buscas_amplas"] = on
    save_cfg(args.config, data)
    print(f"OK: buscas amplas = {on}")
    return 0


def cmd_menu(_args: argparse.Namespace) -> int:
    path = _args.config
    print("Gerenciador de buscas Urbanova (vazio = sair)\n")
    while True:
        print("  l=listar | a=adicionar | r=remover | b=bairro | c=cidade | x=amplas | q=sair")
        try:
            op = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if op in ("q", "", "quit", "sair"):
            return 0
        if op == "l":
            _args_m = argparse.Namespace(config=path)
            cmd_list(_args_m)
        elif op == "a":
            line = input("termos (separados por vírgula): ").strip()
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if parts:
                cmd_add(argparse.Namespace(config=path, termos=parts))
        elif op == "r":
            line = input("remover (separados por vírgula): ").strip()
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if parts:
                cmd_remove(argparse.Namespace(config=path, termos=parts))
        elif op == "b":
            v = input("bairro: ").strip()
            if v:
                cmd_set_bairro(argparse.Namespace(config=path, valor=v))
        elif op == "c":
            v = input("cidade: ").strip()
            if v:
                cmd_set_cidade(argparse.Namespace(config=path, valor=v))
        elif op == "x":
            v = input("amplas on/off: ").strip().lower()
            if v:
                cmd_amplas(argparse.Namespace(config=path, estado=v))
        else:
            print("Opção inválida.")


def main() -> int:
    parser = argparse.ArgumentParser(description="CRUD de config/buscas_urbanova.json")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Caminho do JSON de buscas",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Cria JSON com segmentos padrão")
    p_init.add_argument("--force", action="store_true", help="Sobrescrever se existir")
    p_init.set_defaults(func=cmd_init)

    p_list = sub.add_parser("list", help="Lista segmentos e metadados")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="Adiciona um ou mais segmentos")
    p_add.add_argument("termos", nargs="+", help="Termos de busca (ex.: padaria confeitaria)")
    p_add.set_defaults(func=cmd_add)

    p_rm = sub.add_parser("remove", help="Remove segmentos exatos")
    p_rm.add_argument("termos", nargs="+")
    p_rm.set_defaults(func=cmd_remove)

    p_sb = sub.add_parser("set-bairro", help="Define bairro")
    p_sb.add_argument("valor")
    p_sb.set_defaults(func=cmd_set_bairro)

    p_sc = sub.add_parser("set-cidade", help="Define cidade")
    p_sc.add_argument("valor")
    p_sc.set_defaults(func=cmd_set_cidade)

    p_am = sub.add_parser("amplas", help="Liga/desliga buscas amplas (empresas/comércio/...)")
    p_am.add_argument("estado", help="on ou off")
    p_am.set_defaults(func=cmd_amplas)

    p_menu = sub.add_parser("menu", help="Menu interativo simples")
    p_menu.set_defaults(func=cmd_menu)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
