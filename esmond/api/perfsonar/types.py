'''
This file defines the event types supported by the MA. Edit this file to
define new event types (or even remove support for existing event types)
'''
from esmond.api.perfsonar.validators import FloatValidator, HistogramValidator, IntegerValidator, JSONValidator, PercentageValidator

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

row-prefix: The prefix used for rows in cassandra

validator: Optional. A class to validate the value. If not specified a default will be used based on the type.

'''
EVENT_TYPE_CONFIG = {
    "failures": {
        "type": "json",
        "row_prefix": "ps:failures",
    },
    "histogram-owdelay": {
        "type": "histogram",
        "row_prefix": "ps:histogram_owdelay",
    },
    "histogram-rtt": {
        "type": "histogram",
        "row_prefix": "ps:histogram_rtt",
    },
    "histogram-ttl": {
        "type": "histogram",
        "row_prefix": "ps:histogram_ttl",
    },
    "packet-duplicates": {
        "type": "integer",
        "row_prefix": "ps:packet_duplicates",
    },
    "packet-loss-rate": {
        "type": "percentage",
        "row_prefix": "ps:packet_loss_rate",
        
    },
    "packet-trace": {
        "type": "json",
        "row_prefix": "ps:packet_trace",
    },
    "packet-count-lost": {
        "type": "integer",
        "row_prefix": "ps:packet_count_lost",
    },
    "packet-count-sent": {
        "type": "integer",
        "row_prefix": "ps:packet_count_sent",
    },
    "throughput": {
        "type": "integer",
        "row_prefix": "ps:throughput",
    },
    "throughput-subinterval": {
        "type": "subinterval",
        "row_prefix": "ps:throughput_subinterval",
    },
    "time-error-estimates": {
        "type": "float",
        "row_prefix": "ps:time_error_estimates",
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
SUBJECT_FIELDS = ['p2p_subject']
SUBJECT_TYPE_MAP = {
    "point-to-point": "p2p_subject"
    
}

'''
SUBJECT_MODEL_MAP: Maps the subject-type specified in the key to the Django
model (i.e. the database class) to store data of that subject-type
'''
SUBJECT_MODEL_MAP = {
    "point-to-point": "pspointtopointsubject"
    
}

'''
SUBJECT_FILTER_MAP: The key defines valid GET parameters when searching
metadata and the value is the database field in teh Django model to which
it maps
'''
SUBJECT_FILTER_MAP = {
    #point-to-point subject fields
    "source": 'p2p_subject__source',
    "destination": 'p2p_subject__destination',
    "tool-name": 'p2p_subject__tool_name',
    "measurement-agent": 'p2p_subject__measurement_agent',
    "input-source": 'p2p_subject__input_source',
    "input-destination": 'p2p_subject__input_destination'
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
    "float": [],
    "histogram": ['aggregation', 'statistics'],
    "integer": ['aggregation', 'average'],
    "json": [],
    "percentage": ['aggregation'],
    "subinterval": [],
}

