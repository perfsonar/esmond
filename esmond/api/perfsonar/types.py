'''
This file defines the event types supported by the MA. Edit this file to
define new event types (or even remove support for existing event types)
'''
from esmond.api.perfsonar.validators import FloatValidator, HistogramValidator, IntegerValidator, JSONValidator, PercentageValidator, SubintervalValidator

'''
EVENT_TYPE_CONFIG: Defines the event-types. The 'key' of the dictionary
is the name of the event-type. This name will also appear in the URL, so
avoid special characters. The valid fields in the value object are as follows:

type: The data type of the event type. Valid values are currently:
        float: A floating point number
        histogram: An object where the key is a string labeling the bucket and the value is an integer of the bucket count
        integer: A whole number
        json: A generic JSON object. No summary is possible since the structure is opaque to the MA.
        percentage: A numerator and denominator that can be used to calculate a percentage

validator: Optional. A class to validate the value. If not specified a default will be used based on the type.

'''
EVENT_TYPE_CONFIG = {
    "failures": {
        "type": "json",
    },
    "histogram-owdelay": {
        "type": "histogram",
    },
    "histogram-rtt": {
        "type": "histogram",
    },
    "histogram-ttl": {
        "type": "histogram",
    },
    "histogram-ttl-reverse": {
        "type": "histogram",
    },
    "iostat": {
        "type": "json",
    },
    "mpstat": {
        "type": "json",
    },
    "ntp-offset": {
        "type": "float",
    },
    "ntp-jitter": {
        "type": "float",
    },
    "ntp-wander": {
        "type": "float",
    },
    "ntp-polling-interval": {
        "type": "float",
    },
    "ntp-stratum": {
        "type": "integer",
    },
    "ntp-reach": {
        "type": "integer",
    },
    "ntp-delay": {
        "type": "float",
    },
    "ntp-dispersion": {
        "type": "float",
    },
    "packet-duplicates": {
        "type": "integer",
    },
    "packet-duplicates-bidir": {
        "type": "integer",
    },
    "packet-loss-rate": {
        "type": "percentage",
    },
    "packet-loss-rate-bidir": {
        "type": "percentage",
    },
    "packet-trace": {
        "type": "json",
    },
    "packet-trace-multi": {
        "type": "json",
    },
    "packet-count-lost": {
        "type": "integer"
    },
    "packet-count-lost-bidir": {
        "type": "integer"
    },
    "packet-count-sent": {
        "type": "integer",
    },
    "packet-reorders": {
        "type": "integer",
    },
    "packet-reorders-bidir": {
        "type": "integer",
    },
    "packet-retransmits": {
        "type": "integer",
    },
    "packet-retransmits-subintervals": {
        "type": "subinterval",
    },
    "path-mtu": {
        "type": "integer",
    },
    "pscheduler-raw": {
        "type": "json",
    },
    "pscheduler-run-href": {
        "type": "json",
    },
    "rusage": {
        "type": "json",
    },
    "streams-packet-retransmits": {
        "type": "json",
    },
    "streams-packet-retransmits-subintervals": {
        "type": "json",
    },
    "streams-tcpinfo": {
        "type": "json",
    },
    "streams-throughput": {
        "type": "json",
    },
    "streams-throughput-subintervals": {
        "type": "json",
    },
    "tcpinfo": {
        "type": "json",
    },
    "throughput": {
        "type": "integer",
    },
    "throughput-subintervals": {
        "type": "subinterval",
    },
    "time-error-estimates": {
        "type": "float",
    }
}

'''
SUMMARY_TYPES: The supported summaries. The key is the name as it appears in the URL
(usually plural form) and the value is the name as it appears in JSON.
'''
SUMMARY_TYPES = {
    "base": "base",
    "aggregations": "aggregation",
    "statistics": "statistics",
    "averages": "average"
}

'''
INVERSE_SUMMARY_TYPES: Same as SUMMARY_TYPES with the key and values swapped
'''
INVERSE_SUMMARY_TYPES = {v:k for k,v in SUMMARY_TYPES.items()}
SUBJECT_FIELDS = ['p2p_subject', 'networkelement_subject']
SUBJECT_TYPE_MAP = {
    "point-to-point": "p2p_subject",
    "network-element": "networkelement_subject"
}

'''
SUBJECT_MODEL_MAP: Maps the subject-type specified in the key to the Django
model (i.e. the database class) to store data of that subject-type
'''
SUBJECT_MODEL_MAP = {
    "point-to-point": "pspointtopointsubject",
    "network-element": "psnetworkelementsubject"
}

'''
SUBJECT_FILTER_MAP: The key defines valid GET parameters when searching
metadata and the value is the database field in teh Django model to which
it maps
'''
SUBJECT_FILTER_MAP = {
    #point-to-point subject fields
    "source": ['pspointtopointsubject__source', 'psnetworkelementsubject__source'],
    "destination": ['pspointtopointsubject__destination'],
    "tool-name": ['pspointtopointsubject__tool_name', 'psnetworkelementsubject__tool_name'],
    "measurement-agent": ['pspointtopointsubject__measurement_agent', 'psnetworkelementsubject__measurement_agent'],
    "input-source": ['pspointtopointsubject__input_source', 'psnetworkelementsubject__input_source'],
    "input-destination": ['pspointtopointsubject__input_destination']
}

'''
IP_FIELDS: Fields that must be IP addresses. Maps to GET parameter
name as defined in SUBJECT_FILTER_MAP. This list is used to determine if DNS
lookups need to be performed when a user provides a hostname for a search against
one of the fields listed.
'''
IP_FIELDS = ["source","destination","measurement-agent"]

'''
TYPE_VALIDATOR_MAP: Mpas data types to validator classes. These are the
defaults used if no 'validator' is provided in EVENT_TYPE_CONFIG
'''
TYPE_VALIDATOR_MAP = {
    "float": FloatValidator(),
    "histogram": HistogramValidator(),
    "integer": IntegerValidator(),
    "json": JSONValidator(),
    "percentage": PercentageValidator(),
    "subinterval": SubintervalValidator(),
}

'''
ALLOWED_SUMMARIES: Indicates the types of summaries allowed by each type
'''
ALLOWED_SUMMARIES = {
    "float": ['aggregation', 'average'],
    "histogram": ['aggregation', 'statistics'],
    "integer": ['aggregation', 'average'],
    "json": [],
    "percentage": ['aggregation'],
    "subinterval": [],
}

'''
DEFAULT_FLOAT_PRECISION: Indicates the number of decimal places to store
for float type as 10 ^ <numeber-of-digits>.
Example: 10000 means 4 decimal places
'''
DEFAULT_FLOAT_PRECISION=10000

'''
Constants that map to common filters
'''
SUBJECT_TYPE_FILTER = "subject-type"
METADATA_KEY_FILTER = "metadata-key"
EVENT_TYPE_FILTER = "event-type"
SUMMARY_TYPE_FILTER = "summary-type"
SUMMARY_WINDOW_FILTER = "summary-window"
DNS_MATCH_RULE_FILTER = "dns-match-rule"
TIME_FILTER = "time"
TIME_START_FILTER = "time-start"
TIME_END_FILTER = "time-end"
TIME_RANGE_FILTER = "time-range"
DNS_MATCH_PREFER_V6 = "prefer-v6"
DNS_MATCH_PREFER_V4 = "prefer-v4"
DNS_MATCH_ONLY_V6 = "only-v6"
DNS_MATCH_ONLY_V4 = "only-v4"
DNS_MATCH_V4_V6 = "v4v6"
DATA_KEY_TIME = "ts"
DATA_KEY_VALUE = "val"
LIMIT_FILTER = "limit"
OFFSET_FILTER = "offset"
RESERVED_GET_PARAMS = ["format", LIMIT_FILTER, OFFSET_FILTER, DNS_MATCH_RULE_FILTER, TIME_FILTER,
                       TIME_START_FILTER, TIME_END_FILTER, TIME_RANGE_FILTER]

