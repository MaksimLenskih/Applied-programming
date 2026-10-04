# Запуск на Windows

Нужны Python 3.10+ и интернет для установки зависимостей.
Скачайте и распакуйте репозиторий или клонируйте его через Git.
Откройте терминал в корне репозитория и выполните команды по порядку:

```powershell
cd "Прикладное программирование на языке высокого уровня/Лабораторная работа 1"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Если команда `py` недоступна, используйте `python -m venv .venv`.
Активация окружения не требуется: команды явно используют его Python.

# Входные данные и результаты

В папке лабораторной должны находиться `students.csv`, `plan.csv`,
`grades.csv` и `rules.json`. CSV используют разделитель `;` и UTF-8 с BOM.

Результаты автоматически сохраняются в `results` рядом с `main.py`:

- `rating.csv` — рейтинг студентов;
- `debtors.csv` — задолжники и причины долгов;
- `recommendations.csv` — действия для получения стипендии;
- `errors.log` — ошибки и преобразования данных;
- `average_grades.png` — диаграмма средних по экзаменам.

Статистика и рекомендации также выводятся в терминал.

# Тесты и генератор

Из папки лабораторной, Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe generator.py --count 30 --error-rate 0.2 --output generated
```

На Linux/macOS замените `.\.venv\Scripts\python.exe` на `.venv/bin/python`.
Генератор записывает отдельный набор данных в `generated`.
Параметры запуска доступны через `main.py --help` и `generator.py --help`.
