class EsmondError(Exception):
    """Base class for EsmondErrors."""
    pass

class ConfigError(EsmondError):
    """Unable to find config file."""
    pass

class BadQuery(EsmondError):
    pass
