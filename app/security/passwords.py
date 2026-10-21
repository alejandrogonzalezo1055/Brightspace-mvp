"""Hash de contraseñas con PBKDF2-HMAC-SHA256 (librería estándar)."""
import base64
import hashlib
import hmac
import secrets

ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def check_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
    # compare_digest compara en tiempo constante: no filtra cuántos bytes coinciden.
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def sha256_hex(value: str) -> str:
    """Para guardar códigos, tokens y sesiones: en la base solo queda el hash."""
    return hashlib.sha256(value.encode()).hexdigest()
