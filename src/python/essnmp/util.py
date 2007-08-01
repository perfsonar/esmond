import os
import sys
import dl

def daemonize(pidfile=None):
    '''Forks the current process into a daemon.
        derived from the ASPN recipe:
            http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012
    '''
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
