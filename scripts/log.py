#!/usr/bin/env python3
"""library-tracker 数据读写脚本。

所有对阅读记录 JSON 文件的增删改查都经由本脚本完成，
SKILL.md 中禁止 AI 直接读写 JSON 文件，避免字段错误、覆盖、幻觉等问题。

用法:
  python log.py --action add    --title "百年孤独" [--author "加西亚·马尔克斯"] [--total 417]
  python log.py --action update --title "百年孤独" [--current 100] [--status finished]
  python log.py --action remove --title "百年孤独"
  python log.py --action list   [--status reading|finished] [--sort title|last_update|start_date]
  python log.py --action query  --title "百年孤独"
  python log.py --action stats

数据文件默认位于当前用户主目录下的 ~/library_reading_log.json，
可用环境变量 LIBRARY_LOG_FILE 覆盖。
"""

import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

# 数据文件路径：优先环境变量，其次 HOME 目录
DEFAULT_PATH = os.path.join(str(Path.home()), "library_reading_log.json")
DATA_FILE = os.environ.get("LIBRARY_LOG_FILE", DEFAULT_PATH)


# ---------------------------------------------------------------- 基础读写
def load_records() -> list:
    """读取记录列表；文件不存在或为空时返回空列表。"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        print(f"错误：无法解析数据文件 {DATA_FILE}: {e}", file=sys.stderr)
        sys.exit(2)


def save_records(records: list) -> None:
    """写入记录列表，自动创建父目录。"""
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def find_record(records: list, title: str) -> (int, dict):
    """按书名查找记录，返回 (index, record) 或 (None, None)。书名精确匹配。"""
    key = title.strip()
    for i, rec in enumerate(records):
        if rec.get("title", "").strip() == key:
            return i, rec
    return None, None


def today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------- 各动作
def cmd_add(args) -> int:
    records = load_records()
    idx, _ = find_record(records, args.title)
    if idx is not None:
        print(f"已存在《{args.title}》，如需更新时间请使用 update，或先 remove 再 add。")
        return 1

    rec = {
        "id": uuid.uuid4().hex[:12],
        "title": args.title.strip(),
        "author": (args.author or "").strip(),
        "total_pages": args.total,
        "current_page": args.current if args.current is not None else 0,
        "status": "reading",
        "start_date": today(),
        "last_update": today(),
        "finished_date": None,
    }
    records.append(rec)
    save_records(records)
    print(f"已添加《{rec['title']}》，当前进度第 {rec['current_page']} 页。")
    return 0


def cmd_update(args) -> int:
    records = load_records()
    idx, rec = find_record(records, args.title)
    if idx is None:
        print(f"找不到《{args.title}》，请先 add。")
        return 1

    changed = []
    if args.current is not None:
        # 简单向前校验：进度不能为负
        if args.current < 0:
            print("错误：current 不能为负数。", file=sys.stderr)
            return 1
        rec["current_page"] = args.current
        changed.append(f"进度更新至第 {args.current} 页")

    if args.status == "finished":
        rec["status"] = "finished"
        rec["finished_date"] = today()
        if rec["total_pages"] and args.current is not None and args.current >= rec["total_pages"]:
            rec["current_page"] = rec["total_pages"]
        changed.append("标记为已读完")
    elif args.status == "reading":
        rec["status"] = "reading"
        rec["finished_date"] = None
        changed.append("标记为在读")

    if args.author is not None:
        rec["author"] = args.author.strip()
        changed.append(f"作者改为 {rec['author']}")

    if args.total is not None:
        rec["total_pages"] = args.total
        changed.append(f"总页数改为 {rec['total_pages']}")

    rec["last_update"] = today()
    save_records(records)
    print(f"已更新《{rec['title']}》：" + ("；".join(changed) if changed else "无变更"))
    return 0


def cmd_remove(args) -> int:
    records = load_records()
    idx, rec = find_record(records, args.title)
    if idx is None:
        print(f"找不到《{args.title}》。")
        return 1
    removed = records.pop(idx)
    save_records(records)
    print(f"已删除《{removed['title']}》。")
    return 0


def cmd_list(args) -> int:
    records = load_records()
    if args.status:
        status = args.status
        if status not in ("reading", "finished"):
            print("错误：--status 只能为 reading 或 finished。", file=sys.stderr)
            return 1
        records = [r for r in records if r.get("status") == status]

    sort_key = args.sort or "last_update"
    if sort_key not in ("title", "last_update", "start_date"):
        print("错误：--sort 只能为 title、last_update 或 start_date。", file=sys.stderr)
        return 1
    records = sorted(records, key=lambda r: str(r.get(sort_key, "")), reverse=(sort_key != "title"))

    if not records:
        print("（暂无记录）")
        return 0

    print(f"共 {len(records)} 条记录：")
    for r in records:
        status = "在读" if r.get("status") == "reading" else "已读完"
        progress = f"{r.get('current_page', 0)}/{r.get('total_pages') or '?'}"
        print(f"- 《{r.get('title')}》 {status} 进度 {progress} 页（更新于 {r.get('last_update')}）")
    return 0


def cmd_query(args) -> int:
    records = load_records()
    idx, rec = find_record(records, args.title)
    if idx is None:
        print(f"找不到《{args.title}》。可用 list 查看全部记录。")
        return 1
    status = "在读" if rec.get("status") == "reading" else "已读完"
    progress = f"{rec.get('current_page', 0)}/{rec.get('total_pages') or '?'}"
    print(f"《{rec.get('title')}》 {status}，进度第 {progress} 页。")
    if rec.get("author"):
        print(f"作者：{rec.get('author')}")
    print(f"开始日期：{rec.get('start_date')}｜最近更新：{rec.get('last_update')}")
    if rec.get("finished_date"):
        print(f"完成日期：{rec.get('finished_date')}")
    return 0


def cmd_stats(args) -> int:
    records = load_records()
    total = len(records)
    reading = len([r for r in records if r.get("status") == "reading"])
    finished = len([r for r in records if r.get("status") == "finished"])
    print(f"共 {total} 本书，在读 {reading} 本，已读完 {finished} 本。")
    return 0


# ---------------------------------------------------------------- 入口
def main() -> int:
    parser = argparse.ArgumentParser(description="图书馆纸质书阅读记录管理")
    parser.add_argument("--action", required=True,
                        choices=["add", "update", "remove", "list", "query", "stats"],
                        help="要执行的动作")
    parser.add_argument("--title", help="书名")
    parser.add_argument("--author", help="作者")
    parser.add_argument("--total", type=int, help="总页数")
    parser.add_argument("--current", type=int, help="当前页码")
    parser.add_argument("--status", choices=["reading", "finished"], help="状态")
    parser.add_argument("--sort", help="list 排序字段")
    args = parser.parse_args()

    if args.action in ("add", "update", "remove", "query") and not args.title:
        print("错误：该动作需要 --title 参数。", file=sys.stderr)
        return 1

    handlers = {
        "add": cmd_add,
        "update": cmd_update,
        "remove": cmd_remove,
        "list": cmd_list,
        "query": cmd_query,
        "stats": cmd_stats,
    }
    return handlers[args.action](args)


if __name__ == "__main__":
    sys.exit(main())
