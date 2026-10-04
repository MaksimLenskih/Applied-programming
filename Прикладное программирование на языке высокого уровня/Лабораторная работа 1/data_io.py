"""Чтение справочников и нормализация ведомости."""

import csv
import json
from datetime import datetime
from pathlib import Path


def clean(value):
    """Убрать крайние и повторяющиеся пробельные символы."""
    return " ".join(value.split())


def log_issue(log, source, line, student, discipline, value, reason, action):
    """Записать контекст, исходное значение, причину и действие."""
    log.write(
        f"{source}:{line} | студент={student!r} | "
        f"дисциплина={discipline!r} | исходное={value!r} | "
        f"причина={reason} | действие={action}\n"
    )


def read_rows(path, fields, log):
    """Прочитать CSV, пропуская строки с неправильным числом полей."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=";")
        header = next(reader, [])
        if [clean(item).casefold() for item in header] != fields:
            raise ValueError(f"{path}: ожидается заголовок {';'.join(fields)}")
        try:
            for values in reader:
                line = reader.line_num
                if len(values) != len(fields):
                    log_issue(log, path, line, "?", "?", values,
                              "неверное число полей", "строка отброшена")
                    continue
                row = dict(zip(fields, values))
                for field, original in row.items():
                    normalized = clean(original)
                    if original != normalized:
                        log_issue(
                            log, path, line, row.get("student_id", "?"),
                            row.get("discipline", "?"), original,
                            f"пробелы в поле {field}", repr(normalized),
                        )
                    row[field] = normalized
                yield line, row
        except csv.Error as error:
            log_issue(log, path, reader.line_num, "?", "?", "",
                      str(error), "чтение оставшейся части файла прекращено")


def load_rules(path):
    """Загрузить правила и проверить обязательные поля и типы."""
    with Path(path).open(encoding="utf-8-sig") as stream:
        rules = json.load(stream)
    required = {
        "grade_aliases", "credit_aliases", "valid_grades", "credit_values",
        "absent_mark", "last_attempt_counts", "stipend", "eligible_funding",
    }
    if not isinstance(rules, dict) or not required <= rules.keys():
        raise ValueError("rules.json: отсутствуют обязательные поля")
    grades = rules["valid_grades"]
    credits = rules["credit_values"]
    if (not isinstance(grades, list) or not grades
            or any(type(value) is not int for value in grades)):
        raise ValueError("valid_grades: нужен непустой список целых чисел")
    if (not isinstance(credits, list) or len(credits) != 2
            or any(not isinstance(value, str) or not clean(value)
                   for value in credits)):
        raise ValueError("credit_values: нужны две текстовые отметки")
    rules["credit_values"] = [clean(value).casefold() for value in credits]
    if len(set(rules["credit_values"])) != 2:
        raise ValueError("credit_values: отметки должны различаться")
    for name, values in [("grade_aliases", grades),
                         ("credit_aliases", rules["credit_values"])]:
        aliases = rules[name]
        if not isinstance(aliases, dict):
            raise ValueError(f"{name}: нужен словарь")
        result = {}
        for alias, value in aliases.items():
            if name == "credit_aliases" and isinstance(value, str):
                value = clean(value).casefold()
            if value not in values:
                raise ValueError(f"{name}: недопустимое значение {value!r}")
            result[clean(alias).casefold()] = value
        rules[name] = result
    for name in ["absent_mark", "eligible_funding"]:
        if not isinstance(rules[name], str) or not clean(rules[name]):
            raise ValueError(f"{name}: нужна непустая строка")
        rules[name] = clean(rules[name]).casefold()
    if type(rules["last_attempt_counts"]) is not bool:
        raise ValueError("last_attempt_counts: нужно true или false")
    if not isinstance(rules["stipend"], dict):
        raise ValueError("stipend: нужен словарь")
    for level in ["academic", "increased"]:
        policy = rules["stipend"].get(level, {})
        if (not isinstance(policy, dict)
                or policy.get("min_grade") not in grades
                or type(policy.get("amount")) not in (int, float)
                or policy["amount"] < 0):
            raise ValueError(f"stipend.{level}: некорректный порог или сумма")
    if (rules["stipend"]["academic"]["min_grade"]
            > rules["stipend"]["increased"]["min_grade"]):
        raise ValueError("Порог повышенной ниже порога академической")
    return rules


def load_plan(path, log):
    """Прочитать план; при повторе дисциплины сохранить первую строку."""
    plan = {}
    known = set()
    for line, row in read_rows(path, ["discipline", "type"], log):
        name = row["discipline"]
        kind = row["type"].casefold()
        if kind != row["type"]:
            log_issue(log, path, line, "?", name, row["type"],
                      "регистр типа", kind)
        if not name or kind not in ("экзамен", "зачёт"):
            log_issue(log, path, line, "?", name, row,
                      "пустая дисциплина или неизвестный тип", "отброшено")
        elif name.casefold() in known:
            log_issue(log, path, line, "?", name, row,
                      "повтор дисциплины", "сохранена первая запись")
        else:
            plan[name] = kind
            known.add(name.casefold())
    return plan


def load_students(path, log):
    """Прочитать студентов; ID сравнивать без учёта регистра."""
    students = {}
    fields = ["student_id", "fio", "group", "funding"]
    for line, row in read_rows(path, fields, log):
        sid = row["student_id"].casefold()
        for field in ["student_id", "funding"]:
            lowered = row[field].casefold()
            if lowered != row[field] and field == "funding":
                log_issue(log, path, line, sid, "?", row[field],
                          f"регистр поля {field}", lowered)
                row[field] = lowered
        if any(not row[field] for field in fields):
            log_issue(log, path, line, sid, "?", row,
                      "пустое обязательное поле", "студент отброшен")
        elif sid in students:
            log_issue(log, path, line, sid, "?", row,
                      "повтор student_id", "сохранена первая запись")
        else:
            students[sid] = row
    return students


def normalize_grade(raw, kind, rules):
    """Вернуть нормализованный результат или None для недопустимого."""
    value = clean(raw).casefold()
    if value == rules["absent_mark"]:
        return value
    if kind == "экзамен":
        if value in rules["grade_aliases"]:
            value = rules["grade_aliases"][value]
        elif value in {str(grade) for grade in rules["valid_grades"]}:
            value = int(value)
        else:
            return None
        return value if value in rules["valid_grades"] else None
    value = rules["credit_aliases"].get(value, value)
    return value if value in rules["credit_values"] else None


def load_grades(path, students, plan, rules, log):
    """Отбросить неверные строки; сохранить все допустимые попытки."""
    attempts = []
    disciplines = {name.casefold(): name for name in plan}
    fields = ["student_id", "discipline", "date", "grade"]
    for line, row in read_rows(path, fields, log):
        sid = row["student_id"].casefold()
        discipline = disciplines.get(row["discipline"].casefold())
        if sid not in students or discipline is None:
            log_issue(log, path, line, row["student_id"], row["discipline"],
                      row, "неизвестный студент или дисциплина", "отброшено")
            continue
        label = f"{students[sid]['student_id']} ({students[sid]['fio']})"
        for field, canonical in [
            ("student_id", students[sid]["student_id"]),
            ("discipline", discipline),
        ]:
            if row[field] != canonical:
                log_issue(log, path, line, label, discipline, row[field],
                          f"регистр поля {field}", canonical)
        try:
            date = datetime.strptime(row["date"], "%Y-%m-%d").date()
            if date.isoformat() != row["date"]:
                raise ValueError("Ожидается YYYY-MM-DD")
        except ValueError:
            log_issue(log, path, line, label, discipline, row["date"],
                      "некорректная дата: нужен YYYY-MM-DD", "отброшено")
            continue
        grade = normalize_grade(row["grade"], plan[discipline], rules)
        if grade is None:
            log_issue(log, path, line, label, discipline, row["grade"],
                      "пустой, недопустимый результат или неверный тип",
                      "отброшено")
            continue
        if row["grade"] != str(grade):
            log_issue(log, path, line, label, discipline, row["grade"],
                      "нормализация результата", repr(grade))
        attempts.append({"student_id": sid, "discipline": discipline,
                         "date": date, "grade": grade, "line": line})
    return attempts
