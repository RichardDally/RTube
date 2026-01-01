"""
LDAP Authentication Service for RTube.

Provides LDAP authentication as an alternative to local authentication.
"""

import logging
from dataclasses import dataclass

from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException, LDAPBindError

logger = logging.getLogger(__name__)


@dataclass
class LDAPConfig:
    """Configuration for LDAP authentication."""

    server: str
    use_ssl: bool
    bind_dn: str
    bind_password: str
    user_base: str
    user_filter: str
    username_attribute: str

    @classmethod
    def from_env(cls, env: dict) -> "LDAPConfig | None":
        """Create LDAPConfig from environment variables.

        Returns None if LDAP is not enabled.
        """
        if env.get("RTUBE_LDAP_ENABLED", "").lower() not in ("true", "1", "yes"):
            return None

        return cls(
            server=env.get("RTUBE_LDAP_SERVER", "ldap://localhost:389"),
            use_ssl=env.get("RTUBE_LDAP_USE_SSL", "").lower() in ("true", "1", "yes"),
            bind_dn=env.get("RTUBE_LDAP_BIND_DN", ""),
            bind_password=env.get("RTUBE_LDAP_BIND_PASSWORD", ""),
            user_base=env.get("RTUBE_LDAP_USER_BASE", ""),
            user_filter=env.get("RTUBE_LDAP_USER_FILTER", "(uid={username})"),
            username_attribute=env.get("RTUBE_LDAP_USERNAME_ATTRIBUTE", "uid"),
        )


class LDAPAuthService:
    """Service for authenticating users against an LDAP server."""

    def __init__(self, config: LDAPConfig):
        """Initialize the LDAP authentication service.

        Args:
            config: LDAP configuration settings.
        """
        self.config = config
        self._server = None

    def _get_server(self) -> Server:
        """Get or create the LDAP server connection."""
        if self._server is None:
            self._server = Server(
                self.config.server,
                use_ssl=self.config.use_ssl,
                get_info=ALL,
            )
        return self._server

    def _get_bind_connection(self) -> Connection | None:
        """Create a connection using the service bind credentials.

        Returns:
            Connection object if successful, None otherwise.
        """
        try:
            conn = Connection(
                self._get_server(),
                user=self.config.bind_dn,
                password=self.config.bind_password,
                auto_bind=True,
            )
            return conn
        except LDAPException as e:
            logger.error(f"LDAP bind connection failed: {e}")
            return None

    def _find_user_dn(self, username: str) -> str | None:
        """Find the DN for a given username.

        Args:
            username: The username to search for.

        Returns:
            The user's DN if found, None otherwise.
        """
        conn = self._get_bind_connection()
        if conn is None:
            return None

        try:
            # Build the search filter with the username
            search_filter = self.config.user_filter.format(username=username)

            conn.search(
                search_base=self.config.user_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=[self.config.username_attribute],
            )

            if len(conn.entries) == 1:
                return conn.entries[0].entry_dn

            if len(conn.entries) > 1:
                logger.warning(f"Multiple LDAP entries found for username: {username}")

            return None

        except LDAPException as e:
            logger.error(f"LDAP user search failed: {e}")
            return None
        finally:
            conn.unbind()

    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate a user against the LDAP server.

        Args:
            username: The username to authenticate.
            password: The password to verify.

        Returns:
            True if authentication successful, False otherwise.
        """
        if not username or not password:
            return False

        # Find the user's DN
        user_dn = self._find_user_dn(username)
        if user_dn is None:
            logger.info(f"LDAP user not found: {username}")
            return False

        # Attempt to bind with the user's credentials
        try:
            conn = Connection(
                self._get_server(),
                user=user_dn,
                password=password,
                auto_bind=True,
            )
            conn.unbind()
            logger.info(f"LDAP authentication successful for user: {username}")
            return True

        except LDAPBindError:
            logger.info(f"LDAP authentication failed for user: {username}")
            return False
        except LDAPException as e:
            logger.error(f"LDAP authentication error for user {username}: {e}")
            return False

    def get_user_info(self, username: str) -> dict | None:
        """Get user information from LDAP.

        Args:
            username: The username to look up.

        Returns:
            Dictionary with user info if found, None otherwise.
        """
        conn = self._get_bind_connection()
        if conn is None:
            return None

        try:
            search_filter = self.config.user_filter.format(username=username)

            conn.search(
                search_base=self.config.user_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["*"],
            )

            if len(conn.entries) == 1:
                entry = conn.entries[0]
                return {
                    "dn": entry.entry_dn,
                    "username": getattr(
                        entry, self.config.username_attribute, username
                    ),
                    "attributes": dict(entry.entry_attributes_as_dict),
                }

            return None

        except LDAPException as e:
            logger.error(f"LDAP user info lookup failed: {e}")
            return None
        finally:
            conn.unbind()

    def test_connection(self) -> bool:
        """Test the LDAP connection.

        Returns:
            True if connection successful, False otherwise.
        """
        conn = self._get_bind_connection()
        if conn is None:
            return False
        conn.unbind()
        return True
