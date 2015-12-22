import json
import math
from rest_framework.exceptions import ParseError

'''
DataValidator: Base validator class. Subclasses should override vaildate class
'''
class DataValidator(object):
    def validate(self, obj):
        return obj.value
    
    def summary_cf(self, db, summary_type):
        return None
        
    def base(self, db, obj):
        return
    
    def average(self, db, obj):
        raise NotImplementedError()
    
    def aggregation(self, db, obj, cache):
        raise NotImplementedError()
    
    def statistics(self, db, obj, cache):
        raise NotImplementedError()

'''
FloatValidator: Simple validator for floating point numbers
'''
class FloatValidator(DataValidator):
    def validate(self, obj):
        formatted_value ={}
        try:
            formatted_value = {
                'numerator': long( float(obj.value) *  (obj.base_freq/1000)),
                'denominator': 1
            }
        except ValueError:
            raise ParseError(detail="Value must be a floating point number")
        
        return formatted_value
    
    def average(self, db, obj):
        return
    
    def aggregation(self, db, obj, cache):
        results = db.query_aggregation_timerange(path=obj.datapath, freq=obj.freq,
                   cf='average', ts_min=obj.time*1000, ts_max=obj.time*1000)
        if len(results) > 0:
            obj.value["denominator"] = 0 #don't increase the count
        return
'''
Percentile: Used by histogram class to calculate percentiles using the NIST
algorithm (http://www.itl.nist.gov/div898/handbook/prc/section2/prc252.htm)
'''
class Percentile(object):
    
    def __init__(self, percentile, sample_size):
        self.value = None
        self.is_calculated = False
        self.percentile = percentile
        self.sample_size = sample_size
        self.n = (self.percentile/100.0)*(sample_size + 1)
        self.k = math.floor(self.n)
        self.d = self.n - self.k
        
        if percentile == 50:
            self.key = "median"
        else:
            self.key = "percentile-%d" % percentile
    
    def findvalue(self, count, hist_value):
        if self.value is not None:
            self.value += (self.d * (hist_value - self.value))
            self.is_calculated = True
        elif self.k == 0:
            self.value = hist_value
            self.is_calculated = True
        elif count >= self.sample_size and self.k >= self.sample_size:
            self.value = hist_value
            self.is_calculated = True
        elif (self.k + self.d) < count:
            self.value = hist_value
            self.is_calculated = True
        else:
            self.value = hist_value
            
'''
HistogramValidator: Validator for histogram type
'''
class HistogramValidator(DataValidator):
    def validate(self, obj):
        try:
            json.dumps(obj.value)
            for k in obj.value:
                obj.value[k] = long(obj.value[k])
        except ValueError:
            raise ParseError(detail="Value of histogram must be an integer")
        except:
            raise ParseError(detail="Invalid histogram provided")
        
        return obj.value
    
    def _get_histogram(self, db, obj, datapath=None):
        if datapath is None:
            datapath = obj.datapath
            
        #query current histogram
        results = db.query_raw_data(path=datapath, freq=obj.freq,
                   ts_min=obj.time*1000, ts_max=obj.time*1000, column_count=1)
        #if no results then this is the first histogram
        if len(results) == 0:
            return None
        
        return results[0]['val']
        
    def _aggregation(self, curr_hist, agg_hist):
        for k in curr_hist:
            if k in agg_hist:
                agg_hist[k] += curr_hist[k]
            else:
                agg_hist[k] = curr_hist[k]
                
        return agg_hist
    
    def aggregation(self, db, obj, cache):
        #combine and set as value
        agg_hist = self._get_histogram(db, obj)
        if agg_hist is None:
            return None
        obj.value = self._aggregation(obj.value, agg_hist)
        cache[obj.freq] = obj.value
        
    def statistics(self, db, obj, cache):
        #get aggregated histogram
        agg_hist = obj.value
        if obj.summary_window != 0:
            if obj.freq in cache:
                agg_hist = cache[obj.freq]
        
        #pass one: mode, mean and sample size
        stats = {}
        mean_num = 0
        sample_size = 0
        for k in agg_hist:
            #only can do statistics for histograms with numeric buckets
            try:
                float(k)
            except ValueError:
                #store empty object and return but don't fail whole operation
                obj.value = {}
                return
            
            # update calculation values
            if 'mode' not in stats or agg_hist[k] > agg_hist[stats['mode'][0]]:
               stats['mode'] = [ k ]
            elif agg_hist[k] == agg_hist[stats['mode'][0]]:
                stats['mode'].append(k)
            mean_num += (float(k) * agg_hist[k])
            sample_size += agg_hist[k]
        stats['mean'] = (mean_num/(1.0*sample_size))
        
        #sort items. make sure sort as numbers not strings
        sorted_hist = sorted(agg_hist.iteritems(), key=lambda k: float(k[0]))
        
        #make mode floats.
        stats['mode'] = map(lambda x: float(x), stats['mode'])
        #get min and max
        stats['minimum'] = float(sorted_hist[0][0])
        stats['maximum'] = float(sorted_hist[len(sorted_hist)-1][0])
        
        #pass two: get quantiles, variance, and std deviation
        stddev = 0
        quantiles = [25, 50, 75, 95]
        percentiles = [Percentile(q, sample_size) for q in quantiles]
        percentile = percentiles.pop(0)
        curr_count = 0
        for hist_item in sorted_hist:
            #stddev/variance
            stddev += (math.pow(float(hist_item[0]) - stats['mean'], 2)*hist_item[1])
            #quantiles
            curr_count += hist_item[1]
            while percentile is not None and curr_count >= percentile.k:
                percentile.findvalue(curr_count, float(hist_item[0]))
                #some percentiles require next item in list, so may have to wait until next iteration
                if percentile.is_calculated:
                    #calculated so add to dict
                    stats[percentile.key] = percentile.value
                else:
                    #unable to calculate this pass, so break loop
                    break
                
                #get next percentile
                if len(percentiles) > 0:
                    percentile = percentiles.pop(0)
                else:
                    percentile = None
                    
        #set standard deviation
        stats['variance'] = stddev/sample_size
        stats['standard-deviation'] = math.sqrt(stats['variance'])
        
        #set value
        obj.value = stats
  

'''
IntegerValidator: Simple validator for integers
'''
class IntegerValidator(DataValidator):
    def validate(self, obj):
        try:
            return long(obj.value)
        except ValueError:
            raise ParseError(detail="Value must be an integer")
    
    def summary_cf(self, db, summary_type):
        if summary_type == 'average':
            return db.agg_cf
        return None
    
    def average(self, db, obj):
        obj.value = {
            'numerator': obj.value,
            'denominator': 1
        }
    
    def aggregation(self, db, obj, cache):
        return

'''
JSONValidator: Simple validator for json strings
'''
class JSONValidator(DataValidator):
    def validate(self, obj):
        try:
            json.dumps(obj.value)
        except:
            #This is pretty much an impossible case since TastyPie JSON parser breaks before this
            raise ParseError(detail="Value must be valid JSON")
        
        return obj.value
        
'''
PercentageValidator: Simple validator for percentage types
'''
class PercentageValidator(DataValidator):
    def validate(self, obj):
        if "numerator" not in obj.value:
            raise ParseError(detail="Missing required field 'numerator'")
        elif "denominator" not in obj.value:
            raise ParseError(detail="Missing required field 'denominator'")
        try:
            obj.value["numerator"] = long(obj.value["numerator"])
        except:
            raise ParseError(detail="The field 'numerator' must be an integer")
        try:
            obj.value["denominator"] = long(obj.value["denominator"])
        except:
            raise ParseError(detail="The field 'denominator' must be an integer")
        
        if(obj.value["denominator"] <= 0):
            raise ParseError(detail="The field 'denominator' must be greater than 0")
        elif(obj.value["numerator"] < 0):
            raise ParseError(detail="The field 'numerator' cannot be negative")
        
        return obj.value
    
    def aggregation(self, db, obj, cache):
        return

'''
SubintervalValidator: Validator for subinterval type
'''
class SubintervalValidator(DataValidator):
    def validate(self, obj):
        err = None
        try:
            json.dumps(obj.value)
            pos = 1
            if len(obj.value) == 0:
                 raise ParseError(detail="Empty subinterval provided")
                 
            for si in obj.value:
                if('start' not in si):
                    err = "Interval must contain 'start' field at position %d" % pos
                    break
                if('duration' not in si):
                    err = "Interval must contain 'duration' field at position %d" % pos
                    break
                if('val' not in si):
                    err = "Interval must contain 'val' field at position %d" % pos
                    break
                float(si['start'])
                float(si['duration'])
                pos += 1
        except ValueError:
            raise ParseError(detail="Subinterval 'start' and 'duration' must be floating point numbers")
        except:
            raise ParseError(detail="Invalid subintervals provided")
        
        if err is not None:
            raise ParseError(detail=err)
        
        return obj.value
