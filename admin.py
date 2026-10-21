"""
Herramienta de administración del mock (lo que en Brightspace se hace desde Admin Tools).

Ejemplos:
    python admin.py register-app --name EduTrace --redirect-uri http://localhost:8000/auth/brightspace/callback \
        --scopes "users:own_profile:read enrollment:own_enrollment:read dropbox:folders:read"
    python admin.py register-s2s --name "EduTrace sync" --jwks-url http://localhost:8000/.well-known/jwks.json \
        --scopes "enrollment:orgunit:read dropbox:folders:read" --service-user svc_edutrace
    python admin.py list-apps
    python admin.py delete-app <client_id>
    python admin.py users
    python admin.py reset            # borra TODOS los datos y vuelve a cargar los de demostración
"""
import argparse
import shutil
import sys

from app import apps, seed
from app.config import Settings
from app.db import init_db, transaction


def _prepare(settings: Settings) -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    init_db(settings.db_path)
    seed.seed_demo_if_empty(settings)


def main() -> int:
    parser = argparse.ArgumentParser(description="Administración del mock de Brightspace")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("register-app", help="Registrar una app Authorization Code (usuarios interactivos)")
    p.add_argument("--name", required=True)
    p.add_argument("--redirect-uri", required=True, help="Debe coincidir EXACTAMENTE con la que use el cliente")
    p.add_argument("--scopes", required=True, help="Separados por espacios, entre comillas")
    p.add_argument("--lifetime", type=int, default=3600, help="Vida del access token en segundos (1800-72000)")
    p.add_argument("--no-refresh", action="store_true", help="No emitir refresh tokens")
    p.add_argument("--no-consent", action="store_true", help="No pedir consentimiento al usuario")

    p = sub.add_parser("register-s2s", help="Registrar una app Client Credentials (servidor a servidor)")
    p.add_argument("--name", required=True)
    p.add_argument("--jwks-url", required=True, help="URL donde la app publica sus claves públicas (JWKS)")
    p.add_argument("--scopes", required=True)
    p.add_argument("--service-user", default="svc_edutrace")
    p.add_argument("--lifetime", type=int, default=3600)

    sub.add_parser("list-apps", help="Listar apps registradas")
    p = sub.add_parser("delete-app", help="Eliminar una app")
    p.add_argument("client_id")
    sub.add_parser("users", help="Listar usuarios de demostración")
    sub.add_parser("reset", help="Borrar todos los datos y recargar la demo")

    args = parser.parse_args()
    settings = Settings()

    if args.command == "reset":
        if settings.data_dir.exists():
            shutil.rmtree(settings.data_dir)
        _prepare(settings)
        print(f"Datos reiniciados en {settings.data_dir}. Contraseña de demo: {seed.demo_password()}")
        return 0

    _prepare(settings)
    try:
        if args.command == "register-app":
            client_id, secret = apps.register_authorization_code_app(
                settings, name=args.name, redirect_uri=args.redirect_uri, scopes=args.scopes,
                lifetime=args.lifetime, refresh=not args.no_refresh, consent=not args.no_consent)
            print("App registrada (Authorization Code).")
            print(f"  client_id:     {client_id}")
            print(f"  client_secret: {secret}")
            print("  Guarda el secreto ahora: no se puede volver a mostrar.")
        elif args.command == "register-s2s":
            client_id = apps.register_client_credentials_app(
                settings, name=args.name, jwks_url=args.jwks_url, scopes=args.scopes,
                service_username=args.service_user, lifetime=args.lifetime)
            print("App registrada (Client Credentials).")
            print(f"  client_id: {client_id}")
            print(f"  aud que debe llevar la aserción JWT: {settings.token_endpoint}")
        elif args.command == "list-apps":
            for app in apps.list_apps(settings):
                print(f"- {app['name']} [{app['grant_type']}] client_id={app['client_id']}")
                print(f"    scopes: {app['scopes']}")
                print(f"    redirect_uri: {app['redirect_uri']}  jwks_url: {app['jwks_url']}")
        elif args.command == "delete-app":
            print("Eliminada." if apps.delete_app(settings, args.client_id) else "No existe esa app.")
        elif args.command == "users":
            with transaction(settings.db_path) as conn:
                rows = conn.execute(
                    """SELECT u.id, u.username, u.first_name, u.last_name, r.name AS org_role,
                              (SELECT GROUP_CONCAT(e.org_unit_id || ':' || er.name, ', ') FROM enrollments e
                               JOIN roles er ON er.id = e.role_id WHERE e.user_id = u.id) AS courses
                       FROM users u JOIN roles r ON r.id = u.org_role_id ORDER BY u.id""").fetchall()
            for r in rows:
                print(f"{r['id']:>5}  {r['username']:<14} {r['first_name']} {r['last_name']:<10} "
                      f"[{r['org_role']}]  cursos: {r['courses'] or '-'}")
            print(f"\nContraseña de todos los usuarios con login: {seed.demo_password()}")
    except apps.RegistrationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
