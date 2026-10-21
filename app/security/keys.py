"""
Clave RSA con la que el mock firma los access tokens.

Se genera una sola vez y se guarda en DATA_DIR/signing_key.pem para que los tokens sigan siendo
válidos si el servidor se reinicia.
"""
import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url_uint(number: int) -> str:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@dataclass
class SigningKey:
    private_key: rsa.RSAPrivateKey
    kid: str

    @property
    def public_jwk(self) -> dict:
        numbers = self.private_key.public_key().public_numbers()
        return {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": self.kid,
                "n": _b64url_uint(numbers.n), "e": _b64url_uint(numbers.e)}


def load_or_create_signing_key(path: Path) -> SigningKey:
    if path.exists():
        private_key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        path.write_bytes(pem)
        path.chmod(0o600)
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    kid = hashlib.sha256(public_der).hexdigest()[:16]
    return SigningKey(private_key=private_key, kid=kid)
