"""
Scopes de Brightspace [DOC]:

- Formato `grupo:recurso:acción`, separados por espacios.
- Comodín en recurso o acción: `users:userdata:*`.
- Lista de acciones con comas, sin espacios: `users:userdata:create,read,update`.
- El grupo no puede ser comodín, salvo el scope especial `core:*:*`.
- Los scopes pedidos deben ser un subconjunto de los registrados en la app.
"""
import re

_PART = r"[a-z0-9_]+"
_SCOPE_RE = re.compile(rf"^({_PART}):({_PART}|\*):((?:{_PART})(?:,{_PART})*|\*)$")

CORE_SCOPE = "core:*:*"


class ScopeSyntaxError(ValueError):
    pass


def parse(scope_string: str) -> list[tuple[str, str, frozenset[str]]]:
    """Convierte 'a:b:c d:e:f,g' en [(a, b, {c}), (d, e, {f, g})]. Lanza ScopeSyntaxError si algo no cuadra."""
    result = []
    for item in scope_string.split():
        if item == CORE_SCOPE:
            result.append(("core", "*", frozenset({"*"})))
            continue
        match = _SCOPE_RE.match(item)
        if not match:
            raise ScopeSyntaxError(f"scope con formato inválido: {item!r}")
        group, resource, actions = match.groups()
        if group == "core":
            raise ScopeSyntaxError("el grupo 'core' solo se admite como core:*:*")
        result.append((group, resource, frozenset(actions.split(","))))
    return result


def _covers(granted: tuple[str, str, frozenset[str]], group: str, resource: str, action: str) -> bool:
    g_group, g_resource, g_actions = granted
    return (g_group == group
            and (g_resource == "*" or g_resource == resource)
            and ("*" in g_actions or action in g_actions))


def is_subset(requested: str, registered: str) -> bool:
    """¿Cada scope pedido está cubierto por los registrados?"""
    reg = parse(registered)
    for group, resource, actions in parse(requested):
        if group == "core":
            if not any(r[0] == "core" for r in reg):
                return False
            continue
        for action in actions:
            if not any(_covers(r, group, resource, action) for r in reg):
                return False
    return True


def satisfies(granted: str, required_any: tuple[str, ...], core_grants_all: bool) -> bool:
    """¿El scope del token alcanza para alguno de los scopes que exige la ruta?"""
    try:
        parsed = parse(granted)
    except ScopeSyntaxError:
        return False
    if core_grants_all and any(p[0] == "core" for p in parsed):
        return True
    for required in required_any:
        group, resource, action = required.split(":")
        if any(_covers(p, group, resource, action) for p in parsed):
            return True
    return False
