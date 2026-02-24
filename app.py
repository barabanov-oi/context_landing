import json
import os
import re
from functools import wraps
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "context-landing-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

DATA_FILE = Path("data/cases.json")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Zа-яА-Я0-9\s-]", "", text).strip().lower()
    cleaned = cleaned.replace("ё", "е")
    slug = re.sub(r"\s+", "-", cleaned)
    slug = re.sub(r"-+", "-", slug)
    return slug or "case"


def load_cases() -> list[dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open("r", encoding="utf-8") as file:
        cases = json.load(file)

    for case in cases:
        case.setdefault("custom_content", "")
    return cases


def save_cases(cases: list[dict[str, Any]]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(cases, file, ensure_ascii=False, indent=2)


def find_case(slug: str) -> dict[str, Any] | None:
    for case in load_cases():
        if case["slug"] == slug:
            return case
    return None


def make_unique_slug(title: str, old_slug: str | None = None) -> str:
    base_slug = slugify(title)
    used_slugs = {case["slug"] for case in load_cases()}
    if old_slug:
        used_slugs.discard(old_slug)

    candidate = base_slug
    counter = 2
    while candidate in used_slugs:
        candidate = f"{base_slug}-{counter}"
        counter += 1
    return candidate


def parse_tags(tags: str) -> list[str]:
    return [part.strip() for part in tags.split(",") if part.strip()]


def admin_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Войдите в админку.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return handler(*args, **kwargs)

    return wrapped


@app.route("/")
def index() -> str:
    return render_template("index.html", cases=load_cases())


@app.route("/cases/<slug>")
def case_detail(slug: str) -> str:
    case = find_case(slug)
    if case is None:
        abort(404)
    return render_template("case_detail.html", case=case)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login() -> str:
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Вход выполнен.", "success")
            target = request.args.get("next") or url_for("admin_list")
            return redirect(target)
        flash("Неверный пароль.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout() -> str:
    session.pop("is_admin", None)
    flash("Вы вышли из админки.", "info")
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_list() -> str:
    return render_template("admin_list.html", cases=load_cases())


@app.route("/admin/cases/new", methods=["GET", "POST"])
@admin_required
def admin_new_case() -> str:
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Укажите заголовок кейса.", "danger")
            return render_template("admin_form.html", case=None)

        cases = load_cases()
        case_data = {
            "slug": make_unique_slug(title),
            "title": title,
            "subtitle": request.form.get("subtitle", "").strip(),
            "duration": request.form.get("duration", "").strip(),
            "teaser": request.form.get("teaser", "").strip(),
            "metric_1": request.form.get("metric_1", "").strip(),
            "metric_2": request.form.get("metric_2", "").strip(),
            "metric_3": request.form.get("metric_3", "").strip(),
            "task": request.form.get("task", "").strip(),
            "hypothesis": request.form.get("hypothesis", "").strip(),
            "actions": request.form.get("actions", "").strip(),
            "result": request.form.get("result", "").strip(),
            "conclusion": request.form.get("conclusion", "").strip(),
            "custom_content": request.form.get("custom_content", "").strip(),
            "tags": parse_tags(request.form.get("tags", "")),
        }
        cases.append(case_data)
        save_cases(cases)
        flash("Кейс добавлен.", "success")
        return redirect(url_for("admin_list"))

    return render_template("admin_form.html", case=None)


@app.route("/admin/cases/<slug>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_case(slug: str) -> str:
    cases = load_cases()
    case = next((item for item in cases if item["slug"] == slug), None)
    if case is None:
        abort(404)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Укажите заголовок кейса.", "danger")
            return render_template("admin_form.html", case=case)

        case.update(
            {
                "slug": make_unique_slug(title, old_slug=case["slug"]),
                "title": title,
                "subtitle": request.form.get("subtitle", "").strip(),
                "duration": request.form.get("duration", "").strip(),
                "teaser": request.form.get("teaser", "").strip(),
                "metric_1": request.form.get("metric_1", "").strip(),
                "metric_2": request.form.get("metric_2", "").strip(),
                "metric_3": request.form.get("metric_3", "").strip(),
                "task": request.form.get("task", "").strip(),
                "hypothesis": request.form.get("hypothesis", "").strip(),
                "actions": request.form.get("actions", "").strip(),
                "result": request.form.get("result", "").strip(),
                "conclusion": request.form.get("conclusion", "").strip(),
                "custom_content": request.form.get("custom_content", "").strip(),
                "tags": parse_tags(request.form.get("tags", "")),
            }
        )
        save_cases(cases)
        flash("Кейс обновлён.", "success")
        return redirect(url_for("admin_list"))

    return render_template("admin_form.html", case=case)


if __name__ == "__main__":
    app.run(debug=True)
