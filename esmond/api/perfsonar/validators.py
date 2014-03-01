import json
from tastypie.exceptions import BadRequest

'''
DataValidator: Base validator class. Subclasses should override vaildate class
'''
class DataValidator(object):
    def validate(self, value):
        return value
    
    def base(self, db, obj):
        #use default column family
        return None
    
    def average(self, db, obj):
        raise NotImplementedError()
    
    def aggregation(self, db, obj):
        raise NotImplementedError()
    
    def statistics(self, db, obj):
        raise NotImplementedError()

'''
FloatValidator: Simple validator for floating point numbers
'''
class FloatValidator(DataValidator):
    def validate(self, value):
        try:
            return float(value)
        except ValueError:
            raise BadRequest("Value must be a floating point number")

'''
HistogramValidator: Validator for histogram type
'''
class HistogramValidator(DataValidator):
    def validate(self, value):
        try:
            json.dumps(value)
            for k in value:
                value[k] = long(value[k])
        except ValueError:
            raise BadRequest("Value of histogram must be an integer")
        except:
            raise BadRequest("Invalid histogram provided")
        
        return value
    
    def _get_histogram(self, db, obj):
        #query current histogram
        results = db.query_raw_data(path=obj.datapath, freq=obj.freq,
                   ts_min=obj.time*1000, ts_max=obj.time*1000)
        #if no results then this is the first histogram
        if len(results) == 0:
            return None
        
        return results[0]['val']
    
    def aggregation(self, db, obj):
        #combine and set as value
        agg_hist = self._get_histogram(db, obj)
        if agg_hist is None:
            return None
        curr_hist = obj.value
        for k in curr_hist:
            if k in agg_hist:
                agg_hist[k] += curr_hist[k]
            else:
                agg_hist[k] = curr_hist[k]
        obj.value = agg_hist
        
        return None

'''
IntegerValidator: Simple validator for integers
'''
class IntegerValidator(DataValidator):
    def validate(self, value):
        try:
            return long(value)
        except ValueError:
            raise BadRequest("Value must be an integer")
    
    def average(self, db, obj):
        obj.value = {
            'numerator': obj.value,
            'denominator': 1
        }
        
        return db.agg_cf
    
    def aggregation(self, db, obj):
        return None

'''
JSONValidator: Simple validator for json strings
'''
class JSONValidator(DataValidator):
    def validate(self, value):
        try:
            json.dumps(value)
        except:
            raise BadRequest("Value must be valid JSON")
        
        return value
        
'''
PercentageValidator: Simple validator for percentage types
'''
class PercentageValidator(DataValidator):
    def validate(self, value):
        if "numerator" not in value:
            raise BadRequest("Missing required field 'numerator'")
        elif "denominator" not in value:
            raise BadRequest("Missing required field 'denominator'")
        try:
            value["numerator"] = long(value["numerator"])
        except:
            raise BadRequest("The field 'numerator' must be an integer")
        try:
            value["denominator"] = long(value["denominator"])
        except:
            raise BadRequest("The field 'denominator' must be an integer")
        
        if(value["denominator"] <= 0):
            raise BadRequest("The field 'denominator' must be greater than 0")
        elif(value["numerator"] < 0):
            raise BadRequest("The field 'numerator' cannot be negative")
        
        return value
    
    def aggregation(self, db, obj):
        return None

'''
SubintervalValidator: Validator for subinterval type
'''
class SubintervalValidator(DataValidator):
    def validate(self, value):
        try:
            json.dumps(value)
            for k in value:
                long(value[k])
        except ValueError:
            raise BadRequest("Subinterval key must be an integer")
        except:
            raise BadRequest("Invalid subintervals provided")
        
        return value
