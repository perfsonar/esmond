class ESxSNMPError(Exception):
    """Base class for ESxSNMPErrors."""
    pass

class ConfigError(ESxSNMPError):
    """Unable to find config file."""
    pass

class BadQuery(ESxSNMPError):
    pass

class PollerError(ESxSNMPError):
    """Problem with a poller."""
    pass
