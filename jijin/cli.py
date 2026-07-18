from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

# 保证以 python -m jijin 运行时能找到包
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from jijin.alert.position import run_alert
from jijin.config import cache_dir, load_config
from jijin.data.cache import CacheStore
from jijin.data.fund import fetch_index_fund_table
from jijin.data.valuation import fetch_watch_valuations
from jijin.screener.index_fund import screen_index_funds, to_display
from jijin.strategy.generator import generate_strategy

console = Console()


def _print_screen(df) -> None:
    if df is None or df.empty:
        console.print("[yellow]没有符合条件的基金，请放宽 config.yaml 中的 screen 条件。[/yellow]")
        return
    table = Table(title="指数基金筛选结果", show_lines=False)
    for col in df.columns:
        table.add_column(str(col))
    for _, row in df.iterrows():
        table.add_row(*[("" if v is None or (isinstance(v, float) and v != v) else str(v)) for v in row.tolist()])
    console.print(table)
    console.print(f"[dim]共 {len(df)} 条[/dim]")


def _print_alerts(advices) -> None:
    table = Table(title="估值加减仓提醒", show_lines=False)
    for col in ["指数", "状态", "百分位", "当前仓位%", "目标仓位%", "建议", "金额(元)"]:
        table.add_column(col)
    for a in advices:
        pct = f"{a.percentile:.1f}" if a.percentile is not None else "-"
        table.add_row(
            a.index,
            a.label,
            pct,
            f"{a.current_pct:.1f}",
            f"{a.target_pct:.1f}",
            a.action,
            f"{a.suggest_amount:,.0f}",
        )
    console.print(table)
    for a in advices:
        style = "red" if a.action == "增持" else ("green" if a.action == "减持" else "dim")
        console.print(f"[{style}]{a.message}[/{style}]")


def cmd_screen(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    console.print(f"[dim]配置: {cfg.get('_config_path')}[/dim]")
    console.print("[cyan]正在筛选指数基金…[/cyan]")
    df = screen_index_funds(cfg, force=args.refresh)
    _print_screen(to_display(df))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        to_display(df).to_csv(args.out, index=False, encoding="utf-8-sig")
        console.print(f"[green]已导出[/green] {args.out}")
    return 0


def cmd_alert(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    console.print(f"[dim]配置: {cfg.get('_config_path')}[/dim]")
    console.print("[cyan]正在计算估值与仓位建议…[/cyan]")
    advices = run_alert(cfg, force=args.refresh)
    _print_alerts(advices)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    rc = cmd_screen(args)
    console.print()
    rc2 = cmd_alert(args)
    return rc or rc2


def cmd_refresh(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = CacheStore(cache_dir(cfg) / "jijin_cache.db")
    n = store.clear()
    console.print(f"已清空缓存 {n} 条，开始重新拉取…")
    fetch_index_fund_table(cfg, force=True)
    fetch_watch_valuations(cfg, force=True)
    console.print("[green]刷新完成[/green]")
    return 0


def cmd_valuation(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    vals = fetch_watch_valuations(cfg, force=args.refresh)
    table = Table(title="指数估值快照")
    for c in ["指数", "匹配名", "日期", "PE", "PE百分位", "PB", "PB百分位"]:
        table.add_column(c)
    for v in vals:
        err = v.raw.get("error") if v.raw else None
        table.add_row(
            v.index_name,
            v.matched_name,
            v.date or ("错误" if err else "-"),
            f"{v.pe:.2f}" if v.pe is not None else "-",
            f"{v.pe_percentile:.1f}" if v.pe_percentile is not None else "-",
            f"{v.pb:.2f}" if v.pb is not None else "-",
            f"{v.pb_percentile:.1f}" if v.pb_percentile is not None else "-",
        )
        if err:
            console.print(f"[red]{v.index_name}: {err}[/red]")
    console.print(table)
    return 0


def cmd_strategy(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    plan = generate_strategy(
        risk=args.risk,
        template=args.template,
        total_assets=args.assets,
        monthly_dca=args.monthly,
        cfg=cfg,
        pick_funds=not args.no_funds,
    )
    console.print(f"[bold]{plan.name}[/bold]")
    console.print(plan.summary)
    table = Table(title="策略配置")
    for c in ["指数", "基准%", "目标%", "估值", "基金", "月定投"]:
        table.add_column(c)
    for s in plan.sleeves:
        table.add_row(
            s.index,
            f"{s.base_weight:.1f}",
            f"{s.target_weight:.1f}",
            s.valuation_label,
            f"{s.fund_code or '-'} {s.fund_name or ''}".strip(),
            f"{s.monthly_amount:,.0f}",
        )
    console.print(table)
    if args.out:
        Path(args.out).write_text(plan.to_markdown(), encoding="utf-8")
        console.print(f"[green]已导出[/green] {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jijin",
        description="个人指数基金选购与加减仓提醒工具",
    )
    p.add_argument("-c", "--config", default=None, help="配置文件路径，默认 config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    for name, help_text, fn in [
        ("screen", "按条件一键筛选指数基金", cmd_screen),
        ("alert", "根据估值提醒增持/减持比例", cmd_alert),
        ("run", "筛选 + 提醒", cmd_run),
        ("refresh", "清空并刷新本地缓存", cmd_refresh),
        ("valuation", "仅查看指数估值百分位", cmd_valuation),
    ]:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--refresh", action="store_true", help="忽略缓存强制刷新")
        if name in {"screen", "run"}:
            sp.add_argument("-o", "--out", help="筛选结果导出 CSV 路径")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("strategy", help="生成定投/仓位策略")
    sp.add_argument("--risk", default="均衡", choices=["稳健", "均衡", "积极"])
    sp.add_argument(
        "--template",
        default="valuation_dynamic",
        choices=[
            "valuation_dynamic",
            "core_satellite",
            "dividend_defense",
            "growth_barbell",
        ],
    )
    sp.add_argument("--assets", type=float, default=None, help="总资产（元）")
    sp.add_argument("--monthly", type=float, default=3000.0, help="月定投（元）")
    sp.add_argument("--no-funds", action="store_true", help="不自动匹配基金")
    sp.add_argument("-o", "--out", help="导出 Markdown 路径")
    sp.set_defaults(func=cmd_strategy)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        console.print("\n已取消")
        return 130
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]错误:[/red] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
