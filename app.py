import json
import os
import re
import uuid
from functools import wraps
from pathlib import Path
from typing import Any

import requests
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "context-landing-secret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

DATA_FILE = Path("data/cases.json")
USERS_FILE = Path("data/users.json")
SITE_CONTENT_FILE = Path("data/site_content.json")
YANDEX_DIRECT_API_URL = "https://api.direct.yandex.com/json/v5/customers"
UPLOADS_DIR = Path("static/uploads/covers")
EDITOR_UPLOADS_DIR = Path("static/uploads/editor")
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


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
        case.setdefault("cover_image", "")
        case.setdefault("metric_1_label", "")
        case.setdefault("metric_2_label", "")
        case.setdefault("metric_1_before", "")
        case.setdefault("metric_1_after", case.get("metric_1", ""))
        case.setdefault("metric_1_dynamic", "")
        case.setdefault("metric_2_before", "")
        case.setdefault("metric_2_after", case.get("metric_2", ""))
        case.setdefault("metric_2_dynamic", "")
        case.setdefault("metric_1_trend", "up")
        case.setdefault("metric_2_trend", "up")
        case.setdefault("metric_1_color", "green")
        case.setdefault("metric_2_color", "green")
        case.setdefault("project_stages", [])
        case.setdefault("niche", "")
        case.setdefault("sources", [])
        case.setdefault("icon", "⚖️")
        case.setdefault("leads", "")
        case.setdefault("budget", "")
        case.setdefault("cpl", "")
        case.setdefault("cr", "")
    return cases


def save_cases(cases: list[dict[str, Any]]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(cases, file, ensure_ascii=False, indent=2)


def load_users() -> list[dict[str, Any]]:
    if not USERS_FILE.exists():
        return []
    with USERS_FILE.open("r", encoding="utf-8") as file:
        users = json.load(file)

    for user in users:
        user.setdefault("direct_accounts", [])
    return users


def save_users(users: list[dict[str, Any]]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USERS_FILE.open("w", encoding="utf-8") as file:
        json.dump(users, file, ensure_ascii=False, indent=2)


def load_site_content() -> dict[str, str]:
    default_content = {
        "about_me_title": "Обо мне",
        "about_me_text": (
            "Я специалист по контекстной рекламе в формате резюме-портфолио: "
            "помогаю бизнесу получать прогнозируемые заявки и показываю результат на реальных кейсах."
        ),
    }
    if not SITE_CONTENT_FILE.exists():
        return default_content

    with SITE_CONTENT_FILE.open("r", encoding="utf-8") as file:
        content = json.load(file)

    content.setdefault("about_me_title", default_content["about_me_title"])
    content.setdefault("about_me_text", default_content["about_me_text"])
    return content


def save_site_content(content: dict[str, str]) -> None:
    SITE_CONTENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SITE_CONTENT_FILE.open("w", encoding="utf-8") as file:
        json.dump(content, file, ensure_ascii=False, indent=2)


def find_user(email: str) -> dict[str, Any] | None:
    email_normalized = email.strip().lower()
    for user in load_users():
        if user["email"] == email_normalized:
            return user
    return None


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


def parse_project_stages(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def save_cover_file(file_storage) -> str | None:
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        return None

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOADS_DIR / unique_name
    file_storage.save(file_path)
    return f"uploads/covers/{unique_name}"




def save_editor_image_file(file_storage) -> str | None:
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        return None

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    EDITOR_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{extension}"
    file_path = EDITOR_UPLOADS_DIR / unique_name
    file_storage.save(file_path)
    return f"uploads/editor/{unique_name}"


def admin_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Войдите в админку.", "warning")
            return redirect(url_for("admin", next=request.path))
        return handler(*args, **kwargs)

    return wrapped


def auth_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not session.get("user_email"):
            flash("Сначала войдите в аккаунт.", "warning")
            return redirect(url_for("login", next=request.path))
        return handler(*args, **kwargs)

    return wrapped


def validate_direct_connection(token: str, login: str) -> tuple[bool, str]:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {"Logins": [login]},
            "FieldNames": ["Login", "Name", "CountryId", "Currency"],
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }

    response = requests.post(
        YANDEX_DIRECT_API_URL,
        json=payload,
        headers=headers,
        timeout=15,
    )

    if response.status_code >= 400:
        return False, f"HTTP {response.status_code}: {response.text[:200]}"

    data = response.json()
    if "error" in data:
        error = data["error"]
        detail = error.get("error_detail") or error.get("error_string") or "Неизвестная ошибка API"
        return False, detail

    result = data.get("result", {})
    customers = result.get("Customers", [])
    if not customers:
        return False, "API не вернуло клиентов по указанному логину."

    customer = customers[0]
    name = customer.get("Name") or customer.get("Login")
    return True, name


@app.route("/")
def index() -> str:
    cases = load_cases()
    site_content = load_site_content()

    niches = sorted({case.get("niche", "").strip() for case in cases if case.get("niche")})
    sources = sorted(
        {
            source.strip()
            for case in cases
            for source in case.get("sources", [])
            if source and source.strip()
        }
    )

    selected_niche = request.args.get("niche", "").strip()
    selected_source = request.args.get("source", "").strip()

    filtered_cases = [
        case
        for case in cases
        if (not selected_niche or case.get("niche") == selected_niche)
        and (
            not selected_source
            or selected_source in [source.strip() for source in case.get("sources", [])]
        )
    ]

    return render_template(
        "index.html",
        cases=filtered_cases,
        niches=niches,
        sources=sources,
        selected_niche=selected_niche,
        selected_source=selected_source,
        site_content=site_content,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup() -> str:
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or "@" not in email:
            flash("Укажите корректный email.", "danger")
            return render_template("signup.html")
        if len(password) < 6:
            flash("Пароль должен содержать минимум 6 символов.", "danger")
            return render_template("signup.html")
        if find_user(email):
            flash("Пользователь с таким email уже зарегистрирован.", "danger")
            return render_template("signup.html")

        users = load_users()
        users.append(
            {
                "email": email,
                "password_hash": generate_password_hash(password),
                "direct_accounts": [],
            }
        )
        save_users(users)
        session["user_email"] = email
        flash("Регистрация прошла успешно. Добро пожаловать!", "success")
        return redirect(url_for("cabinet"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = find_user(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Неверный email или пароль.", "danger")
            return render_template("login.html")

        session["user_email"] = user["email"]
        flash("Вы успешно вошли в аккаунт.", "success")
        target = request.args.get("next") or url_for("cabinet")
        return redirect(target)

    return render_template("login.html")


@app.route("/logout")
def logout() -> str:
    session.pop("user_email", None)
    flash("Вы вышли из личного кабинета.", "info")
    return redirect(url_for("index"))


@app.route("/cabinet")
@auth_required
def cabinet() -> str:
    user = find_user(session["user_email"])
    if user is None:
        session.pop("user_email", None)
        flash("Пользователь не найден. Войдите снова.", "warning")
        return redirect(url_for("login"))
    return render_template("cabinet.html", user=user)


@app.route("/cabinet/direct/connect", methods=["POST"])
@auth_required
def connect_direct() -> str:
    token = request.form.get("access_token", "").strip()
    direct_login = request.form.get("direct_login", "").strip()

    if not token or not direct_login:
        flash("Укажите OAuth-токен и логин аккаунта Директа.", "danger")
        return redirect(url_for("cabinet"))

    users = load_users()
    user_index = next(
        (idx for idx, item in enumerate(users) if item["email"] == session["user_email"]),
        None,
    )
    if user_index is None:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("login"))

    user = users[user_index]
    already_connected = next(
        (acc for acc in user.get("direct_accounts", []) if acc["direct_login"] == direct_login),
        None,
    )
    if already_connected is not None:
        flash("Этот аккаунт Яндекс Директ уже подключён.", "warning")
        return redirect(url_for("cabinet"))

    try:
        is_valid, name_or_error = validate_direct_connection(token, direct_login)
    except requests.RequestException as error:
        flash(f"Ошибка подключения к API Яндекс Директ: {error}", "danger")
        return redirect(url_for("cabinet"))

    if not is_valid:
        flash(f"Не удалось подключить аккаунт: {name_or_error}", "danger")
        return redirect(url_for("cabinet"))

    user.setdefault("direct_accounts", []).append(
        {
            "direct_login": direct_login,
            "display_name": name_or_error,
            "access_token": token,
        }
    )
    save_users(users)
    flash(f"Аккаунт {direct_login} успешно подключён к кабинету.", "success")
    return redirect(url_for("cabinet"))


@app.route("/cabinet/direct/<direct_login>/disconnect", methods=["POST"])
@auth_required
def disconnect_direct(direct_login: str) -> str:
    users = load_users()
    user_index = next(
        (idx for idx, item in enumerate(users) if item["email"] == session["user_email"]),
        None,
    )
    if user_index is None:
        flash("Пользователь не найден.", "danger")
        return redirect(url_for("login"))

    user = users[user_index]
    before = len(user.get("direct_accounts", []))
    user["direct_accounts"] = [
        account
        for account in user.get("direct_accounts", [])
        if account["direct_login"] != direct_login
    ]

    if len(user["direct_accounts"]) == before:
        flash("Аккаунт не найден среди подключённых.", "warning")
    else:
        save_users(users)
        flash(f"Аккаунт {direct_login} отключён.", "info")

    return redirect(url_for("cabinet"))


@app.route("/cases/<slug>")
def case_detail(slug: str) -> str:
    case = find_case(slug)
    if case is None:
        abort(404)
    return render_template("case_detail.html", case=case)


@app.route("/admin", methods=["GET", "POST"])
def admin() -> str:
    if session.get("is_admin"):
        return redirect(url_for("admin_list"))

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




@app.route("/admin/editor/upload-image", methods=["POST"])
@admin_required
def admin_upload_editor_image():
    uploaded_image = request.files.get("image")
    if uploaded_image is None or not uploaded_image.filename:
        return jsonify({"error": "Файл изображения не передан."}), 400

    saved_image = save_editor_image_file(uploaded_image)
    if saved_image is None:
        return jsonify({"error": "Поддерживаются только изображения: PNG, JPG, JPEG, WEBP, GIF."}), 400

    return jsonify({"url": url_for("static", filename=saved_image)})


@app.route("/admin/cases")
@admin_required
def admin_list() -> str:
    return render_template("admin_list.html", cases=load_cases())


@app.route("/admin/content", methods=["GET", "POST"])
@admin_required
def admin_content() -> str:
    content = load_site_content()

    if request.method == "POST":
        about_me_title = request.form.get("about_me_title", "").strip()
        about_me_text = request.form.get("about_me_text", "").strip()

        if not about_me_title or not about_me_text:
            flash("Заполните заголовок и текст блока «Обо мне».", "danger")
            return render_template("admin_content.html", content=content)

        content.update(
            {
                "about_me_title": about_me_title,
                "about_me_text": about_me_text,
            }
        )
        save_site_content(content)
        flash("Блок «Обо мне» обновлён.", "success")
        return redirect(url_for("admin_content"))

    return render_template("admin_content.html", content=content)


@app.route("/admin/cases/new", methods=["GET", "POST"])
@admin_required
def admin_new_case() -> str:
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Укажите заголовок кейса.", "danger")
            return render_template("admin_form.html", case=None)

        cases = load_cases()
        cover_image = ""
        uploaded_cover = request.files.get("cover_image")
        if uploaded_cover and uploaded_cover.filename:
            saved_cover = save_cover_file(uploaded_cover)
            if saved_cover is None:
                flash("Поддерживаются только изображения: PNG, JPG, JPEG, WEBP, GIF.", "danger")
                return render_template("admin_form.html", case=None)
            cover_image = saved_cover

        case_data = {
            "slug": make_unique_slug(title),
            "title": title,
            "subtitle": request.form.get("subtitle", "").strip(),
            "duration": request.form.get("duration", "").strip(),
            "teaser": request.form.get("teaser", "").strip(),
            "cover_image": cover_image,
            "metric_1_label": request.form.get("metric_1_label", "").strip(),
            "metric_1_before": request.form.get("metric_1_before", "").strip(),
            "metric_1_after": request.form.get("metric_1_after", "").strip(),
            "metric_1_dynamic": request.form.get("metric_1_dynamic", "").strip(),
            "metric_1_trend": request.form.get("metric_1_trend", "up").strip() or "up",
            "metric_1_color": request.form.get("metric_1_color", "green").strip() or "green",
            "metric_2_label": request.form.get("metric_2_label", "").strip(),
            "metric_2_before": request.form.get("metric_2_before", "").strip(),
            "metric_2_after": request.form.get("metric_2_after", "").strip(),
            "metric_2_dynamic": request.form.get("metric_2_dynamic", "").strip(),
            "metric_2_trend": request.form.get("metric_2_trend", "up").strip() or "up",
            "metric_2_color": request.form.get("metric_2_color", "green").strip() or "green",
            "task": request.form.get("task", "").strip(),
            "hypothesis": request.form.get("hypothesis", "").strip(),
            "actions": request.form.get("actions", "").strip(),
            "result": request.form.get("result", "").strip(),
            "conclusion": request.form.get("conclusion", "").strip(),
            "custom_content": request.form.get("custom_content", "").strip(),
            "tags": parse_tags(request.form.get("tags", "")),
            "project_stages": parse_project_stages(request.form.getlist("project_stages[]")),
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

        uploaded_cover = request.files.get("cover_image")
        new_cover_image = case.get("cover_image", "")
        if uploaded_cover and uploaded_cover.filename:
            saved_cover = save_cover_file(uploaded_cover)
            if saved_cover is None:
                flash("Поддерживаются только изображения: PNG, JPG, JPEG, WEBP, GIF.", "danger")
                return render_template("admin_form.html", case=case)

            old_cover = case.get("cover_image", "")
            old_cover_path = Path("static") / old_cover if old_cover else None
            if old_cover_path and old_cover_path.exists() and old_cover_path.is_file():
                old_cover_path.unlink()
            new_cover_image = saved_cover

        case.update(
            {
                "slug": make_unique_slug(title, old_slug=case["slug"]),
                "title": title,
                "subtitle": request.form.get("subtitle", "").strip(),
                "duration": request.form.get("duration", "").strip(),
                "teaser": request.form.get("teaser", "").strip(),
                "cover_image": new_cover_image,
                "metric_1_label": request.form.get("metric_1_label", "").strip(),
                "metric_1_before": request.form.get("metric_1_before", "").strip(),
                "metric_1_after": request.form.get("metric_1_after", "").strip(),
                "metric_1_dynamic": request.form.get("metric_1_dynamic", "").strip(),
                "metric_1_trend": request.form.get("metric_1_trend", "up").strip() or "up",
                "metric_1_color": request.form.get("metric_1_color", "green").strip() or "green",
                "metric_2_label": request.form.get("metric_2_label", "").strip(),
                "metric_2_before": request.form.get("metric_2_before", "").strip(),
                "metric_2_after": request.form.get("metric_2_after", "").strip(),
                "metric_2_dynamic": request.form.get("metric_2_dynamic", "").strip(),
                "metric_2_trend": request.form.get("metric_2_trend", "up").strip() or "up",
                "metric_2_color": request.form.get("metric_2_color", "green").strip() or "green",
                "task": request.form.get("task", "").strip(),
                "hypothesis": request.form.get("hypothesis", "").strip(),
                "actions": request.form.get("actions", "").strip(),
                "result": request.form.get("result", "").strip(),
                "conclusion": request.form.get("conclusion", "").strip(),
                "custom_content": request.form.get("custom_content", "").strip(),
                "tags": parse_tags(request.form.get("tags", "")),
                "project_stages": parse_project_stages(request.form.getlist("project_stages[]")),
            }
        )
        save_cases(cases)
        flash("Кейс обновлён.", "success")
        return redirect(url_for("admin_list"))

    return render_template("admin_form.html", case=case)


if __name__ == "__main__":
    app.run(debug=True)
