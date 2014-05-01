#!/usr/bin/env python

"""
Utility to parse and load GridFTP data.
"""

import calendar
import datetime
import pickle
import os
import socket
import sys

from optparse import OptionParser

from esmond.api.client.perfsonar.post import MetadataPost, EventTypePost

import logging
import time

def setup_log(log_path):
    """
    Usage:
    _log('main.start', 'happy simple log event')
    _log('launch', 'more={0}, complex={1} log=event'.format(100, 200))
    """
    log = logging.getLogger("grid_ftp_esmond_load")
    if not log_path:
        _h = logging.StreamHandler()
    else:
        logfile = '{0}/grid_ftp_esmond_load.log'.format(log_path)
        _h = logging.FileHandler(logfile)
    _h.setFormatter(logging.Formatter('ts=%(asctime)s %(message)s'))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    return log

class LogEntryDataObject(object):
    def __init__(self, initial=None):
        self.__dict__['_data'] = {}

        if hasattr(initial, 'items'):
            self.__dict__['_data'] = initial
        elif isinstance(initial, list):
            for i in initial:
                k,v = i.split('=')
                k = k.lower().replace('.', '_')
                self.__setattr__(k,v)
        else:
            pass

    def __getattr__(self, name):
        val = self._data.get(name, None)
        if name in ['start', 'date'] and val is not None:
            return self._parse_date(val)
        try:
            val = int(val)
        except (ValueError, TypeError):
            pass
        return val

    def __setattr__(self, name, value):
        self.__dict__['_data'][name] = value

    def _parse_date(self, d):
        return datetime.datetime.strptime(d, '%Y%m%d%H%M%S.%f')

    def to_pickle(self, f):
        fh = open(f, 'w')
        pickle.dump(self.to_dict(), fh)
        fh.close()

    def from_pickle(self, f):
        fh = open(f, 'r')
        d = pickle.load(fh)
        fh.close()
        self.__dict__['_data'] = d

    def to_dict(self):
        return self._data

def _convert_host(dest, hn):
    version = None

    try:
        socket.inet_aton(dest)
        version = 4
    except socket.error:
        pass

    try:
        socket.inet_pton(socket.AF_INET6,dest)
        version = 6
    except socket.error:
        pass

    if version == 4:
        r =  socket.getaddrinfo(hn, None)
    elif version == 6:
        r = socket.getaddrinfo(hn, None, socket.AF_INET6)
    else:
        r = None
    
    return r[0][4][0]

def _epoch(d):
    return calendar.timegm(d.utctimetuple())

def _generate_metadata_args(o):

    dest = o.dest.lstrip('[').rstrip(']')

    args = { 'tool_name': 'gridftp', 'subject_type': 'point-to-point' }

    if o.type == 'RETR':
        args['source'] = _convert_host(dest, o.host)
        args['destination'] = dest
        args['input_source'] = o.host
        args['input_destination'] = dest
    elif o.type == 'STOR':
        args['source'] = dest
        args['destination'] = _convert_host(dest, o.host)
        args['input_source'] = dest
        args['input_destination'] = o.host

    args['measurement_agent'] = _convert_host(dest, o.host)

    return args

FTP_CODES = {
    200: 'Command okay.',
    202: 'Command not implemented, superfluous at this site.',
    211: 'System status, or system help reply.',
    212: 'Directory status.',
    213: 'File status.',
    214: 'Help message.',
    215: 'NAME system type.',
    220: 'Service ready for new user.',
    221: 'Service closing control connection.',
    225: 'Data connection open; no transfer in progress.',
    226: 'Closing data connection.',
    227: 'Entering Passive Mode (h1,h2,h3,h4,p1,p2).',
    230: 'User logged in, proceed.',
    250: 'Requested file action okay, completed.',
    257: '"PATHNAME" created.',
    331: 'User name okay, need password.',
    332: 'Need account for login.',
    350: 'Requested file action pending further information.',
    421: 'Service not available, closing control connection.',
    425: 'Cant open data connection.',
    426: 'Connection closed; transfer aborted.',
    450: 'Requested file action not taken.',
    451: 'Requested action aborted: local error in processing.',
    452: 'Requested action not taken.',
    500: 'Syntax error, command unrecognized.',
    501: 'Syntax error in parameters or arguments.',
    502: 'Command not implemented.',
    503: 'Bad sequence of commands.',
    504: 'Command not implemented for that parameter.',
    530: 'Not logged in.',
    532: 'Need account for storing files.',
    550: 'Requested action not taken.',
    551: 'Requested action aborted: page type unknown.',
    552: 'Requested file action aborted.',
    553: 'Requested action not taken.',
}

def _filter_log(s):
    t_stats = 'Transfer stats: '
    if s.find(t_stats) == -1:
        return None
    else:
        return s.split(t_stats)[1].strip()

def scan_and_load(file_path, last_record, options, _log):
    # Load the log

    with open(file_path,'r') as fh:
        data = fh.read()
    data = data.split('\n')

    # Read up to the last record that was processed and start processing
    # subsequent records

    scanning = False

    o = None
    count = 0

    for row in data:
        if not row.strip(): continue
        row = _filter_log(row)
        if not row: continue
        print row
        o = LogEntryDataObject(row.split())
        if last_record and not scanning:
            if o.to_dict() == last_record.to_dict():
                print 'found last match'
                scanning = True
            continue
        count += 1
        mp = MetadataPost(options.api_url, username=options.user,
            api_key=options.key, script_alias=options.script_alias, 
            **_generate_metadata_args(o))
        mp.add_event_type('throughput')
        mp.add_event_type('failures')
        # Additional/optional data
        mp.add_freeform_key_value('bw-parallel-streams', o.streams)
        mp.add_freeform_key_value('bw-stripes', o.stripes)
        mp.add_freeform_key_value('gridftp-program', o.prog)
        mp.add_freeform_key_value('gridftp-block-size', o.block)
        mp.add_freeform_key_value('tcp-window-size', o.buffer)
        # Optional vars
        # XXX(mmg) make these configurable
        if False:
            mp.add_freeform_key_value('gridftp-file', o.file)
            mp.add_freeform_key_value('gridftp-user', o.user)
            mp.add_freeform_key_value('gridftp-volume', o.volume)
        
        metadata = mp.post_metadata()

        if o.code == 226:
            et = EventTypePost(options.api_url, username=options.user,
                api_key=options.key, script_alias=options.script_alias, 
                metadata_key=metadata.metadata_key,
                event_type='throughput')
            throughput = 8 * o.nbytes / (_epoch(o.date) - _epoch(o.start))
            et.add_data_point(_epoch(o.start), throughput)
            et.post_data()
        else:
            et = EventTypePost(options.api_url, username=options.user,
                api_key=options.key, script_alias=options.script_alias, 
                metadata_key=metadata.metadata_key,
                event_type='failures')
            et.add_data_point(_epoch(o.start), 
                { 'error': '{0} {1}'.format(o.code, FTP_CODES.get(o.code, None)) })
            et.post_data()

        if options.single:
            break

    _log('scan_and_load.end', 'Loaded {0} records'.format(count))

    return o

def main():
    usage = '%prog [ -f filename | -v ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-f', '--file', metavar='FILE',
            type='string', dest='filename', 
            help='Input filename.')
    parser.add_option('-p', '--pickle_file', metavar='FILE',
            type='string', dest='pickle', default='./load_grid_ftp.pickle',
            help='Path to pickle file (default=%default).')
    parser.add_option('-d', '--dont_write',
            dest='write', action='store_false', default=True,
            help='Do not write last position pickle file - can be used to process multiple files by hand, development, etc.')
    parser.add_option('-S', '--single',
            dest='single', action='store_true', default=False,
            help='Only load a single record - used for development.')
    parser.add_option('-l', '--log_dir', metavar='DIR',
            type='string', dest='logdir', default='',
            help='Write log output to specified directory - if not set, log goes to stdout.')
    parser.add_option('-U', '--url', metavar='ESMOND_REST_URL',
            type='string', dest='api_url', 
            help='URL for the REST API (default=%default) - required.',
            default='http://localhost:8000')
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for POST operation.')
    parser.add_option('-s', '--script_alias', metavar='URI_PREFIX',
            type='string', dest='script_alias', default='/',
            help='Set the script_alias arg if the perfsonar API is configured to use one (default=%default which means none set).')
    parser.add_option('-v', '--verbose',
            dest='verbose', action='count', default=False,
            help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()

    log_path = None

    if options.logdir:
        log_path = os.path.normpath(options.logdir)
        if not os.path.exists(log_path):
            parser.error('{0} log path does not exist.'.format(log_path))

    log = setup_log(log_path)
    _log = lambda e, s: log.info('event={e} id={gid} {s}'.format(e=e, gid=int(time.time()), s=s))

    if not options.filename:
        parser.error('Filename is required.')
    
    file_path = os.path.normpath(options.filename)
    pickle_path = os.path.normpath(options.pickle)
    
    if not os.path.exists(file_path):
        parser.error('{f} does not exist'.format(f=file_path))

    # Check for previously saved state file

    last_record = None

    if os.path.exists(pickle_path):
        last_record = LogEntryDataObject()
        last_record.from_pickle(pickle_path)
        _log('main.start', 'found last record: {0}'.format(last_record.to_dict()))
    else:
        _log('main.start', 'no last record found')

    # See if the currently indicated log contains the last record - 
    # primarily a check to see if the log has been rotated and we 
    # need to look around for our last spot.

    last_record_check = False

    if last_record:
        with open(file_path,'r') as fh:
            data = fh.read()
        data = data.split('\n')
        for row in data:
            if not row.strip(): continue
            row = _filter_log(row)
            if not row: continue
            o = LogEntryDataObject(row.split())
            if o.to_dict() == last_record.to_dict():
                last_record_check = True
                break
    
    # Process the file
    if not last_record:
        # Probably a fresh run or manual loads with --dont_write, just do it.
        _log('main.process', 'No last record, processing {0}'.format(file_path))
        last_log_entry = scan_and_load(file_path, last_record, options, _log)
    elif last_record and last_record_check:
        _log('main.process', 'File {0} passes last record check'.format(file_path))
        # We have a hit in the curent log so proceed.
        last_log_entry = scan_and_load(file_path, last_record, options, _log)
    else:
        # Crap, we need to look for it.
        _log('main.process', 'File {0} does not pass check'.format(file_path))
        last_log_entry = None # XXX(mmg): temp bulletproof, remove later.
        pass

    if last_log_entry and options.write:
        last_log_entry.to_pickle(pickle_path)
    
    pass

if __name__ == '__main__':
    main()