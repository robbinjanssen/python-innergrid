"""Exceptions for the Innergrid client."""


class InnergridError(Exception):
    """Generic Innergrid exception."""


class InnergridConnectionError(InnergridError):
    """The connection to the MQTT broker failed or was lost."""


class InnergridAuthError(InnergridConnectionError):
    """The MQTT broker rejected the username or password."""


class InnergridTimeoutError(InnergridError):
    """No data arrived in time."""
