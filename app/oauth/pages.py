"""
Páginas HTML del flujo de autorización (login, consentimiento y errores).

Son deliberadamente genéricas: no copian la marca ni el diseño de D2L. Dicen claramente que es un
entorno de pruebas para que nadie las confunda con el Brightspace real.
"""
from html import escape

_STYLE = """
body{font-family:system-ui,sans-serif;background:#f2f4f7;color:#1d2433;margin:0;display:grid;
     place-items:center;min-height:100vh;padding:16px;box-sizing:border-box}
.card{background:#fff;border:1px solid #d7dce4;border-radius:12px;padding:28px;max-width:420px;width:100%;
      box-shadow:0 4px 18px rgba(0,0,0,.06)}
.badge{display:inline-block;background:#fff3cd;color:#7a5b00;border:1px solid #f1d27a;border-radius:999px;
       font-size:12px;padding:3px 10px;margin-bottom:12px}
h1{font-size:22px;margin:0 0 6px} p{color:#4a5568;font-size:14px;line-height:1.5}
label{display:block;font-size:13px;font-weight:600;margin:14px 0 4px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #c5ccd6;border-radius:8px;font-size:15px}
button{margin-top:18px;padding:10px 16px;border-radius:8px;border:0;font-size:15px;cursor:pointer}
.primary{background:#2554c7;color:#fff;width:100%} .secondary{background:#e7ebf1;color:#1d2433}
.row{display:flex;gap:10px} .row button{flex:1}
.error{background:#fdecea;color:#8a1c12;border-radius:8px;padding:10px 12px;font-size:14px}
ul{padding-left:18px;font-size:14px} code{background:#eef1f6;padding:1px 5px;border-radius:4px}
"""

_BADGE = '<span class="badge">MOCK de Brightspace · entorno de pruebas, no es D2L</span>'


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{_STYLE}</style></head>"
            f"<body><main class='card'>{_BADGE}{body}</main></body></html>")


def login_page(*, request_query: str, csrf: str, error: str = "") -> str:
    error_html = f"<p class='error'>{escape(error)}</p>" if error else ""
    return _page("Iniciar sesión", f"""
<h1>Iniciar sesión</h1>
<p>Ingresa con un usuario del mock para continuar.</p>
{error_html}
<form method="post" action="/oauth2/auth/login">
  <input type="hidden" name="request" value="{escape(request_query)}">
  <input type="hidden" name="csrf" value="{escape(csrf)}">
  <label for="username">Usuario</label>
  <input id="username" name="username" autocomplete="username" required autofocus>
  <label for="password">Contraseña</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  <button class="primary" type="submit">Iniciar sesión</button>
</form>""")


def consent_page(*, app_name: str, user_name: str, scopes: list[str], request_query: str, csrf: str) -> str:
    items = "".join(f"<li><code>{escape(s)}</code></li>" for s in scopes)
    return _page("Autorizar aplicación", f"""
<h1>Autorizar a {escape(app_name)}</h1>
<p>Hola, {escape(user_name)}. <b>{escape(app_name)}</b> quiere acceder a tu cuenta con estos permisos:</p>
<ul>{items}</ul>
<form method="post" action="/oauth2/auth/consent">
  <input type="hidden" name="request" value="{escape(request_query)}">
  <input type="hidden" name="csrf" value="{escape(csrf)}">
  <div class="row">
    <button class="secondary" type="submit" name="decision" value="deny">Cancelar</button>
    <button class="primary" type="submit" name="decision" value="allow">Permitir</button>
  </div>
</form>""")


def error_page(message: str) -> str:
    return _page("Error de autorización", f"""
<h1>No se puede continuar</h1>
<p class="error">{escape(message)}</p>
<p>Esta solicitud no se redirige de vuelta a la aplicación porque su <code>client_id</code> o su
<code>redirect_uri</code> no son válidos.</p>""")
