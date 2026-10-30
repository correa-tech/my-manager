
from datetime import date, datetime, timedelta

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for

from db import get_db, init_app as db_init, init_db

app = Flask(__name__)
app.config["SECRET_KEY"] = "local-dev-only-change-me"
db_init(app)
with app.app_context():
    init_db()

def today_str():
    return date.today().isoformat()

def add_months(y, m, delta):
    m += delta
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return y, m

def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

# ---------- RESUMO ----------
@app.route("/")
def resumo():
    db = get_db()
    today = today_str()
    in_7 = (date.today() + timedelta(days=7)).isoformat()

    priority_tasks = db.execute("""
      SELECT t.*, a.name AS area_name FROM tasks t JOIN areas a ON a.id = t.area_id
       WHERE t.status='pending' AND (
         (t.due_date IS NOT NULL AND t.due_date < ?)
         OR t.priority='high'
         OR (t.due_date IS NOT NULL AND t.due_date BETWEEN ? AND ?))
       ORDER BY CASE WHEN t.due_date IS NOT NULL AND t.due_date < ? THEN 0
                     WHEN t.priority='high' THEN 1 ELSE 2 END,
                t.due_date IS NULL, t.due_date, t.id DESC
       LIMIT 10
    """, (today, today, in_7, today)).fetchall()

    events_next = db.execute(
        "SELECT * FROM events WHERE date >= ? ORDER BY date, start_time LIMIT 5",
        (today,)).fetchall()
    tasks_today = db.execute("""
      SELECT t.*, a.name AS area_name FROM tasks t JOIN areas a ON a.id=t.area_id
       WHERE t.due_date=? AND t.status='pending'
       ORDER BY t.due_time IS NULL, t.due_time
    """, (today,)).fetchall()

    notes_review = db.execute(
        "SELECT * FROM notes WHERE review=1 ORDER BY updated_at DESC LIMIT 5").fetchall()
    notes_fav = db.execute(
        "SELECT * FROM notes WHERE favorite=1 AND review=0 ORDER BY updated_at DESC LIMIT 5").fetchall()

    stats = {
        "pending": db.execute("SELECT COUNT(*) c FROM tasks WHERE status='pending'").fetchone()["c"],
        "done":    db.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"],
        "overdue": db.execute(
            "SELECT COUNT(*) c FROM tasks WHERE status='pending' AND due_date < ?",
            (today,)).fetchone()["c"],
    }
    area_progress = db.execute("""
      SELECT a.id, a.name, COUNT(t.id) total,
             SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) done
        FROM areas a LEFT JOIN tasks t ON t.area_id=a.id
       GROUP BY a.id ORDER BY a.name
    """).fetchall()

    return render_template("resumo.html",
        priority_tasks=priority_tasks, events_next=events_next,
        tasks_today=tasks_today, notes_review=notes_review,
        notes_fav=notes_fav, stats=stats, area_progress=area_progress,
        today=today)

# ---------- ÁREAS + TAREFAS ----------
@app.route("/todo")
def todo_index():
    db = get_db()
    areas = db.execute("""
      SELECT a.*,
             (SELECT COUNT(*) FROM tasks WHERE area_id=a.id) total,
               (SELECT COUNT(*) FROM tasks WHERE area_id=a.id AND (stage='concluido' OR status='done')) done,
             (SELECT COUNT(*) FROM tasks WHERE area_id=a.id AND status='pending' AND due_date < ?) overdue
           FROM areas a ORDER BY a.parent_id IS NOT NULL, a.created_at
    """, (today_str(),)).fetchall()
    return render_template("areas.html", areas=areas)

@app.route("/areas", methods=["POST"])
def area_create():
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    if not name:
        flash("Informe um nome para a área.", "error")
        return redirect(url_for("todo_index"))
    db = get_db()
    parent_id = request.form.get("parent_id", type=int)
    if parent_id and not db.execute("SELECT id FROM areas WHERE id=?", (parent_id,)).fetchone():
        flash("A área-pai selecionada não existe.", "error")
        return redirect(url_for("todo_index"))
    cur = db.execute("INSERT INTO areas(name, description, parent_id) VALUES (?,?,?) RETURNING id", (name, desc, parent_id))
    area_id = cur.fetchone()["id"]
    db.commit()
    flash("Área criada.", "ok")
    return redirect(url_for("area_detail", area_id=area_id))

@app.route("/areas/<int:area_id>")
def area_detail(area_id):
    db = get_db()
    area = db.execute("SELECT * FROM areas WHERE id=?", (area_id,)).fetchone()
    if not area: abort(404)

    status = request.args.get("status", "all")
    priority = request.args.get("priority", "all")
    stage = request.args.get("stage", "all")
    sort = request.args.get("sort", "created")
    q = request.args.get("q", "").strip()

    where = ["area_id = ?"]; params = [area_id]
    if status in ("pending", "done"):
        where.append("status = ?"); params.append(status)
    if stage in ("inicio", "fazendo", "bug", "concluido"):
        where.append("stage = ?"); params.append(stage)
    if priority in ("low","medium","high"):
        where.append("priority = ?"); params.append(priority)
    if q:
        where.append("(title LIKE ? OR IFNULL(description,'') LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    order = {
        "created": "created_at DESC",
        "due":     "due_date IS NULL, due_date ASC, due_time IS NULL, due_time ASC",
        "priority":"CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END ASC",
    }.get(sort, "created_at DESC")

    tasks = db.execute(f"SELECT * FROM tasks WHERE {' AND '.join(where)} ORDER BY {order}", params).fetchall()

    total = db.execute("SELECT COUNT(*) c FROM tasks WHERE area_id=?", (area_id,)).fetchone()["c"]
    done = db.execute("SELECT COUNT(*) c FROM tasks WHERE area_id=? AND (stage='concluido' OR status='done')", (area_id,)).fetchone()["c"]
    children = db.execute("SELECT * FROM areas WHERE parent_id=? ORDER BY created_at", (area_id,)).fetchall()
    parent = db.execute("SELECT id, name FROM areas WHERE id=?", (area["parent_id"],)).fetchone() if area["parent_id"] else None
    all_areas = db.execute("SELECT id, name, parent_id FROM areas ORDER BY parent_id IS NOT NULL, created_at").fetchall()

    return render_template("area_detalhe.html", area=area, tasks=tasks,
        today=today_str(), total=total, done=done,
        filters={"status": status, "stage": stage, "priority": priority, "sort": sort, "q": q},
        children=children, parent=parent, all_areas=all_areas)

@app.route("/areas/<int:area_id>/edit", methods=["POST"])
def area_edit(area_id):
    db = get_db()
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    if not name:
        flash("Nome obrigatório.", "error")
    else:
        db.execute("UPDATE areas SET name=?, description=? WHERE id=?", (name, desc, area_id))
        db.commit()
        flash("Área atualizada.", "ok")
    return redirect(url_for("area_detail", area_id=area_id))

@app.route("/areas/<int:area_id>/delete", methods=["POST"])
def area_delete(area_id):
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM tasks WHERE area_id=?", (area_id,)).fetchone()["c"]
    children = db.execute("SELECT COUNT(*) c FROM areas WHERE parent_id=?", (area_id,)).fetchone()["c"]
    if (total > 0 or children > 0) and request.form.get("confirm") != "yes":
        flash(f"Esta área possui {total} tarefa(s) e {children} subárea(s). Confirme a exclusão.", "warn")
        return redirect(url_for("area_detail", area_id=area_id))
    db.execute("DELETE FROM areas WHERE parent_id=?", (area_id,))
    db.execute("DELETE FROM areas WHERE id=?", (area_id,))
    db.commit()
    flash("Área excluída.", "ok")
    return redirect(url_for("todo_index"))

@app.route("/areas/<int:area_id>/tasks", methods=["POST"])
def task_create(area_id):
    db = get_db()
    title = request.form.get("title", "").strip()
    if not title:
        flash("Título obrigatório.", "error")
        return redirect(url_for("area_detail", area_id=area_id))
    priority = request.form.get("priority", "medium")
    if priority not in ("low", "medium", "high"):
        priority = "medium"
    due_date = request.form.get("due_date") or None
    if due_date and not parse_date(due_date):
        flash("A data da tarefa é inválida.", "error")
        return redirect(url_for("area_detail", area_id=area_id))
    stage = request.form.get("stage", "inicio")
    if stage not in ("inicio", "fazendo", "bug", "concluido"):
        stage = "inicio"
    db.execute("""INSERT INTO tasks(area_id,title,description,priority,due_date,due_time,stage,status)
                  VALUES (?,?,?,?,?,?,?,?)""", (
        area_id, title,
        request.form.get("description","").strip(),
        priority,
        due_date,
        request.form.get("due_time") or None,
        stage,
        "done" if stage == "concluido" else "pending",
    ))
    db.commit()
    flash("Tarefa criada.", "ok")
    return redirect(url_for("area_detail", area_id=area_id))

@app.route("/tasks/<int:task_id>/edit", methods=["POST"])
def task_edit(task_id):
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not t: abort(404)
    priority = request.form.get("priority", t["priority"])
    if priority not in ("low", "medium", "high"):
        priority = t["priority"]
    due_date = request.form.get("due_date") or None
    if due_date and not parse_date(due_date):
        flash("A data da tarefa é inválida.", "error")
        return redirect(url_for("area_detail", area_id=t["area_id"]))
    stage = request.form.get("stage", t["stage"] or "inicio")
    if stage not in ("inicio", "fazendo", "bug", "concluido"):
        stage = t["stage"] or "inicio"
    db.execute("""UPDATE tasks SET title=?, description=?, priority=?, due_date=?, due_time=?, stage=?, status=?
                   WHERE id=?""", (
        request.form.get("title", t["title"]).strip() or t["title"],
        request.form.get("description","").strip(),
        priority,
        due_date,
        request.form.get("due_time") or None,
        stage,
        "done" if stage == "concluido" else "pending",
        task_id,
    ))
    db.commit()
    return redirect(url_for("area_detail", area_id=t["area_id"]))

@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def task_toggle(task_id):
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not t: abort(404)
    new_stage = "concluido" if (t["stage"] or "inicio") != "concluido" else "inicio"
    db.execute("UPDATE tasks SET status=?, stage=? WHERE id=?", ("done" if new_stage == "concluido" else "pending", new_stage, task_id))
    db.commit()
    return redirect(request.referrer or url_for("area_detail", area_id=t["area_id"]))

@app.route("/tasks/<int:task_id>/stage", methods=["POST"])
def task_stage(task_id):
    db = get_db()
    task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task: abort(404)
    stage = request.form.get("stage", "inicio")
    if stage not in ("inicio", "fazendo", "bug", "concluido"):
        stage = "inicio"
    db.execute("UPDATE tasks SET stage=?, status=? WHERE id=?", (stage, "done" if stage == "concluido" else "pending", task_id))
    db.commit()
    return redirect(request.referrer or url_for("area_detail", area_id=task["area_id"]))

@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def task_delete(task_id):
    db = get_db()
    t = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not t: abort(404)
    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    db.commit()
    return redirect(url_for("area_detail", area_id=t["area_id"]))

# ---------- AGENDA ----------
@app.route("/agenda")
def agenda():
    db = get_db()
    today = date.today()
    try:
        year = int(request.args.get("y", today.year))
        month = int(request.args.get("m", today.month))
    except ValueError:
        year, month = today.year, today.month
    if not (1 <= month <= 12):
        year, month = today.year, today.month

    first = date(year, month, 1)
    next_first = date(*add_months(year, month, 1), 1)
    last = next_first - timedelta(days=1)

    start_offset = (first.weekday() + 1) % 7
    grid_start = first - timedelta(days=start_offset)
    grid_end = last + timedelta(days=(6 - (last.weekday() + 1) % 7))

    weeks = []
    cur = grid_start
    while cur <= grid_end:
        weeks.append([cur + timedelta(days=i) for i in range(7)])
        cur += timedelta(days=7)

    events = db.execute(
        "SELECT * FROM events WHERE date BETWEEN ? AND ? ORDER BY date, start_time",
        (first.isoformat(), last.isoformat())).fetchall()
    tasks = db.execute("""
      SELECT t.*, a.name AS area_name FROM tasks t JOIN areas a ON a.id=t.area_id
       WHERE t.due_date BETWEEN ? AND ?
       ORDER BY t.due_date, t.due_time IS NULL, t.due_time
    """, (first.isoformat(), last.isoformat())).fetchall()

    by_day = {}
    for e in events:
        by_day.setdefault(e["date"], {"events":[], "tasks":[]})["events"].append(e)
    for t in tasks:
        by_day.setdefault(t["due_date"], {"events":[], "tasks":[]})["tasks"].append(t)

    prev_y, prev_m = add_months(year, month, -1)
    next_y, next_m = add_months(year, month, 1)

    return render_template("agenda.html",
        weeks=weeks, month=month, year=year, today=today.isoformat(),
        by_day=by_day, prev=(prev_y, prev_m), next=(next_y, next_m))

@app.route("/events", methods=["POST"])
def event_create():
    db = get_db()
    title = request.form.get("title","").strip()
    d = request.form.get("date")
    if not title or not parse_date(d):
        flash("Título e data são obrigatórios.", "error")
        return redirect(url_for("agenda"))
    db.execute("INSERT INTO events(title,description,date,start_time,end_time) VALUES (?,?,?,?,?)",
        (title, request.form.get("description","").strip(), d,
         request.form.get("start_time") or None, request.form.get("end_time") or None))
    db.commit()
    flash("Compromisso criado.", "ok")
    return redirect(url_for("agenda", y=d[:4], m=int(d[5:7])))

@app.route("/events/<int:event_id>/edit", methods=["POST"])
def event_edit(event_id):
    db = get_db()
    e = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not e: abort(404)
    event_date = request.form.get("date", e["date"])
    if not parse_date(event_date):
        flash("A data do compromisso é inválida.", "error")
        return redirect(url_for("agenda"))
    db.execute("""UPDATE events SET title=?, description=?, date=?, start_time=?, end_time=?
                   WHERE id=?""", (
        request.form.get("title", e["title"]).strip(),
        request.form.get("description","").strip(),
        event_date,
        request.form.get("start_time") or None,
        request.form.get("end_time") or None, event_id))
    db.commit()
    return redirect(url_for("agenda", y=event_date[:4], m=int(event_date[5:7])))

@app.route("/events/<int:event_id>/delete", methods=["POST"])
def event_delete(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    return redirect(url_for("agenda"))

# ---------- ANOTAÇÕES ----------
@app.route("/notas")
def notas():
    db = get_db()
    q = request.args.get("q","").strip()
    tag = request.args.get("tag","").strip()
    filt = request.args.get("filter","")

    where = ["1=1"]; params = []
    if q:
        where.append("(title LIKE ? OR content LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if tag:
        where.append("id IN (SELECT nt.note_id FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE t.name=?)")
        params.append(tag)
    if filt == "review": where.append("review=1")
    elif filt == "fav": where.append("favorite=1")

    notes = db.execute(f"SELECT * FROM notes WHERE {' AND '.join(where)} ORDER BY updated_at DESC", params).fetchall()
    all_tags = db.execute("""SELECT t.name, COUNT(nt.note_id) c FROM tags t
        LEFT JOIN note_tags nt ON nt.tag_id=t.id GROUP BY t.id ORDER BY t.name""").fetchall()

    tag_map = {}
    for row in db.execute("SELECT nt.note_id, t.name FROM note_tags nt JOIN tags t ON t.id=nt.tag_id"):
        tag_map.setdefault(row["note_id"], []).append(row["name"])

    return render_template("notas.html", notes=notes, all_tags=all_tags,
                           tag_map=tag_map, q=q, tag=tag, filt=filt)

@app.route("/notas/nova", methods=["POST"])
def note_create():
    db = get_db()
    cur = db.execute("INSERT INTO notes(title, content) VALUES ('Sem título','') RETURNING id")
    note_id = cur.fetchone()["id"]
    db.commit()
    return redirect(url_for("note_editor", note_id=note_id))

@app.route("/notas/<int:note_id>")
def note_editor(note_id):
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    if not note: abort(404)
    tags = [r["name"] for r in db.execute(
        "SELECT t.name FROM tags t JOIN note_tags nt ON nt.tag_id=t.id WHERE nt.note_id=?",
        (note_id,))]
    all_tags = [r["name"] for r in db.execute("SELECT name FROM tags ORDER BY name")]
    areas = db.execute("SELECT id, name FROM areas ORDER BY name").fetchall()
    return render_template("nota_editor.html", note=note, tags=tags,
                           all_tags=all_tags, areas=areas)

@app.route("/notas/<int:note_id>/save", methods=["POST"])
def note_save(note_id):
    db = get_db()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    content = data.get("content") or ""
    favorite = 1 if data.get("favorite") else 0
    review = 1 if data.get("review") else 0
    tags = data.get("tags") or []

    db.execute("""UPDATE notes SET title=?, content=?, favorite=?, review=?,
                  updated_at=CURRENT_TIMESTAMP WHERE id=?""",
               (title or "Sem título", content, favorite, review, note_id))
    db.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
    for name in tags:
        name = name.strip()
        if not name: continue
        row = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        if row:
            tid = row["id"]
        else:
            tag_result = db.execute("INSERT INTO tags(name) VALUES (?) RETURNING id", (name,))
            tid = tag_result.fetchone()["id"]
        db.execute("INSERT INTO note_tags(note_id,tag_id) VALUES (?,?) ON CONFLICT DO NOTHING", (note_id, tid))
    db.commit()
    return jsonify({"ok": True, "saved_at": datetime.now().strftime("%H:%M:%S")})

@app.route("/notas/<int:note_id>/delete", methods=["POST"])
def note_delete(note_id):
    db = get_db()
    db.execute("DELETE FROM notes WHERE id=?", (note_id,))
    db.commit()
    return redirect(url_for("notas"))

@app.route("/notas/<int:note_id>/transform/task", methods=["POST"])
def note_to_task(note_id):
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    if not note: abort(404)
    area_id = request.form.get("area_id", type=int)
    if not area_id:
        flash("Selecione uma área.", "error")
        return redirect(url_for("note_editor", note_id=note_id))
    db.execute("""INSERT INTO tasks(area_id,title,description,priority,due_date)
                  VALUES (?,?,?,?,?)""", (
        area_id, note["title"] or "Tarefa da anotação",
        (note["content"] or "")[:2000],
        request.form.get("priority","medium"),
        request.form.get("due_date") or None))
    db.commit()
    flash("Tarefa criada a partir da anotação (original preservada).", "ok")
    return redirect(url_for("note_editor", note_id=note_id))

@app.route("/notas/<int:note_id>/transform/area", methods=["POST"])
def note_to_area(note_id):
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    if not note: abort(404)
    name = request.form.get("name","").strip() or note["title"] or "Nova área"
    desc = request.form.get("description","").strip() or (note["content"] or "")[:300]
    db.execute("INSERT INTO areas(name, description) VALUES (?,?)", (name, desc))
    db.commit()
    flash("Área criada a partir da anotação (original preservada).", "ok")
    return redirect(url_for("note_editor", note_id=note_id))

if __name__ == "__main__":
    app.run(debug=True, port=5000)
