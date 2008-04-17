import os
import sys
import dl
import time
import logging
import logging.handlers
import smtplib
from email.MIMEText import MIMEText
from StringIO import StringIO
import traceback
import inspect
import tempfile

from thrift.transport import TTransport
from thrift.transport import TSocket
from thrift.transport import THttpClient
from thrift.protocol import TBinaryProtocol

from essnmp.rpc import ESDB

proctitle = None

def daemonize(pidfile=None):
    '''Forks the current process into a daemon.
        derived from the ASPN recipe:
            http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012
    '''

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
            raise "process still running as pid %d.  aborting." % pid

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
        f = file(pidfile,'w+')
        f.write("%s\n" % pid)
        f.close()
  
    # close stdin, stdout, stderr
    # XXX might not be 100% portable.
    for fd in range(3):
        os.close(fd)

    # Redirect standard file descriptors.
    os.open("/tmp/espolld.log", os.O_RDWR|os.O_CREAT)
    os.dup2(0, sys.stdout.fileno())
    os.dup2(0, sys.stderr.fileno())


def setproctitle(name):
    """Set the title of the current process to name.  This also sets the
    proctitle global variable.

    XXX Presently only works on FreeBSD 6.x.  Silently fails elsewhere.
    """
    if os.uname()[0] == 'FreeBSD' and os.path.exists('/lib/libc.so.6'):
        libc = dl.open('/lib/libc.so.6')
        libc.call('setproctitle', name + "\0")
        libc.close()

    global proctitle
    proctitle = name

def get_logger(name):
    log = logging.getLogger(name)
    log.addHandler(logging.handlers.SysLogHandler(('localhost', 514), logging.handlers.SysLogHandler.LOG_LOCAL7))
    log.setLevel(logging.DEBUG)
    log.handlers[0].setFormatter(logging.Formatter("%(name)s [%(process)d] %(message)s"))

    return log

def send_mail(sender,to,subject,body, relay='localhost'):
    if type(to) != list and type(to) != tuple:
        to = [to]

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['To'] = ", ".join(to)
    msg['From'] = sender
    srv = smtplib.SMTP(host=relay)
    srv.connect()
    srv.sendmail(sender, to, msg.as_string())
    srv.close()

def log_exception(log=None,name='essnmp'):
    if log == None:
        log = get_logger(name)

    (x,y,z) = sys.exc_info()
    lines = traceback.format_exception(x,y,z)
    log.error("Uncaught exception: " + lines[-1])
    for line in lines:
        log.error(line)

def mail_exception(to):
    body = StringIO()
    (x,y,z) = sys.exc_info()
    traceback.print_exception(x,y,z,None,body)
    subj = 'ESSNMP Exception: ' + time.ctime()
    send_mail('ESSNMP Exception Monkey <emonkey@es.net>', to, subj, body.getvalue())

def get_ESDB_client(server='localhost', port=9090):
    transport = TTransport.TBufferedTransport(TSocket.TSocket(server, port))
    client = ESDB.Client(TBinaryProtocol.TBinaryProtocol(transport))
    return (transport, client)

class ExceptHook(object):
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

    def __call__(self, *args):
        self.handle(args)

    def install(self):
        sys.excepthook = self

    def handle(self, e_info=None):
        e_info = e_info or sys.exc_info()
        if e_info[0] in self.ignore:
            return

        body = ''

        e_val = repr(e_info[1])
        if isinstance(e_info[1], str):
            e_name = e_info[1]
        elif hasattr(e_info[1], '__class__'):
            e_name = e_info[1].__class__.__name__
        else:
            e_name = e_val

        log_msg = "exception=%s" % e_name

        pid = os.getpid()

        global proctitle

        body += "Process %d (%s): %s\n\n" % (pid, proctitle, e_val)
        log_msg += " pid=%d process_name=%s" % (pid,proctitle)

        body += self.format(*e_info)

        if self.email is not None:
            subj = "%s: %s" % (self.email, log_msg)
            if email.has_key('relay'):
                relay = email['relay']
            else:
                relay = 'localhost'

            try:
                send_mail(self.email['from'], self.email['to'], subj, body,
                        relay=relay)
            except Exception, e:
                msg = "unable to send email: %s" % (repr(e))
                body += msg + "\n"

                if self.log:
                    log.error(msg)

        if self.output_dir is not None:
            log_id = self.log_to_dir(log_msg, body)
            log_msg += " log_id=%s" % (log_id)

        if self.log is not None:
            self.log.error(log_msg)

    def format(self, e_type, e_val, tb, context_lines=5):
        s = ''
        for (frame, filename, lineno, func, ctx, idx) in \
                inspect.getinnerframes(tb, context_lines):
            (args,varargs,varkw,locals) = inspect.getargvalues(frame)
            s += "%s:%s %s%s\n" % (filename, lineno+idx,
                    func,inspect.formatargvalues(args, varargs, varkw, locals))
    
            i = lineno
            s += "\n"
            for line in ctx:
                if i == lineno+idx:
                    s += "    >"
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
