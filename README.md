# Gestão pessoal

Aplicação local de tarefas, agenda e anotações com Flask.

## Rodar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Sem `DATABASE_URL`, a aplicação usa SQLite em `personal.db`. Os dados permanecem no computador local.

## Publicar no Render com PostgreSQL

1. Publique esta pasta em um repositório do GitHub.
2. No Render, crie um novo Blueprint apontando para o repositório.
3. O arquivo `render.yaml` cria o serviço web e o banco PostgreSQL.
4. O Render fornece `DATABASE_URL` automaticamente ao serviço.
5. O comando de produção usado será `gunicorn app:app`.

O banco PostgreSQL é usado automaticamente quando `DATABASE_URL` começa com `postgres://` ou `postgresql://`. O schema é criado na primeira inicialização.

## Estrutura

- `app.py`: rotas e regras da aplicação.
- `db.py`: conexão PostgreSQL ou fallback SQLite.
- `schema.sql`: schema SQLite local.
- `schema.postgres.sql`: schema PostgreSQL de produção.
- `templates/`: páginas Jinja2.
- `static/`: estilos.