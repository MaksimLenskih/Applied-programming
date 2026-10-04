"""CSV для Excel, консольная сводка и диаграмма."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def write_csv(path, fields, rows):
    """Сохранить таблицу с BOM, разделителем ; и окончаниями CRLF."""
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def rating_key(row):
    """Среднее убывает, число долгов возрастает, затем алфавит ФИО."""
    average = row["average_grade"]
    return (-(average if average is not None else float("-inf")),
            row["debts_count"], row["fio"].casefold())


def excel_number(value):
    """Форматировать число с запятой для русской локали Excel."""
    return "" if value is None else f"{value:.2f}".replace(".", ",")


def save_reports(rows, output):
    """Записать рейтинг, задолжников и рекомендации в отдельные CSV."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rating = []
    for row in sorted(rows, key=rating_key):
        rating.append({field: row[field] for field in
                       ["student_id", "fio", "debts_count", "stipend",
                        "stipend_amount"]})
        rating[-1]["average_grade"] = excel_number(row["average_grade"])
    write_csv(output / "rating.csv", ["student_id", "fio", "average_grade",
              "debts_count", "stipend", "stipend_amount"], rating)
    debtors = [{"student_id": row["student_id"], "fio": row["fio"],
                "debts": "; ".join(f"{name}: {reason}" for name, reason
                                   in row["debts"].items())}
               for row in rows if row["debts"]]
    write_csv(output / "debtors.csv", ["student_id", "fio", "debts"], debtors)
    write_csv(output / "recommendations.csv",
              ["student_id", "fio", "recommendation"],
              [{key: row[key] for key in
                ["student_id", "fio", "recommendation"]} for row in rows])


def percentage(value):
    """Показать процент либо сообщение об отсутствии данных."""
    return "нет данных" if value is None else f"{value:.2%}"


def print_summary(rows, stats):
    """Напечатать фонд, статистику дисциплин и индивидуальные рекомендации."""
    print(f"Студентов: {len(rows)}")
    for label in ["академическая", "повышенная"]:
        count = sum(row["stipend"] == label for row in rows)
        print(f"{label.capitalize()} стипендия: {count}")
    print(f"Общий стипендиальный фонд: "
          f"{sum(row['stipend_amount'] for row in rows):g} руб.")
    print("\nСтатистика по актуальным допустимым результатам:")
    for item in stats:
        if item["type"] == "зачёт":
            average = "не применяется (зачёт)"
        else:
            average = (f"{item['average']:.4f}"
                       if item["average"] is not None else "нет данных")
        print(f"{item['discipline']}: среднее={average}; "
              f"допустимых результатов={item['valid_count']}; "
              f"неудовлетворительных="
              f"{percentage(item['failure_share'])}; "
              f"долги в группе={percentage(item['debt_share'])}")
    print("\nЧто нужно для стипендии:")
    for row in rows:
        print(f"{row['student_id']} — {row['fio']}: {row['recommendation']}")


def save_chart(stats, path):
    """Сохранить диаграмму экзаменов; отсутствующие средние пометить явно."""
    exams = [item for item in stats if item["type"] == "экзамен"]
    figure, axes = plt.subplots(figsize=(10, 6))
    if exams:
        heights = [item["average"] if item["average"] is not None else 0
                   for item in exams]
        bars = axes.bar([item["discipline"] for item in exams], heights,
                        color="#426cb4")
        for bar, item in zip(bars, exams):
            label = (f"{item['average']:.2f}" if item["average"] is not None
                     else "нет данных")
            axes.annotate(label, (bar.get_x() + bar.get_width() / 2,
                                 bar.get_height()), ha="center", va="bottom")
        axes.tick_params(axis="x", labelrotation=25)
        for label in axes.get_xticklabels():
            label.set_horizontalalignment("right")
        axes.margins(y=0.15)
    else:
        axes.text(0.5, 0.5, "В плане нет экзаменов", ha="center",
                  transform=axes.transAxes)
    axes.set_title("Средний балл по экзаменационным дисциплинам")
    axes.set_ylabel("Средний балл")
    axes.set_ylim(bottom=0)
    axes.grid(axis="y", alpha=0.2)
    axes.set_axisbelow(True)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
