class ESxSNMPError(Exception):
    """Base class for ESxSNMPErrors."""
    pass

class ConfigError(ESxSNMPError):
    """Unable to find config file."""
    pass
