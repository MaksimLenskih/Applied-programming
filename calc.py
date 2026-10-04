"""Расчёты на нормализованных данных: без чтения файлов и печати."""


def select_attempts(attempts, rules, log=None):
    """Выбрать последнюю по дате (либо лучшую) допустимую попытку."""
    selected = {}
    seen = set()
    for attempt in attempts:
        key = (attempt["student_id"], attempt["discipline"])
        identity = (*key, attempt["date"], attempt["grade"])
        if identity in seen:
            if log is not None:
                log.write(f"студент={key[0]} | дисциплина={key[1]} | "
                          f"исходное={attempt!r} | причина=дубликат | "
                          "действие=повтор отброшен\n")
            continue
        seen.add(identity)
        previous = selected.get(key)
        if previous is None:
            selected[key] = attempt
            continue
        if rules["last_attempt_counts"]:
            replace = attempt["date"] >= previous["date"]
        else:
            replace = attempt_rank(attempt, rules) >= attempt_rank(
                previous, rules,
            )
        if replace:
            selected[key] = attempt
        if log is not None:
            reason = ("разные результаты в одну дату"
                      if attempt["date"] == previous["date"] else "попытки")
            chosen = selected[key]
            log.write(
                f"студент={key[0]} | дисциплина={key[1]} | "
                f"исходное={previous!r}; {attempt!r} | причина={reason} | "
                f"действие=учтена строка {chosen['line']} "
                f"от {chosen['date']} с результатом {chosen['grade']!r}\n"
            )
    return {key: attempt["grade"] for key, attempt in selected.items()}


def attempt_rank(attempt, rules):
    """Для альтернативы false: лучший результат, затем поздняя дата."""
    grade = attempt["grade"]
    if type(grade) is int:
        rank = grade
    elif grade in rules["credit_values"]:
        rank = len(rules["credit_values"]) - rules["credit_values"].index(grade)
    else:
        rank = float("-inf")
    return rank, attempt["date"]


def exam_values(sid, results, plan, rules):
    """Собрать только допустимые числовые результаты экзаменов."""
    return [results[(sid, name)] for name, kind in plan.items()
            if kind == "экзамен"
            and type(results.get((sid, name))) is int
            and results[(sid, name)] in rules["valid_grades"]]


def average_grade(sid, results, plan, rules):
    """Вычислить среднее по экзаменам; при отсутствии оценок вернуть None."""
    values = exam_values(sid, results, plan, rules)
    return sum(values) / len(values) if values else None


def debt_reason(grade, kind, rules):
    """Определить причину долга; пустая строка означает успешный результат."""
    if grade is None:
        return "нет допустимого результата"
    if grade == rules["absent_mark"]:
        return "неявка"
    if kind == "экзамен":
        if type(grade) is not int or grade not in rules["valid_grades"]:
            return "нет допустимого результата"
        if grade == min(rules["valid_grades"]):
            return f"неудовлетворительная оценка {grade}"
    elif grade != rules["credit_values"][0]:
        return str(grade)
    return ""


def debts(sid, results, plan, rules):
    """Проверить весь план, включая дисциплины без записей в ведомости."""
    return {name: reason for name, kind in plan.items()
            if (reason := debt_reason(results.get((sid, name)), kind, rules))}


def stipend(student, results, plan, rules):
    """Вернуть вид и сумму стипендии по финансированию, долгам и порогу."""
    sid = student["student_id"].casefold()
    if (student["funding"].casefold() != rules["eligible_funding"]
            or debts(sid, results, plan, rules)):
        return "нет", 0
    values = exam_values(sid, results, plan, rules)
    if not values:
        return "нет", 0
    for level, label in [("increased", "повышенная"),
                         ("academic", "академическая")]:
        policy = rules["stipend"][level]
        if all(value >= policy["min_grade"] for value in values):
            return label, policy["amount"]
    return "нет", 0


def recommendations(student, results, plan, rules):
    """Предложить ровно по одному действию для каждого препятствия."""
    if student["funding"].casefold() != rules["eligible_funding"]:
        return "не претендует"
    label, _ = stipend(student, results, plan, rules)
    if label == "повышенная":
        return "уровень повышенной стипендии уже достигнут"
    level = "increased" if label == "академическая" else "academic"
    target = rules["stipend"][level]["min_grade"]
    sid = student["student_id"].casefold()
    actions = []
    for name, kind in plan.items():
        grade = results.get((sid, name))
        if kind == "экзамен":
            if (type(grade) is not int or grade not in rules["valid_grades"]
                    or grade < target
                    or grade == min(rules["valid_grades"])):
                passing = [value for value in rules["valid_grades"]
                           if value >= target
                           and value > min(rules["valid_grades"])]
                if not passing:
                    return "цель недостижима при заданных правилах"
                actions.append(f'сдать/пересдать «{name}» на {min(passing)}')
        elif grade != rules["credit_values"][0]:
            actions.append(f'получить «{rules["credit_values"][0]}» '
                           f'по дисциплине «{name}»')
    if not exam_values(sid, results, plan, rules) and not any(
        kind == "экзамен" for kind in plan.values()
    ):
        return "стипендия не определяется: в плане нет экзаменов"
    target_label = "повышенной" if level == "increased" else "академической"
    return f"Для {target_label} стипендии: " + "; ".join(actions)


def summarize(students, results, plan, rules):
    """Объединить индивидуальные расчёты в список строк отчёта."""
    rows = []
    for sid, student in students.items():
        label, amount = stipend(student, results, plan, rules)
        student_debts = debts(sid, results, plan, rules)
        rows.append({**student, "average_grade": average_grade(
            sid, results, plan, rules,
        ), "debts": student_debts, "debts_count": len(student_debts),
            "stipend": label, "stipend_amount": amount,
            "recommendation": recommendations(student, results, plan, rules)})
    return rows


def discipline_statistics(students, results, plan, rules):
    """Среднее и доли: неудовлетворительные среди результатов, долги в группе."""
    stats = []
    for name, kind in plan.items():
        values = [results.get((sid, name)) for sid in students]
        if kind == "экзамен":
            valid = [value for value in values if type(value) is int
                     and value in rules["valid_grades"]]
            failures = sum(value == min(rules["valid_grades"])
                           for value in valid)
            average = sum(valid) / len(valid) if valid else None
        else:
            valid = [value for value in values
                     if value in rules["credit_values"]]
            failures = sum(value == rules["credit_values"][1]
                           for value in valid)
            average = None
        debt_count = sum(bool(debt_reason(value, kind, rules))
                         for value in values)
        stats.append({"discipline": name, "type": kind,
                      "average": average, "valid_count": len(valid),
                      "failure_share": failures / len(valid) if valid else None,
                      "debt_share": debt_count / len(students)
                      if students else None})
    return stats
