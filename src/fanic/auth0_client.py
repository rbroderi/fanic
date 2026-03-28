from dataclasses import dataclass

from authlib.common.security import generate_token
from authlib.integrations.requests_client import OAuth2Session

from fanic.settings import FanicSettings


@dataclass(frozen=True, slots=True)
class Auth0Config:
    domain: str
    client_id: str
    client_secret: str
    callback_url: str
    logout_return_url: str
    audience: str
    connection: str
    superadmin_email: str
    scope: str = "openid profile email"

    @property
    def authorization_endpoint(self) -> str:
        return f"https://{self.domain}/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"https://{self.domain}/oauth/token"

    @property
    def userinfo_endpoint(self) -> str:
        return f"https://{self.domain}/userinfo"

    @property
    def logout_endpoint(self) -> str:
        return f"https://{self.domain}/v2/logout"


def auth0_config_from_settings(settings: FanicSettings) -> Auth0Config:
    return Auth0Config(
        domain=settings.auth0_domain.strip(),
        client_id=settings.auth0_client_id.strip(),
        client_secret=settings.auth0_client_secret.strip(),
        callback_url=settings.auth0_callback_url.strip(),
        logout_return_url=settings.auth0_logout_return_url.strip(),
        audience=settings.auth0_audience.strip(),
        connection=settings.auth0_connection.strip(),
        superadmin_email=settings.auth0_superadmin_email.strip().lower(),
    )


def build_oauth_client(config: Auth0Config) -> OAuth2Session:
    return OAuth2Session(
        client_id=config.client_id,
        client_secret=config.client_secret,
        scope=config.scope,
        code_challenge_method="S256",
    )


def new_code_verifier() -> str:
    return generate_token(48)
