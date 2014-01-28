import os
import os.path
import sys
import ctypes
import datetime
import time
import logging
import logging.handlers
import smtplib
import syslog
from email.MIMEText import MIMEText
from StringIO import StringIO
import traceback
import inspect
import tempfile
from optparse import OptionParser

from django.utils.timezone import utc, make_aware

proctitle = None

class LoggerIO(object):
    """file like class which logs writes to syslog module
    
    This is intended to catch errant output to stdout or stderr inside daemon
    processes and log it to syslog rather than crashing the program."""

    def __init__(self, name, facility):
        self.name = name
        syslog.openlog(name, syslog.LOG_PID, facility)

    def write(self, buf):
        syslog.syslog(syslog.LOG_ERR, "captured: " + buf)

def daemonize(name, piddir=None, logfile=None, log_stdout_stderr=None):
    '''Forks the current process into a daemon.
        derived from the ASPN recipe:
            http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012
    '''

    pidfile = os.path.join(piddir, name + ".pid")

    if not os.path.exists(os.path.dirname(pidfile)):
        try:
            os.makedirs(os.path.dirname(pidfile))
        except:
            raise Exception("pid file directory does not exist %s.  aborting." % pidfile) 
    if not os.access(os.path.dirname(pidfile), os.W_OK):
        raise Exception("pid file directory %s is not writable.  aborting." % pidfile) 

    if os.path.exists(pidfile):
        f = open(pidfile)
        pid = f.readline()
        f.close()
        pid = int(pid.strip())
        try:
            os.kill(pid, 0)
        except:
            pass
        else:
            raise Exception("process still running as pid %d.  aborting." % pid) 

    # Do first fork.
    try: 
        pid = os.fork() 
        if pid > 0: sys.exit(0) # Exit first parent.
    except OSError, e: 
        sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)
        
    # Decouple from parent environment.
    os.chdir("/") 
    os.umask(0) 
    os.setsid() 
    
    # Do second fork.
    try: 
        pid = os.fork() 
        if pid > 0: sys.exit(0) # Exit second parent.
    except OSError, e: 
        sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
        sys.exit(1)
    

    pid = str(os.getpid())

    if pidfile:
        f = file(pidfile,'w')
        f.write("%s\n" % pid)
        f.close()
  
    # close stdin, stdout, stderr
    # XXX might not be 100% portable.
    for fd in range(3):
        os.close(fd)

    # Redirect standard file descriptors.
    if logfile:
        os.open(logfile, os.O_RDWR|os.O_CREAT)
        os.dup2(0, sys.stdout.fileno())
        os.dup2(0, sys.stderr.fileno())

    if log_stdout_stderr:
        sys.stdout = sys.stderr = LoggerIO(name, log_stdout_stderr)


def setproctitle(name):
    """Set the title of the current process to name.  This also sets the
    proctitle global variable.

    XXX Presently only works on FreeBSD => 6.x.  Silently fails elsewhere.
    """
    if os.uname()[0] == 'FreeBSD':
        for libc_ver in range(7, 5, -1):
            libc_file = '/lib/libc.so.%d' % libc_ver
            if os.path.exists(libc_file):
                libc = ctypes.CDLL(libc_file)
                libc.setproctitle("-" + name + "\0")
                break

    global proctitle
    proctitle = name

def init_logging(name, facility, level=logging.INFO,
        format="%(name)s [%(process)d] %(message)s", debug=False):

    log = logging.getLogger()
    log.setLevel(level)
    # NOTE: /dev/log appears to be more costly at least on FreeBSD
    if os.uname()[0] == 'FreeBSD':
        syslog = logging.handlers.SysLogHandler(('localhost', 514), facility=facility)
    elif os.uname()[0] == 'Darwin':
        syslog = logging.handlers.SysLogHandler('/var/run/syslog', facility=facility)
    else:
        syslog = logging.handlers.SysLogHandler("/dev/log", facility=facility)
    syslog.setFormatter(logging.Formatter(format))
    syslog.addFilter(logging.Filter(name=name))
    log.addHandler(syslog)

    if debug:
        log.setLevel(logging.DEBUG)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(format))
        log.addHandler(console)

def get_logger(name):
    return logging.getLogger(name)

def send_mail(sender, to, subject, body, relay='localhost'):
    if type(to) != list and type(to) != tuple:
        to = [to]

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['To'] = ", ".join(to)
    msg['From'] = sender
    srv = smtplib.SMTP()
    srv.connect(host=relay)
    srv.sendmail(sender, to, msg.as_string())
    srv.close()

class ExceptionHandler(object):
    """Flexible exception hook with detailed messages.

    This exception hook reports the exception encountered along with a
    traceback including the local variables in each frame.  This exception
    hook is inspired by cgitb but behaves a bit differently.

    If 'ignore' is specified it is contains a list of exceptions to ignore.

    If 'email' is specified it is a dict containing: 'subject': the subject of
    the email 'from': who the email is from, and 'to': a list of recipients.
    Optionally if the dict contains 'relay' it is used as the host name to
    use as an SMTP relay,, otherwise this defaults to 'localhost'.

    If 'log' is specified it is a logging.Logger instance or something that
    defines a method named 'error' to handle error message.
    """

    def __init__(self, ignore=[], email=None, log=None, output_dir=None):
        self.ignore = ignore
        self.email = email
        self.log = log
        self.output_dir = output_dir

        self.e_val = None

        if not os.path.isdir(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except Exception, e:
                print >>sys.stderr, "unable to create traceback directory: %s: %s" % (self.output_dir, str(e))
                raise

    def __call__(self, *args):
        self.handle(*args)

    def install(self):
        sys.excepthook = self

    def handle(self, *args):
        try:
            if len(args) == 3:
                e_info = args
            else:
                e_info = sys.exc_info()

            if e_info[0] in self.ignore:
                return

            body = ''

            if len(e_info) > 1:
                e_val = repr(e_info[1])

                if isinstance(e_info[1], str):
                    e_name = e_info[1]
                elif hasattr(e_info[1], '__class__'):
                    e_name = e_info[1].__class__.__name__
                else:
                    e_name = e_val
            else:
                e_val = "<undefined>"
                e_name = e_val

            log_msg = "exception=%s" % e_name

            pid = os.getpid()

            global proctitle

            body += "Process %d (%s): %s\n\n" % (pid, proctitle, e_val)
            body += "XX: %s" % (str(e_info[1]))
            log_msg += " pid=%d process_name=%s" % (pid,proctitle)

            body += self.format(*e_info)

            if self.email is not None:
                subj = "%s: %s" % (self.email['subject'], log_msg)
                if self.email.has_key('relay'):
                    relay = self.email['relay']
                else:
                    relay = 'localhost'

                try:
                    send_mail(self.email['from'], self.email['to'], subj, body,
                            relay=relay)
                except Exception, e:
                    msg = "unable to send email: %s" % (repr(e))
                    body += msg + "\n"

                    if self.log:
                        self.log.error(msg)

            if self.output_dir is not None:
                log_id = self.log_to_dir(log_msg, body)
                log_msg += " log_id=%s" % (log_id)

            if self.log is not None:
                self.log.error(log_msg)
        except Exception, e:
            f = open("/tmp/exclog", "a")
            f.write(time.ctime())
            f.write("\n")
            f.write(str(e))
            f.close()

    def format(self, e_type, e_val, tb, context_lines=5):
        s = ''
        for (frame, filename, lineno, func, ctx, idx) in \
                inspect.getinnerframes(tb, context_lines):
            (args,varargs,varkw,locals) = inspect.getargvalues(frame)
            if idx is None:
                # sometimes idx is None, see ctx comments below
                # report what info we can
                idx = 0

            s += "%s:%s %s%s\n" % (filename, lineno+idx,
                    func,inspect.formatargvalues(args, varargs, varkw, locals))
    
            i = lineno
            s += "\n"
            if ctx is None:
                # sometimes ctx is None
                # report what info we can
                # seems to be happening with some eggs
                s += "     [ no context available ]\n\n"
                continue
            for line in ctx:
                if i == lineno+idx:
                    s += "====>"
                else:
                    s += "     "
                s += "%4d %s" % (i, line)
                i += 1
    
            s += "\n"
            linelen = 0
            s += "    Locals:\n"
            for (k,v) in locals.items():
                s += "         %s=%s\n" % (k,repr(v))
            s += "\n\n"
    
        return s

    def log_to_dir(self, log_msg, body):
        # the use of unqualified excepts here is intentional, we don't want
        # anything to obscure our chances of reporting a failure
        if not os.path.exists(self.output_dir):
            try:
                os.mkdir(self.output_dir)
            except:
                return None

        try:
            (fd,name) = tempfile.mkstemp(dir=self.output_dir, prefix="traceback_")
            f = os.fdopen(fd, 'w')
            f.write(body)
            f.close()
        except:
            return None

        return name

def setup_exc_handler(name, config, ignore=[SystemExit]):
    email = None
    if config.send_error_email:
        email = {}
        email['from'] = config.error_email_from
        email['to'] = config.error_email_to
        email['subject'] = config.error_email_subject

    log = None
    if config.syslog_facility is not None:
        log = get_logger(name)

    output_dir = None
    if config.traceback_dir is not None:
        output_dir = config.traceback_dir

    return ExceptionHandler(ignore=ignore, email=email, log=log, output_dir=output_dir)

def run_server(callable_, name, config):
    exc_hook = setup_exc_handler(name, config)
    exc_hook.install()

    daemonize(name, config.run_dir, log_stdout_stderr=exc_hook.log)

    setproctitle(name)

    callable_()

def remove_metachars(name):
    """remove troublesome metacharacters from ifDescr"""
    for (char,repl) in (("/", "_"), (" ", "_")):
        name = name.replace(char, repl)
    return name

_atencode_safe = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXWZ0123456789_.-'
_atencode_map = {}
for i, c in (zip(xrange(256), str(bytearray(xrange(256))))):
    _atencode_map[c] = c if c in _atencode_safe else '@{:02X}'.format(i)

_atencode_unsafe = ' $&+,/:;=?@\x7F'
_atencode_map_minimal = {}
for i, c in (zip(xrange(256), str(bytearray(xrange(256))))):
    _atencode_map_minimal[c] = c if (i > 31 and i < 128 and c not in _atencode_unsafe) else '@{:02X}'.format(i)

_atdecode_map = {}
for i in xrange(256):
    _atdecode_map['{:02X}'.format(i)] = chr(i)
    _atdecode_map['{:02x}'.format(i)] = chr(i)

def atencode(s, minimal=False):
    if minimal:
        return ''.join(map(_atencode_map_minimal.__getitem__, s))
    else:
        return ''.join(map(_atencode_map.__getitem__, s))

def atdecode(s):
    parts = s.split('@')
    r = [parts[0]]

    for part in parts[1:]:
        try:
            r.append(_atdecode_map[part[:2]])
            r.append(part[2:])
        except KeyError:
            append('@')
            append(part)

    return ''.join(r)

class NagiosCheck(object):
    def __init__(self):
        self.parser = OptionParser()
        self.parser.add_option("-c", "--critical", dest="critical",
                help="Critical Threshhold", metavar="CRITICAL")
        self.parser.add_option("-w", "--warning", dest="warning",
                help="Warning threshhold", metavar="WARNING")

    def add_option(self, *args, **kwargs):
        self.parser.add_option(*args, **kwargs)

    def run(self):
        pass


class IfRefNagiosCheck(NagiosCheck):
    def run(self):
        q = """
        SELECT count(*)
          FROM ifref
         WHERE begin_time > timestamp 'NOW'  - interval '1 weeks'
            OR (end_time < 'NOW'
                AND end_time > timestamp 'NOW' - interval '1 weeks')"""


def check_ifref():
    check = IfRefNagiosCheck().setup().run()

def decode_alu_port(x):
    x = int(x)
    a = (x & int('00011110000000000000000000000000', 2)) >> 25
    b = (x & int('00000001111000000000000000000000', 2)) >> 21
    c = (x & int('00000000000111111000000000000000', 2)) >> 15

    return "%d/%d/%d" % (a,b,c)

def build_alu_sap_name(s):
    """convert the last parts of a SAP OID to an intelligible name.
    xxx.111.337969152.2200 -> 111-10/1/10-2200
    """
    _, service, port, vlan = s.split('.')
    return "-".join((service, decode_alu_port(port), vlan))


def datetime_to_unixtime(dt):
    return int(time.mktime(dt.timetuple()))

# max_datetime is used to represent a time sufficiently far into future such
# that this datetime is effectively infinite.  it is set to be 2 days less than
# datetime.datetime.max to prevent overflow due to timezone variances.
max_datetime = make_aware(datetime.datetime.max - datetime.timedelta(2), utc)
