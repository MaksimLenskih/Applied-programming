"""Точка входа: python main.py; пути можно переопределить аргументами."""

import argparse
import json
from pathlib import Path

from calc import discipline_statistics, select_attempts, summarize
from data_io import (
    load_grades, load_plan, load_rules, load_students, log_issue,
)
from report import print_summary, save_chart, save_reports


def parse_args():
    """Разобрать пути; значения по умолчанию относятся к папке main.py."""
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Журнал успеваемости группы")
    for name, extension in [("students", "csv"), ("plan", "csv"),
                            ("grades", "csv"), ("rules", "json")]:
        parser.add_argument(f"--{name}", type=Path,
                            default=base / f"{name}.{extension}")
    parser.add_argument("--output", type=Path, default=base / "results",
                        help="папка отчётов и errors.log")
    return parser, parser.parse_args()


def main():
    """Прочитать данные, рассчитать итоги и сохранить все результаты."""
    parser, args = parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=True)
        with (args.output / "errors.log").open("w", encoding="utf-8") as log:
            rules = load_rules(args.rules)
            plan = load_plan(args.plan, log)
            students = load_students(args.students, log)
            attempts = load_grades(args.grades, students, plan, rules, log)
            results = select_attempts(attempts, rules, log)
            rows = summarize(students, results, plan, rules)
            for row in rows:
                for name, reason in row["debts"].items():
                    if reason == "нет допустимого результата":
                        log_issue(log, "план/ведомость", "—", row["student_id"],
                                  name, "нет", reason, "учтена задолженность")
        stats = discipline_statistics(students, results, plan, rules)
        save_reports(rows, args.output)
        print_summary(rows, stats)
        save_chart(stats, args.output / "average_grades.png")
        print(f"\nРезультаты: {args.output.resolve()}")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"Ошибка входных файлов или записи результата: {error}\n")


if __name__ == "__main__":
    main()
