import os
import optparse
import logging
from logging.handlers import SysLogHandler
import ConfigParser

from esxsnmp.error import ConfigError

def get_config_path():
    if os.environ.has_key('ESXSNMP_CONF'):
        conf = os.environ['ESXSNMP_CONF']
    else:
        conf = './esxsnmp.conf'

    return conf

def get_config(config_file, opts=None):
    if not os.path.exists(config_file):
        raise ConfigError("config file not found: %s" % config_file)

    try:
        conf = ESxSNMPConfig(config_file)
    except ConfigParser.Error, e:
        raise ConfigError("unable to parse config: %s" % e)

    # the command line overrides the config file
    if opts and opts.pid_dir:
        conf.pid_dir = opts.pid_dir

    return conf

def get_opt_parser(default_config_file=None, default_pid_dir=None):
    oparse = optparse.OptionParser()
    oparse.add_option("-d", "--debug", dest="debug", action="store_true",
            default=False)
    oparse.add_option("-f", "--config-file", dest="config_file",
            default=default_config_file)
    oparse.add_option("-p", "--pid-dir", dest="pid_dir",
            default=default_pid_dir)

    return oparse

class ESxSNMPConfig(object):
    def __init__(self, file):
        self.file = file

        self.agg_tsdb_root = None
        self.cassandra_pass = None
        self.cassandra_servers = []
        self.cassandra_user = None
        self.cassandra_raw_expire = None
        self.db_clear_on_testing = None
        self.db_profile_on_testing = None
        self.error_email_from = None
        self.error_email_subject = None
        self.error_email_to = None
        self.esdb_uri = None
        self.espersistd_uri = None
        self.espoll_persist_uri = None
        self.htpasswd_file = None
        self.mib_dirs = []
        self.mibs = []
        self.pid_dir = None
        self.poll_retries = 5
        self.poll_timeout = 2
        self.reload_interval = 1*10
        self.rrd_path = None
        self.send_error_email = False
        self.sql_db_engine = ''
        self.sql_db_host = ''
        self.sql_db_name = ''
        self.sql_db_password = ''
        self.sql_db_port = ''
        self.sql_db_user = ''
        self.streaming_log_dir = None
        self.syslog_facility = None
        self.syslog_priority = None
        self.traceback_dir = None
        self.tsdb_chunk_prefixes = None
        self.tsdb_root = None

        self.read_config()
        self.convert_types()

        # XXX(jdugan): validate_config is too restrictive needs to be fixed
        # self.validate_config()

    def read_config(self):
        """ read in config from INI-style file, requiring section header 'main'"""
        defaults = {}
        for v in ('ESXSNMP_ROOT', ):
            defaults[v] = os.environ.get(v)

        cfg = ConfigParser.ConfigParser(defaults)
        cfg.read(self.file)
        config_items = map(lambda x: x[0], cfg.items("main"))
        for opt in (
                'agg_tsdb_root',
                'cassandra_pass',
                'cassandra_servers',
                'cassandra_user',
                'cassandra_raw_expire',
                'db_clear_on_testing',
                'db_profile_on_testing',
                'db_uri',
                'error_email_from',
                'error_email_subject',
                'error_email_to',
                'esdb_uri',
                'espersistd_uri',
                'espoll_persist_uri',
                'htpasswd_file',
                'mib_dirs',
                'mibs',
                'pid_dir',
                'poll_retries',
                'poll_timeout',
                'reload_interval',
                'rrd_path',
                'sql_db_engine',
                'sql_db_host',
                'sql_db_name',
                'sql_db_password',
                'sql_db_port',
                'sql_db_user',
                'streaming_log_dir',
                'syslog_facility',
                'syslog_priority',
                'traceback_dir',
                'tsdb_chunk_prefixes',
                'tsdb_root',
                ):
            if opt in config_items:
                setattr(self, opt, cfg.get("main", opt))

        for key, val in cfg.items('main'):
            if key == 'db_clear_on_testing' or key == 'db_profile_on_testing':
                setattr(self, key, cfg.getboolean('main', key))
        
        self.persist_map = {}
        for key, val in cfg.items("persist_map"):
            if key == 'esxsnmp_root': # XXX(jdugan) this is probably cruft
                continue

            self.persist_map[key] = val.replace(" ", "").split(",")

        self.persist_queues = {}
        for key, val in cfg.items("persist_queues"):
            if key == 'esxsnmp_root':
                continue

            self.persist_queues[key] = val.split(':', 1)
            self.persist_queues[key][1] = int(self.persist_queues[key][1])

        if self.espoll_persist_uri:
            self.espoll_persist_uri = \
                self.espoll_persist_uri.replace(' ', '').split(',')

    def convert_types(self):
        """update_types -- convert input from config file to appropriate types"""

        if self.mib_dirs:
            self.mib_dirs = map(str.strip, self.mib_dirs.split(','))

        if self.mibs:
            self.mibs = map(str.strip, self.mibs.split(','))
        if self.cassandra_raw_expire:
            self.cassandra_raw_expire = int(self.cassandra_raw_expire)
        if self.cassandra_servers:
            self.cassandra_servers = map(str.strip, self.cassandra_servers.split(','))
        if self.poll_timeout:
            self.poll_timeout = int(self.poll_timeout)
        if self.poll_retries:
            self.poll_retries = int(self.poll_retries)
        if self.reload_interval:
            self.reload_interval = int(self.reload_interval)


        if self.error_email_to is not None \
                and self.error_email_subject is not None \
                and self.error_email_from is not None:
            self.send_error_email = True

        if self.syslog_facility is not None:
            if not SysLogHandler.facility_names.has_key(self.syslog_facility):
                raise ConfigError("invalid config: %s syslog facility is unknown" % self.syslog_facility)

            self.syslog_facility = SysLogHandler.facility_names[self.syslog_facility]

        if self.syslog_priority is None:
            syslog_priority = logging.INFO
        else:
            if not SysLogHandler.priority_names.has_key(self.syslog_priority):
                raise ConfigError("invaild config: unknown syslog_priority %s" %
                        self.syslog_priority)
            self.syslog_priority = SysLogHandler.priority_names[self.syslog_priority]

    def validate_config(self):
        for attr in ('tsdb_root', 'db_uri'):
            if getattr(self, attr) == None:
                raise ConfigError("invalid config: %s: %s must be specified",
                        self.file, attr)

        if not os.path.isdir(self.tsdb_root):
            raise ConfigError("invalid config: tsdb_root does not exist: %s" % self.tsdb_root)
        if not os.access(self.tsdb_root, os.W_OK):
            raise ConfigError("invalid config: tsdb_root %s is not writable" % self.tsdb_root)
        if self.tsdb_chunk_prefixes:
            self.tsdb_chunk_prefixes = map(str.strip,
                    self.tsdb_chunk_prefixes.split(','))
            for cdir in self.tsdb_chunk_prefixes:
                if not os.path.isdir(cdir):
                    raise ConfigError("invalid config: tsdb_chunk_prefixes doesn't exist: %s" % cdir)
                if not os.access(cdir, os.W_OK):
                    raise ConfigError("invalid config: tsdb_chunk_prefixes %s not writable" % cdir)

        if self.traceback_dir is not None:
            if not os.path.isdir(self.traceback_dir):
                raise ConfigError("invalid config: traceback_dir %s does not exist" % self.traceback_dir)
            if not os.access(self.traceback_dir, os.W_OK):
                raise ConfigError("invalid config: traceback_dir %s is not writable" % self.traceback_dir)

        if self.syslog_facility is not None:
            if not SysLogHandler.facility_names.has_key(self.syslog_facility):
                raise ConfigError("invalid config: %s syslog facility is unknown" % self.syslog_facility)

            self.syslog_facility = SysLogHandler.facility_names[self.syslog_facility]

        if self.syslog_priority is None:
            syslog_priority = logging.INFO
        else:
            if not SysLogHandler.priority_names.has_key(self.syslog_priority):
                raise ConfigError("invaild config: unknown syslog_priority %s" %
                        self.syslog_priority)
            self.syslog_priority = SysLogHandler.priority_names[self.syslog_priority]

        errors = []
        for oidset, queues in self.persist_map.iteritems():
            for queue in queues:
                if not self.persist_queues.has_key(queue):
                    errors.append("%s for %s" % (queue, oidset))

        if errors:
            raise ConfigError("unknown persist queue(s): %s" \
                    % ", ".join(errors))


