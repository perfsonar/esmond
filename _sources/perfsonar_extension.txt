***************************
Extending the perfSONAR API
***************************

Summary
=======
This document describes how developers can extend the perfSONAR API to support new types of data and metadata.

Terminology
===============
Below is a definition of common terms used throughout this document:
 * **subject** - The thing being measured. For example, a router interface, a point-to-point measurement, tea in china or really just about anything about which information can be collected.
 * **event type** - The kind of measurement being performed. For example, utilization, throughput, the price, etc. The event type provides context for interpreting the measurement (e.g. an event type of throughput is always expressed as an integer in bits per second and represents the speed of a transfer).
 * **metadata** - A set of parameters describing the subject including the list of event types being measured about that subject.
 * **data** - The measurement results. All data belongs to a particular event type and is defined by the time it was performed and the value it measured at that time. 
 * **data type** - The fundamental form of the data. For example: integer, floating-point number, JSON object, etc. Each event type has a particular data type and multiple event types may have the same data type. The difference between the data type and the event type is that event type carries additional context with it such as the units or meaning of the data, whereas data just tells you how it will look (e.g. this is a number).
 * **summarization** - A transformation of the data over a particular time period into a form that provides additional information about the measurement or combines multiple data points of the same event type to accomplish goals such as reducing the number of data points returned. 
 
Adding New Event Types
======================

.. _event_type-use_existing:

Using an Existing Data Type
-----------------------------
Adding a new event type to esmond is relatively easy if you would like to use an existing data type. The supported data types are as follows:

+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| Data Type       | Supported Summarizations | Description                                                                                                                                                                                |
+=================+==========================+============================================================================================================================================================================================+
| **float**       | aggregation              | A floating point number                                                                                                                                                                    |
|                 | average                  |                                                                                                                                                                                            |
+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **histogram**   | aggregation              | A histogram where the key is a string bucket and the value is the count of items in that bucket.  The *statistics* summary is only available for histograms where the buckets are numeric. |
|                 | statistics               |                                                                                                                                                                                            |
+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **integer**     | aggregation              | A whole number integer                                                                                                                                                                     |
|                 | average                  |                                                                                                                                                                                            |
+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **json**        | *None*                   | A JSON object or array. Any valid JSON is accepted.                                                                                                                                        |
+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **percentage**  | aggregation              | A special type that is registered as a numerator and a denominator but is returned in queries as a float. The registration form is used to improve summaries.                              |
+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| **subinterval** | *None*                   | An object with a time, duration and val that represents a time interval.                                                                                                                   |
+-----------------+--------------------------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

You may add a new event type by editing the file **esmond/api/perfsonar/types.py** and adding a new entry to the ``EVENT_TYPE_CONFIG`` dictionary. The ``EVENT_TYPE_CONFIG`` dictionary has keys with the event type name and another dictionary as the value indicating the *type* (a.k.a data type). For example, to add a new event type called *process-count* of type *integer* you would do the following::

    EVENT_TYPE_CONFIG = {
        "process-count": {
            "type": "integer",
        },
        ...
    }

That's it! Restart esmond and your new event type is available for use.

Adding a New Data Type
-----------------------------
If you would like to add a new data type not already supported there are a few additional steps. Most types can fit into the ``json`` data type, but you may want to define an explicit type if you want to be able to summarize an object. The following steps need to be performed to define a new data type:

#. Open *esmond/api/perfsonar/validator.py*
#. Define a new class that extends ``DataValidator``. You may override the following functions (none are required and all have a default behavior):

    * **validate(obj)** - Validate the given object, perform any required formatting (if any) and return the formatted value. By default just returns obj.value.
    * **summary_cf(db, summary_type)** - Return the name of the column family that should be used for the given summary type. By default returns ``None`` which means use the default. You may not need to override this if all your summaries are stored in the same column family as your base data. 
    * **average(db, obj)** - Calculate an average on the given obj and store the result in obj.value. By default a ``NotImplementedError`` is raised.
    * **aggregation(db, obj)** - Aggregate given obj and store the result in obj.value. The meaning of aggregation is context-specific (e.g. for integer or float types it means calculate the sum). By default a ``NotImplementedError`` is raised.
    * **statistics(db, obj)** - Calculate the common statistical measures on obj such as min, median, max, etc and store result in obj.value. By default a ``NotImplementedError`` is raised.

#. Open *esmond/api/perfsonar/types.py*
#. In the file add a mapping of your data type to the ``DataValidator`` you just defined in ``TYPE_VALIDATOR_MAP``. The key will be the name of your data type that you will use to reference it. For example, to add a new type **foo** you would do the following::
 
    TYPE_VALIDATOR_MAP = {
        ...
        "foo": FooValidator(),
        ...
    }

#. Update ``ALLOWED_SUMMARIES`` to indicate which summaries your data type supports. For example, if our new type *foo* supports an *aggregation* and *average* you would define it as follows::
 
    ALLOWED_SUMMARIES = {
        ...
        "foo": ['aggregation', 'average'],
        ...
    }

#. Open *esmond/api/perfsonar/api.py* and modify ``EVENT_TYPE_CF_MAP`` to map your new data type to a column family::

    EVENT_TYPE_CF_MAP = {
        'histogram': db.raw_cf,
        'integer': db.rate_cf,
        'json': db.raw_cf,
        'percentage': db.agg_cf,
        'subinterval': db.raw_cf,
        'foo': db.rate_cf
    }

That completes the steps required to define the new data type. You can now follow the steps in :ref:`event_type-use_existing` to add a new event type using your data type.

Adding New Subject Types
========================
**NOTE:** This section assumes some familiarity with `Django <https://www.djangoproject.com>`_ and `Tastypie <http://tastypieapi.org>`_. See the provided links for more details


It may be desirable to add support a new type of subject for which measurements can be collected. For example, the default esmond implementation comes with a *point-to-point* subject type for describing measurements performed between two IP addresses. Let's say instead we want to measure some statistics about a car. Before we can define new event types like speed and miles per gallon, we need to define how we will describe our car. To do so, we perform the following steps:

#. **Create a new Django model with required parameters for all subjects of this type.** We do this by opening *esmond/api/models.py* and defining a new class that extends ``django.db.models.Model``.  There is one required foreign key to the ``PSMetadata`` table that must be named *metadata*. Continuing our car example we might define something like below::

    class PSCarSubject(models.Model):
        metadata = models.OneToOneField(PSMetadata)
        vehicle_id_number = models.CharField(max_length=128)
        make = models.CharField(max_length=128)
        model = models.CharField(max_length=128)
        color = models.CharField(max_length=128)
        
        class Meta:
            db_table = "ps_car_subject"

#. **Define a REST resource for your new subject.** Open *esmond/api/perfsonar/api.py* and add a class that extends ``tastypie.resources.ModelResorce`` and maps to the model defined in the previous step. For example::

    class PSCarSubjectResource(ModelResource):
        psmetadata = fields.ToOneField('esmond.api.perfsonar.api.PSArchiveResource', 'metadata', null=True, blank=True)
    
        class Meta:
            queryset=PSCarSubject.objects.all()
            resource_name = 'car_subject'
            allowed_methods = ['get', 'post']
            authentication = AnonymousGetElseApiAuthentication()
            authorization = DjangoAuthorization()
            excludes = ['id']
            filtering = {
                "vehicle_id_number": ['exact'],  
                "make": ['exact'],
                "model": ['exact'],
                "color": ['exact']
            }
        
        def alter_detail_data_to_serialize(self, request, data):
            formatted_objs = format_detail_keys(data)
            return formatted_objs
        
        def alter_list_data_to_serialize(self, request, data):
            formatted_objs = format_list_keys(data)
            return formatted_objs


#. **Add the subject to the REST API's PSArchiveResource.** Open *esmond/api/perfsonar/api.py* and add your new subject type as a field to ``PSArchiveResource``. For example::

    class PSArchiveResource(ModelResource):
        event_types = fields.ToManyField(PSEventTypesResource, 'pseventtypes', related_name='psmetadata', full=True, null=True, blank=True)
        p2p_subject = fields.ToOneField(PSPointToPointSubjectResource, 'pspointtopointsubject', related_name='psmetadata', full=True, null=True, blank=True)
        car_subject = fields.ToOneField(PSCarSubjectResource, 'pscarsubject', related_name='psmetadata', full=True, null=True, blank=True)
        md_parameters = fields.ToManyField(PSMetadataParametersResource, 'psmetadataparameters', related_name='psmetadata', full=True, null=True, blank=True)
        ...
#. **Update the list of valid subject types** The list of valid subject types lives in **esmond/api/perfsonar/types.py** as the ``SUBJECT_FIELDS`` array. Add the ``resource_name`` from the `Meta`` class of the ``tastypie.resources.ModelResorce`` (e.g. ``PSCarSubjectResource``) previously defined. For example::

    SUBJECT_FIELDS = ['p2p_subject', 'car_subject']

#. **Map a subject type string to the REST Resource and Model Resource** In the REST API metadata object there is a *subject-type* field that indicates the type of subject the metadata describes. You must define this string and add it to the ``SUBJECT_TYPE_MAP`` and ``SUBJECT_MODEL_MAP`` dictionaries in **esmond/api/perfsonar/types.py**. From a style perspective, the string should contain hyphens and not underscores (e.g. *point-to-point*). The ``SUBJECT_TYPE_MAP`` uses the string as the key and has the ``resource_name`` defined in the ``Meta`` class of the ``tastypie.resources.ModelResorce`` you defined earlier (e.g. ``PSCarSubjectResource``). The ``SUBJECT_MODEL_MAP`` also uses the string as the key and the value is the name of our ``django.db.models.Model`` in all lowercase (e.g. *pscarsubject*). Putting it all together, you can add the *car* subject type as follows::
    
    SUBJECT_TYPE_MAP = {
        "car": "car_subject"
    }
    
    SUBJECT_MODEL_MAP = {
        "point-to-point": "pspointtopointsubject",
        "car": "pscarsubject"
    }

#. **Define how the subject parameters look in the REST interface** You can map particular filters and fields in the REST interface to columns in your Django model by updating the ``SUBJECT_FILTER_MAP`` in **esmond/api/perfsonar/types.py**. The key is the name as it appears in the REST interface and the value is the column name as it would be seen by the ``PSMetadata`` model. The name as it appears in the REST Interface must not conflict with any existing subject fields. As a good practice, you may want to prefix your fields with something that indicates the subject to limit future conflicts. For example we will prefix *car-* in all our fields  Also, as a general style you will also want o use hyphens instead of underscored in your fields.  Continuing our example::

    SUBJECT_FILTER_MAP = {
        #point-to-point subject fields
        "source": 'p2p_subject__source',
        "destination": 'p2p_subject__destination',
        "tool-name": 'p2p_subject__tool_name',
        "measurement-agent": 'p2p_subject__measurement_agent',
        "input-source": 'p2p_subject__input_source',
        "input-destination": 'p2p_subject__input_destination'
        #car subject fields
        "car-vin": 'car_subject__vehicle_id_number',
        "car-make": 'car_subject__make',
        "car-model": 'car_subject__model',
        "car-color": 'car_subject__color',
    }

That completes the basic process. A few additional notes worth considering:

* If any of your subject fields are IP addresses you may add them to the ``IP_FIELDS`` array in **esmond/api/perfsonar/types.py**. This will allow users to search on this field using a hostname or IP address.
* As a reminder you are NOT limited to only the fields in the subject for your metadata. All ``PSMetadata`` models reference both the subject model and the ``PSMetadataParameters`` model. The latter allows arbitrary defining of new fields by the client registering with the API. This can lead to a performance hit if too many of these fields are searched on simultaneously due to the way database JOINs will be structured which is why here are subject fields as well. Only fields that are required and are most commonly searched should go in the subject table to allow for greatest flexibility. 

