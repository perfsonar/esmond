import os
import optparse
from logging.handlers import SysLogHandler
import ConfigParser

from essnmp.error import ConfigError

def get_config_path():
    if os.environ.has_key('ESXSNMP_CONF'):
        conf = sys.environ('ESXSNMP_CONF')
    else:
        conf = './esxsnmp.conf'

    return conf

def get_config(config_file, opts):
    if not os.path.exists(config_file):
        raise ConfigError("config file not found: " % config_file)

    try:
        conf = ESxSNMPConfig(config_file)
    except ConfigParser.Error, e:
        raise ConfigError("unable to parse config: %s" % e)

    # the command line overrides the config file
    if opts.pid_file:
        conf.pid_file = opts.pid_file

    return conf

def get_opt_parser(default_config_file=None, default_pid_file=None):
    oparse = optparse.OptionParser()
    oparse.add_option("-d", "--debug", dest="debug", action="store_true",
            default=False)
    oparse.add_option("-f", "--config-file", dest="config_file",
            default=default_config_file)
    oparse.add_option("-p", "--pid-file", dest="pid_file",
            default=default_pid_file)

    return oparse

class ESxSNMPConfig(object):
    def __init__(self, file):
        self.file = file

        self.db_uri = None
        self.tsdb_root = None
        self.error_email_to = None
        self.error_email_subject = None
        self.error_email_from = None
        self.traceback_dir = None
        self.syslog_facility = None
        self.syslog_verbosity = 0
        self.pid_file = None

        self.send_error_email = False

        self.read_config()
        self.validate_config()

    def read_config(self):
        """ read in config from INI-style file, requiring section header 'main'"""
        cfg = ConfigParser.ConfigParser()
        cfg.read(self.file)
        for opt in ('db_uri', 'tsdb_root', 'error_email_to',
                'error_email_subject', 'error_email_from', 'traceback_dir',
                'syslog_facility', 'syslog_verbosity', 'pid_file'):
            setattr(self, opt, cfg.get("main", opt))

    def validate_config(self):
        for attr in ('tsdb_root', 'db_uri'):
            if getattr(self, attr) == None:
                raise ConfigError("invalid config: %s: %s must be specified",
                        self.file, attr)

        if self.error_email_to is not None \
                and self.error_email_subject is not None \
                and self.error_email_from is not None:
            self.send_error_email = True

        if self.syslog_facility is not None:
            if not SysLogHandler.facility_names.has_key(self.syslog_facility):
                raise ConfigError("invalid config: %s syslog facility is unknown" % self.syslog_facility)

            self.syslog_facility = SysLogHandler.facility_names[self.syslog_facility]

        if self.traceback_dir is not None:
            if not os.path.isdir(self.traceback_dir):
                raise ConfigError("invalid config: traceback_dir %s does not exist")


