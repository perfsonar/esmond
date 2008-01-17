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

from thrift.transport import TTransport
from thrift.transport import TSocket
from thrift.transport import THttpClient
from thrift.protocol import TBinaryProtocol

from essnmp.rpc import ESDB

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
    """Set the title of the current process to name.

    XXX Presently only works on FreeBSD 6.x.  Silently fails elsewhere.
    """
    if os.uname()[0] == 'FreeBSD' and os.path.exists('/lib/libc.so.6'):
        libc = dl.open('/lib/libc.so.6')
        libc.call('setproctitle', name + "\0")
        libc.close()

def get_logger(name):
    log = logging.getLogger(name)
    log.addHandler(logging.handlers.SysLogHandler(('localhost', 514), logging.handlers.SysLogHandler.LOG_LOCAL7))
    log.setLevel(logging.DEBUG)
    log.handlers[0].setFormatter(logging.Formatter("%(name)s [%(process)d] %(message)s"))

    return log

def send_mail(sender,to,subject,body):
    if type(to) != list and type(to) != tuple:
        to = [to]

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['To'] = ", ".join(to)
    msg['From'] = sender
    srv = smtplib.SMTP()
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
