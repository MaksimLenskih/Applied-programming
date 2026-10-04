"""Проверки расчётов на маленьком учебном плане."""

import copy
from datetime import date
from io import StringIO
from pathlib import Path

import pytest

from calc import (
    average_grade, debts, discipline_statistics, recommendations,
    select_attempts, stipend,
)
from data_io import load_rules
from report import rating_key


@pytest.fixture
def rules():
    """Загрузить реальные правила без изменения исходного JSON."""
    return load_rules(Path(__file__).resolve().parents[1] / "rules.json")


@pytest.fixture
def plan():
    """Два экзамена и один зачёт."""
    return {"Алгебра": "экзамен", "Python": "экзамен", "Язык": "зачёт"}


@pytest.fixture
def student():
    """Один бюджетник."""
    return {"student_id": "X1", "fio": "Тестовый Студент", "funding": "бюджет"}


def results(a, b, credit="зачёт"):
    """Составить результаты, отсутствующие значения не добавлять."""
    return {("x1", name): grade for name, grade in
            [("Алгебра", a), ("Python", b), ("Язык", credit)]
            if grade is not None}


@pytest.mark.parametrize("a,b,expected", [(2, 5, 3.5), (4, 5, 4.5),
                                         ("н/я", 4, 4.0), (None, None, None)])
def test_average(a, b, expected, rules, plan):
    """Двойка входит в среднее, неявка и отсутствие не входят."""
    assert average_grade("x1", results(a, b), plan, rules) == expected


def test_debts(rules, plan):
    """Проверить двойку, незачёт, неявку и отсутствующую дисциплину."""
    assert set(debts("x1", results(2, "н/я", "незачёт"), plan, rules)) == set(plan)
    assert debts("x1", results(4, None), plan, rules) == {
        "Python": "нет допустимого результата",
    }
    assert not debts("x1", results(3, 5), plan, rules)


@pytest.mark.parametrize("a,b,credit,funding,label,amount", [
    (4, 5, "зачёт", "бюджет", "академическая", 3000),
    (5, 5, "зачёт", "бюджет", "повышенная", 6000),
    (3, 5, "зачёт", "бюджет", "нет", 0),
    (5, 5, None, "бюджет", "нет", 0),
    (5, 5, "зачёт", "контракт", "нет", 0),
])
def test_stipend(a, b, credit, funding, label, amount, student, plan, rules):
    """Оба уровня стипендии и три основания отказа."""
    student["funding"] = funding
    assert stipend(student, results(a, b, credit), plan, rules) == (label, amount)


def test_changed_rules(student, plan, rules):
    """Изменённые пороги, суммы и форма финансирования применяются."""
    changed = copy.deepcopy(rules)
    changed["stipend"]["academic"] = {"min_grade": 3, "amount": 1234}
    changed["stipend"]["increased"] = {"min_grade": 4, "amount": 4321}
    changed["eligible_funding"] = "контракт"
    student["funding"] = "контракт"
    assert stipend(student, results(3, 5), plan, changed) == ("академическая", 1234)
    assert stipend(student, results(4, 5), plan, changed) == ("повышенная", 4321)
    message = recommendations(student, results(3, 5), plan, changed)
    assert "Алгебра» на 4" in message and "Python" not in message


def test_attempts(rules):
    """Поздняя дата побеждает порядок строк; дубликат не добавляет оценку."""
    attempts = [
        {"student_id": "x1", "discipline": "Python", "date": date(2026, 2, 20),
         "grade": 3, "line": 2},
        {"student_id": "x1", "discipline": "Python", "date": date(2026, 1, 12),
         "grade": 2, "line": 3},
        {"student_id": "x1", "discipline": "Python", "date": date(2026, 2, 6),
         "grade": 5, "line": 4},
    ]
    attempts.append(attempts[0].copy())
    log = StringIO()
    assert select_attempts(attempts, rules, log) == {("x1", "Python"): 3}
    assert "дубликат" in log.getvalue()
    rules["last_attempt_counts"] = False
    assert select_attempts(attempts, rules) == {("x1", "Python"): 5}
    rules["last_attempt_counts"] = True
    attempts.append({**attempts[0], "grade": 4, "line": 7})
    assert select_attempts(attempts, rules, log) == {("x1", "Python"): 4}
    assert "разные результаты в одну дату" in log.getvalue()


def test_recommendations(student, rules, plan):
    """Сразу целевая оценка, ни одной лишней дисциплины."""
    message = recommendations(student, results(2, 5, "незачёт"), plan, rules)
    assert "академической" in message
    assert "Алгебра» на 4" in message and "Язык»" in message
    assert "Python" not in message
    assert recommendations(student, results(4, 5), plan, rules) == (
        "Для повышенной стипендии: сдать/пересдать «Алгебра» на 5"
    )
    assert "уже достигнут" in recommendations(student, results(5, 5), plan, rules)
    student["funding"] = "контракт"
    assert recommendations(student, results(2, 2), plan, rules) == "не претендует"


def test_statistics(rules, plan):
    """Неявка входит только в долю долгов, для зачётов среднего нет."""
    students = {"x1": {}, "x2": {}}
    data = {("x1", "Алгебра"): 2, ("x2", "Алгебра"): "н/я",
            ("x1", "Язык"): "зачёт", ("x2", "Язык"): "незачёт"}
    stats = {row["discipline"]: row
             for row in discipline_statistics(students, data, plan, rules)}
    assert stats["Алгебра"]["average"] == 2
    assert stats["Алгебра"]["failure_share"] == 1
    assert stats["Алгебра"]["debt_share"] == 1
    assert stats["Язык"]["average"] is None
    assert stats["Язык"]["failure_share"] == 0.5
    assert stats["Python"]["failure_share"] is None
    assert discipline_statistics({}, {}, plan, rules)[0]["debt_share"] is None


def test_rating_and_empty_plan(student, rules):
    """Три ключа сортировки, None в конце и защита от all([])."""
    rows = [{"average_grade": a, "debts_count": d, "fio": f}
            for a, d, f in [(None, 0, "А"), (4, 2, "А"),
                            (4, 1, "Б"), (4, 1, "А"), (5, 3, "В")]]
    assert [row["fio"] for row in sorted(rows, key=rating_key)] == [
        "В", "А", "Б", "А", "А",
    ]
    assert stipend(student, {}, {}, rules) == ("нет", 0)
    assert average_grade("x1", {}, {}, rules) is None
