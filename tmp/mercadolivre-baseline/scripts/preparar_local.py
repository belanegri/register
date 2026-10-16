"""Inicializa PostgreSQL portátil para desenvolvimento. Nunca substitui .env ou cluster."""
import json
import os
import ctypes
import sys
from pathlib import Path
import secrets
import subprocess

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
# initdb para Windows precisa de caminho ASCII durante o bootstrap UTF-8.
buffer = ctypes.create_unicode_buffer(32768)
if not ctypes.windll.kernel32.GetShortPathNameW(str(ROOT), buffer, len(buffer)):
    raise SystemExit("Nao foi possivel obter o caminho curto do projeto.")
ROOT = Path(buffer.value)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOCAL = ROOT / ".local"
BIN = LOCAL / "pgsql" / "bin"
DATA = LOCAL / "pgdata"
PORT = 5433


def run(*args):
    if Path(args[0]).name == "pg_ctl.exe":
        with (LOCAL / "pg_ctl.log").open("ab") as log:
            subprocess.run([str(x) for x in args], stdout=log, stderr=log,
                check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return
    result = subprocess.run([str(x) for x in args], capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    print(result.stdout.decode("utf-8", errors="replace"))
    if result.returncode:
        print(result.stderr.decode("utf-8", errors="replace"))
        raise SystemExit(result.returncode)


def main():
    if not (BIN / "initdb.exe").exists():
        raise SystemExit("Extraia os binários oficiais em .local/pgsql antes de continuar.")
    if (ROOT / ".env").exists():
        raise SystemExit("Configuração existente preservada. Use scripts/iniciar.ps1.")
    if DATA.exists():
        raise SystemExit("Cluster existente preservado. Consulte o README para a configuração manual.")
    LOCAL.mkdir(exist_ok=True)
    admin_password = secrets.token_urlsafe(36)
    app_password = secrets.token_urlsafe(36)
    password_file = LOCAL / "initdb-password.tmp"
    password_file.write_text(admin_password, encoding="utf-8")
    try:
        run(BIN / "initdb.exe", "-D", DATA, "-U", "postgres", "-E", "UTF8",
            "--locale=C", "--auth=scram-sha-256", f"--pwfile={password_file}")
    finally:
        password_file.unlink(missing_ok=True)
    with (DATA / "postgresql.conf").open("a", encoding="utf-8") as config:
        config.write(f"\n# PontoCar: acesso somente nesta maquina\nlisten_addresses = '127.0.0.1'\nport = {PORT}\n")
    (LOCAL / "postgres-admin.json").write_text(json.dumps({"user": "postgres", "password": admin_password,
        "host": "127.0.0.1", "port": PORT}), encoding="utf-8")
    run(BIN / "pg_ctl.exe", "-D", DATA, "-l", LOCAL / "postgres.log", "-w", "start")
    with psycopg.connect(host="127.0.0.1", port=PORT, user="postgres", password=admin_password,
                        dbname="postgres", autocommit=True) as conn:
        # CREATEDB permite somente a criação do banco temporário pelo runner de testes local.
        conn.execute(sql.SQL("CREATE ROLE pontocar LOGIN CREATEDB PASSWORD {}").format(sql.Literal(app_password)))
        conn.execute("CREATE DATABASE pontocar OWNER pontocar ENCODING 'UTF8'")
    (ROOT / ".env").write_text(
        f"DEBUG=True\nSECRET_KEY={secrets.token_urlsafe(64)}\n"
        f"DATABASE_URL=postgresql://pontocar:{app_password}@127.0.0.1:{PORT}/pontocar\n"
        "ALLOWED_HOSTS=localhost,127.0.0.1\n"
        "CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000\n", encoding="utf-8")
    print("Banco pontocar criado na porta 5433. Credenciais gravadas apenas nos arquivos locais ignorados.")


if __name__ == "__main__":
    main()
