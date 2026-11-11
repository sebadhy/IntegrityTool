"""Offline local-account administration. No default credentials or public signup."""
from __future__ import annotations

import argparse
import getpass
from pathlib import Path


def main():
    from .runtime_secrets import load_secret_files
    load_secret_files()
    parser = argparse.ArgumentParser(description="Administrar usuarios locales del equipo autorizado.")
    parser.add_argument("command", choices=["init-admin", "create", "reset-password", "disable", "unlock", "revoke-all"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--name")
    parser.add_argument("--role", choices=["admin", "reviewer", "reader"], default="reviewer")
    parser.add_argument("--password-file", type=Path, help="Archivo protegido; nunca una contraseña en argumentos.")
    args = parser.parse_args()
    if args.command != "revoke-all" and not args.username:
        parser.error("Indique el nombre de usuario.")
    from .analyzer.storage_settings import create_review_store
    from .local_auth import LocalAuth
    store = create_review_store(Path(__file__).resolve().parents[1], initialize=False)
    try:
        auth = LocalAuth(store.engine, initialize=args.command == "init-admin")
        password = None
        if args.command in {"init-admin", "create", "reset-password"}:
            if args.password_file:
                password = args.password_file.read_text(encoding="utf-8").rstrip("\r\n")
            else:
                password = getpass.getpass("Contraseña (mínimo 15 caracteres): ")
                if password != getpass.getpass("Repita la contraseña: "):
                    raise ValueError("Las contraseñas no coinciden.")
        if args.command == "revoke-all":
            from sqlalchemy import delete
            from .local_auth import sessions
            with store.engine.begin() as db:
                db.execute(delete(sessions))
        elif args.command in {"init-admin", "create"}:
            auth.add_user(args.username, args.name or args.username,
                "admin" if args.command == "init-admin" else args.role, password,
                first_admin=args.command == "init-admin")
        else:
            auth.change_user(args.username, password=password, disable=args.command == "disable", unlock=args.command == "unlock")
        print("Operación completada. Las credenciales no se imprimen ni se envían al navegador.")
    except (ValueError, OSError):
        # Password-file paths and driver details can contain private information.
        raise SystemExit("No se completó la operación. Compruebe los datos, el usuario, el archivo y el estado de inicialización.") from None
    finally:
        store.close()


if __name__ == "__main__":
    main()
