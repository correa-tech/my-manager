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

## Publicar no PythonAnywhere

1. No PythonAnywhere, abra **Files** e clone o repositório:

	```bash
	git clone https://github.com/correa-tech/my-manager.git
	cd my-manager
	```

2. No **Consoles > Bash**, crie o ambiente virtual:

	```bash
	python3.10 -m venv ~/.virtualenvs/my-manager
	source ~/.virtualenvs/my-manager/bin/activate
	pip install -r requirements.txt
	```

3. Em **Web > Add a new web app**, escolha **Manual configuration** e a mesma versão do Python.
4. Em **Virtualenv**, informe:

	```text
	/home/SEU_USUARIO/.virtualenvs/my-manager
	```

5. Em **Code**, configure:

	```text
	Source code: /home/SEU_USUARIO/my-manager
	Working directory: /home/SEU_USUARIO/my-manager
	```

6. Abra o arquivo WSGI indicado pelo PythonAnywhere e substitua o conteúdo por:

	```python
	import sys
	sys.path.insert(0, "/home/SEU_USUARIO/my-manager")
	from wsgi import application
	```

7. Clique em **Reload**. O endereço será parecido com `https://SEU_USUARIO.pythonanywhere.com`.

No PythonAnywhere, não configure `DATABASE_URL`: a aplicação usará `personal.db` com SQLite. Para manter os dados, não apague esse arquivo e faça backups periódicos.

## Estrutura

- `app.py`: rotas e regras da aplicação.
- `db.py`: conexão PostgreSQL ou fallback SQLite.
- `schema.sql`: schema SQLite local.
- `schema.postgres.sql`: schema PostgreSQL de produção.
- `templates/`: páginas Jinja2.
- `static/`: estilos.