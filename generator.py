"""Генератор: собственный план и правила задаются входными файлами."""

import argparse
import copy
import json
import random
from datetime import date, timedelta
from pathlib import Path

from data_io import load_plan, load_rules
from report import write_csv

DIRTY_TYPES = ["alias", "spaces", "case", "invalid", "empty", "duplicate",
               "retake", "absent", "wrong_type", "unknown_student",
               "unknown_discipline", "bad_date", "missing"]


def corrupt(row, kind, mode, rules, rng):
    """Применить один выбранный вид загрязнения к базовой записи."""
    row = row.copy()
    grade = row["grade"]
    if mode == "alias":
        aliases = (rules["grade_aliases"] if kind == "экзамен"
                   else rules["credit_aliases"])
        matches = [key for key, value in aliases.items() if value == grade]
        row["grade"] = rng.choice(matches) if matches else f" {grade} "
    elif mode == "spaces":
        row["grade"] = f"  {grade}  "
        row["discipline"] = f" {row['discipline']} "
    elif mode == "case":
        row["discipline"] = row["discipline"].upper()
        row["grade"] = str(grade).upper()
    elif mode == "invalid":
        row["grade"] = max(rules["valid_grades"]) + 1
    elif mode == "empty":
        row["grade"] = ""
    elif mode == "absent":
        row["grade"] = rules["absent_mark"]
    elif mode == "wrong_type":
        row["grade"] = (rules["credit_values"][0] if kind == "экзамен"
                        else rng.choice(rules["valid_grades"]))
    elif mode == "unknown_student":
        row["student_id"] = "UNKNOWN"
    elif mode == "unknown_discipline":
        row["discipline"] = "Несуществующая дисциплина"
    elif mode == "bad_date":
        row["date"] = "не дата"
    elif mode == "missing":
        return []
    elif mode == "duplicate":
        return [row, row.copy()]
    elif mode == "retake":
        later = row.copy()
        later["date"] = (
            date.fromisoformat(row["date"]) + timedelta(days=35)
        ).isoformat()
        later["grade"] = (max(rules["valid_grades"]) if kind == "экзамен"
                          else rules["credit_values"][0])
        row["grade"] = (min(rules["valid_grades"]) if kind == "экзамен"
                        else rules["credit_values"][1])
        return [later, row]
    return [row]


def generate(count, error_rate, plan, rules, seed=42, error_types=None):
    """Загрязнить ровно round(N*доля) базовых строк, затем перемешать."""
    if count < 1 or not 0 <= error_rate <= 1 or not plan:
        raise ValueError("Нужны count >= 1, доля от 0 до 1 и непустой план")
    modes = error_types if error_types is not None else DIRTY_TYPES
    if not modes or any(mode not in DIRTY_TYPES for mode in modes):
        raise ValueError("Неизвестный или пустой список типов ошибок")
    rng = random.Random(seed)
    students, base_rows = [], []
    for number in range(1, count + 1):
        sid = f"G{number:04d}"
        students.append({"student_id": sid, "fio": f"Студент {number:04d}",
                         "group": "Тестовая группа",
                         "funding": (rules["eligible_funding"]
                                     if rng.random() < 0.8 else "иная форма")})
        for index, (name, kind) in enumerate(plan.items()):
            grade = rng.choice(rules["valid_grades"] if kind == "экзамен"
                               else rules["credit_values"])
            base_rows.append({"student_id": sid, "discipline": name,
                              "date": (date(2026, 1, 1)
                                       + timedelta(days=index)).isoformat(),
                              "grade": grade})
    chosen = set(rng.sample(range(len(base_rows)),
                           round(len(base_rows) * error_rate)))
    rows = []
    for index, row in enumerate(base_rows):
        if index in chosen:
            mode = rng.choice(modes)
            rows.extend(corrupt(row, plan[row["discipline"]], mode, rules, rng))
        else:
            rows.append(row)
    rng.shuffle(rows)
    return students, rows


def main():
    """Прочитать параметры и записать отдельный набор из четырёх файлов."""
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Генератор тестового журнала")
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--error-rate", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--error-types", nargs="+", choices=DIRTY_TYPES)
    parser.add_argument("--plan", type=Path, default=base / "plan.csv")
    parser.add_argument("--rules", type=Path, default=base / "rules.json")
    parser.add_argument("--output", type=Path, default=base / "generated")
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=True)
        targets = [(args.plan, args.output / "plan.csv"),
                   (args.rules, args.output / "rules.json")]
        if any(source.resolve() == target.resolve()
               for source, target in targets):
            raise ValueError("Папка генератора должна отличаться от исходной")
        rules = load_rules(args.rules)
        with (args.output / "generator.log").open("w", encoding="utf-8") as log:
            plan = load_plan(args.plan, log)
        students, grades = generate(args.count, args.error_rate, plan, rules,
                                    args.seed, args.error_types)
        write_csv(args.output / "students.csv",
                  ["student_id", "fio", "group", "funding"], students)
        write_csv(args.output / "grades.csv",
                  ["student_id", "discipline", "date", "grade"], grades)
        write_csv(args.output / "plan.csv", ["discipline", "type"],
                  [{"discipline": name, "type": kind}
                   for name, kind in plan.items()])
        with (args.output / "rules.json").open("w", encoding="utf-8") as stream:
            json.dump(copy.deepcopy(rules), stream, ensure_ascii=False, indent=2)
        print(f"Создано студентов: {len(students)}, строк: {len(grades)}; "
              f"набор: {args.output.resolve()}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Ошибка генерации: {error}\n")


if __name__ == "__main__":
    main()
