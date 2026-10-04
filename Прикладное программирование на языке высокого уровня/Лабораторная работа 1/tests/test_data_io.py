"""Нормализация и генератор на новых данных."""

from io import StringIO
from pathlib import Path

import pytest

from calc import select_attempts
from data_io import load_grades, load_rules, normalize_grade
from generator import DIRTY_TYPES, generate
from report import write_csv


@pytest.fixture
def rules():
    """Реальные правила нормализации."""
    return load_rules(Path(__file__).resolve().parents[1] / "rules.json")


@pytest.mark.parametrize("raw,kind,expected", [
    (" Отл ", "экзамен", 5), (" 4 ", "экзамен", 4),
    ("НЕЗАЧЕТ", "зачёт", "незачёт"), ("Зачёт", "зачёт", "зачёт"),
    ("Н/Я", "экзамен", "н/я"), ("", "экзамен", None),
    ("6", "экзамен", None), ("4+", "экзамен", None),
    ("зачёт", "экзамен", None), ("5", "зачёт", None),
])
def test_normalization(raw, kind, expected, rules):
    """Все виды исходных опечаток и неверных типов результатов."""
    assert normalize_grade(raw, kind, rules) == expected


def test_bad_rows_and_late_invalid(tmp_path, rules):
    """Ошибочные строки не прерывают чтение; поздняя неверная не стирает оценку."""
    path = tmp_path / "grades.csv"
    path.write_text(
        "student_id;discipline;date;grade\n"
        " x1 ; PYTHON ;2026-01-01; Отл \n"
        "x1;Python;2026-02-01;6\n"
        "unknown;Python;2026-01-01;5\n"
        "x1;unknown;2026-01-01;5\n"
        "x1;Python;не дата;5\n"
        "x1;Python;2026-02-02;4;лишнее\n"
        "x1;Python\n"
        "x1;Язык;2026-01-01;ЗАЧЕТ\n",
        encoding="utf-8-sig",
    )
    students = {"x1": {"student_id": "X1", "fio": "Новый Студент"}}
    plan = {"Python": "экзамен", "Язык": "зачёт"}
    log = StringIO()
    attempts = load_grades(path, students, plan, rules, log)
    assert select_attempts(attempts, rules) == {
        ("x1", "Python"): 5, ("x1", "Язык"): "зачёт",
    }
    for phrase in ["неизвестный", "некорректная дата", "число полей",
                   "нормализация", "регистр", "пробелы", "недопустимый"]:
        assert phrase in log.getvalue()


def test_generator_reproducible(tmp_path, rules):
    """Воспроизводимость, все типы загрязнений и другая группа."""
    plan = {"Новый экзамен": "экзамен", "Новый зачёт": "зачёт"}
    assert generate(7, 0.4, plan, rules, 1) == generate(7, 0.4, plan, rules, 1)
    for mode in DIRTY_TYPES:
        students, rows = generate(7, 1, plan, rules, 2, [mode])
        assert len(students) == 7
        path = tmp_path / "grades.csv"
        write_csv(path, ["student_id", "discipline", "date", "grade"], rows)
        mapping = {row["student_id"].casefold(): row for row in students}
        assert isinstance(load_grades(path, mapping, plan, rules, StringIO()), list)
    students, rows = generate(7, 0, plan, rules)
    assert len(rows) == 14
    with pytest.raises(ValueError):
        generate(0, 0.1, plan, rules)
    with pytest.raises(ValueError):
        generate(7, 1.1, plan, rules)
