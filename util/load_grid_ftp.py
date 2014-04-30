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
    parser.add_option('-v', '--verbose',
            dest='verbose', action='count', default=False,
            help='Verbose output - -v, -vv, etc.')
    options, args = parser.parse_args()

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
        print 'found last record:', last_record.to_dict()
    else:
        print 'no last record'

    # Load the log

    with open(file_path,'r') as fh:
        data = fh.read()
    data = data.split('\n')

    # Read up to the last record that was processed and start processing
    # subsequent records

    scanning = False

    for row in data:
        print row
        if not row.strip(): continue
        o = LogEntryDataObject(row.split())
        if last_record and not scanning:
            if o.to_dict() == last_record.to_dict():
                print 'found last match'
                scanning = True
            continue

        # XXX(mmg) - tweak script_alias deal
        mp = MetadataPost(options.api_url, username=options.user,
            api_key=options.key, script_alias=None, 
            **_generate_metadata_args(o))
        mp.add_event_type('throughput')
        mp.add_event_type('failures')
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
            # XXX(mmg) - tweak script_alias deal
            et = EventTypePost(options.api_url, username=options.user,
                api_key=options.key, script_alias=None, 
                metadata_key=metadata.metadata_key,
                event_type='throughput')
            throughput = 8 * o.nbytes / (_epoch(o.date) - _epoch(o.start))
            et.add_data_point(_epoch(o.start), throughput)
            et.post_data()
        else:
            # XXX(mmg) - tweak script_alias deal
            et = EventTypePost(options.api_url, username=options.user,
                api_key=options.key, script_alias=None, 
                metadata_key=metadata.metadata_key,
                event_type='failures')
            et.add_data_point(_epoch(o.start), 
                { 'error': '{0} {1}'.format(o.code, FTP_CODES.get(o.code, None)) })
            et.post_data()

    if options.write:
        o.to_pickle(options.pickle)
    
    pass

if __name__ == '__main__':
    main()