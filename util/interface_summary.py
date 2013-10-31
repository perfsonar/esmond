#!/usr/bin/env python

"""
Program to generate interface summaries for a specific set of interfaces 
aggregated on the sort of endpoint (in, out, discard/in, etc).  These
aggregations are performed on the 30 second base rate values and are 
written to the same 30 second timestamps.

Usage and args:

-U : the url to the REST interface of the form: http://host, http://host:port,
etc.  This is required - defaults to http://localhost.

-a or -i : specifies a search patter for either an interface alias (-a) or 
an interface name/ifdescr (-i).  One or the other is required.  This is used
to perform a django filtering search to generate a group of interfaces. A 
django '__contains' (ifDescr__contains, etc) query on the interfaces.

-e : specifies an endpoint type (in, out, error/in, discard/out, etc) to 
retrieve and aggregate data for.  This option may be specified more than 
once (-e in -e out) to include more than one endpoint alias in the generated
aggregations.  This is "optional" as the query library default to just 'in.'

-l : last n minutes of of data to query.  If this optional args it not 
specified, it defaults to one minute ago, rounded back to the closest
30 second rate bin timestamp.  Otherwise it will go back n minutes ago
and search up to the current time.

-P : a boolean flag indicated that the generated aggregations are POSTed 
and stored in the cassandra backend.  This does not need to be specified 
if the user just wants to generate an look at the generated objects and 
values (generally in conjunction with the -v flag) for debugging or 
edification.

-u and -k : user name and api key string - these will need to be specified 
if the -P flag is invoked to store the generated aggregations as the 
/timeseries POSTs are protected with api key authorization.

-v and -vv : produce increasingly noisy output.

Aggregation: the filtering search is performed to pull back the data
from the matched interfaces, the values from each endpoint alias type 
(in, out, etc) are summed together for every 30 second rate bin for a 
given endpoint alias.

Storage: the aggregated values are written to the "raw_data" column 
family in the esmond cassandra backend.  The keys are of the following
format:

summary:TotalTrafficIntercloud:out:30000:2013

The first 'summary' segment is just a 'namespace' that prefixes all of the 
keys of the summary data (as opposed to the 'snmp' namespace that) the 
live data is written to.  The second segment (TotalTrafficIntercloud in 
this case) is the 'summary name' that is mapped to a given query (see next
section).  The third segment is the endpoint alias being aggregated.  The
30000 frequency (30 sec in ms) matches that this has been derived from
thirty second data.  The trailing year segment is automatically generated 
by the cassandra.py module logic.

The way the data are written, all of the aggregations are idempotent, so 
running the same search over the same time period will yield the same 
results being stored (unless the base rate data has been updated in the 
meantime).

All of the values in a given row are just 30-second bin timestamps and 
the summed value.

Summary name: the summary name segment is an operator-specified string that 
maps to a specific search criteria.  It is important that this value not be 
overloaded because if it is, aggs from one query will over-write previously
generated aggregations.  To better illustrate how this mapping works, and 
to show the way that the users can manage this, all of the these have 
been put in a configuration file (see: interface_summary.conf).  Example
entries:

# Mappings for ifdescr filters
[ifDescr__contains]
me0.0: TotalTrafficMe0.0

# Mappings for ifalias filters
[ifAlias__contains]
intercloud: TotalTrafficIntercloud

The [sections] correspond to the filtering query that is being performed, 
the key of a given entry is the actual search criteria used in the filter, 
and the value of a given entry is the summary name that is used when 
formulating the row key.  So this row key:

summary:TotalTrafficMe0.0:in:30000:2013

contains the aggregations for the 'in' endpoints on all the interfaces 
returned by the query "ifDescr__contains=me0.0".

"""

import datetime
import os
import os.path
import requests
import sys
import time

from optparse import OptionParser

from esmond.api.client.snmp import ApiConnect, ApiFilters
from esmond.api.client.timeseries import PostRawData, GetRawData
from esmond.api.client.util import SUMMARY_NS, get_summary_name, \
    aggregate_to_ts_and_endpoint

def main():    
    usage = '%prog [ -U rest url (required) | -i ifDescr pattern | -a alias pattern | -e endpoint -e endpoint (multiple ok) ]'
    parser = OptionParser(usage=usage)
    parser.add_option('-U', '--url', metavar='ESMOND_REST_URL',
            type='string', dest='api_url', 
            help='URL for the REST API (default=%default) - required.',
            default='http://localhost')
    parser.add_option('-i', '--ifdescr', metavar='IFDESCR',
            type='string', dest='ifdescr_pattern', 
            help='Pattern to apply to interface ifdescr search.')
    parser.add_option('-a', '--alias', metavar='ALIAS',
            type='string', dest='alias_pattern', 
            help='Pattern to apply to interface alias search.')
    parser.add_option('-e', '--endpoint', metavar='ENDPOINT',
            dest='endpoint', action='append', default=[],
            help='Endpoint type to query (required) - can specify more than one.')
    parser.add_option('-l', '--last', metavar='LAST',
            type='int', dest='last', default=0,
            help='Last n minutes of data to query - api defaults to 60 if not given.')
    parser.add_option('-v', '--verbose',
                dest='verbose', action='count', default=False,
                help='Verbose output - -v, -vv, etc.')
    parser.add_option('-P', '--post',
            dest='post', action='store_true', default=False,
            help='Switch to actually post data to the backend - otherwise it will just query and give output.')
    parser.add_option('-u', '--user', metavar='USER',
            type='string', dest='user', default='',
            help='POST interface username.')
    parser.add_option('-k', '--key', metavar='API_KEY',
            type='string', dest='key', default='',
            help='API key for POST operation.')
    options, args = parser.parse_args()
    
    filters = ApiFilters()

    filters.verbose = options.verbose
    filters.endpoint = options.endpoint

    if options.last:
        filters.begin_time = int(time.time() - (options.last*60))
    else:
        # Default to one minute ago, then rounded to the nearest 30 
        # second bin.
        time_point = int(time.time() - 60)
        bin_point = time_point - (time_point % 30)
        filters.begin_time = filters.end_time = bin_point

    if not options.ifdescr_pattern and not options.alias_pattern:
        # Don't grab *everthing*.
        print 'Specify an ifdescr or alias filter option.'
        parser.print_help()
        return -1
    elif options.ifdescr_pattern and options.alias_pattern:
        print 'Specify only one filter option.'
        parser.print_help()
        return -1
    else:
        if options.ifdescr_pattern:
            interface_filters = { 'ifDescr__contains': options.ifdescr_pattern }
        elif options.alias_pattern:
            interface_filters = { 'ifAlias__contains': options.alias_pattern }

    conn = ApiConnect(options.api_url, filters)

    data = conn.get_interface_bulk_data(**interface_filters)

    print data

    # Aggregate/sum the returned data by timestamp and endpoint alias.
    aggs = aggregate_to_ts_and_endpoint(data, options.verbose)

    # Might be searching over a time period, so re-aggregate based on 
    # path so that we only need to do one API write per endpoint alias, 
    # rather than a write for every data point.

    bin_steps = aggs.keys()[:]
    bin_steps.sort()

    summary_name = get_summary_name(interface_filters)

    path_aggregation = {}

    for bin_ts in bin_steps:
        if options.verbose > 1: print bin_ts
        for endpoint in aggs[bin_ts].keys():
            path = (SUMMARY_NS, summary_name, endpoint)
            if not path_aggregation.has_key(path):
                path_aggregation[path] = []
            if options.verbose > 1: print ' *', endpoint, ':', aggs[bin_ts][endpoint], path
            path_aggregation[path].append({'ts': bin_ts*1000, 'val': aggs[bin_ts][endpoint]})

    if not options.post:
        print 'Not posting (use -P flag to write to backend).'
        return

    if not options.user or not options.key:
        print 'user and key args must be supplied to POST summary data.'
        return

    for k,v in path_aggregation.items():
        args = {
            'api_url': options.api_url, 'path': list(k), 'freq': 30000
        }
            
        p = PostRawData(username=options.user, api_key=options.key, **args)
        p.set_payload(v)
        p.send_data()
        
        if options.verbose:
            print 'verifying write'
            g = GetRawData(**args)
            payload = g.get_data()
            print payload
            for d in payload.data:
                print '  *', d


    pass

if __name__ == '__main__':
    main()