import json

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
}

'''
DataValidator: Base validator class. Subclasses should override vaildate class
'''
def DataValidator(object):
    def validate(self, value):
        return

'''
FloatValidator: Simple validator for floating point numbers
'''
def FloatValidator(DataValidator):
    def validate(self, value):
        try:
            float(value)
        except ValueError:
            raise BadRequest("Value must be a floating point number")

'''
HistogramValidator: Validator for histogram type
'''
def HistogramValidator(DataValidator):
    def validate(self, value):
        try:
            json.loads(value)
            for k in value:
                long(value[k])
        except ValueError:
            raise BadRequest("Value of histogram must be an integer")
        except:
            raise BadRequest("Invalid histogram provided")

'''
IntegerValidator: Simple validator for integers
'''
def HistogramValidator(DataValidator):
    def validate(self, value):
        try:
            long(value)
        except ValueError:
            raise BadRequest("Value must be an integer")

'''
JSONValidator: Simple validator for json strings
'''
def JSONValidator(DataValidator):
    def validate(self, value):
        try:
            json.loads(value)
        except:
            raise BadRequest("Value must be valid JSON")
        
'''
PercentageValidator: Simple validator for percentage types
'''
def PercentageValidator(DataValidator):
    def validate(self, value):
        if "numerator" not in value:
            raise BadRequest("Missing required field 'numerator'")
        elif "denominator" not in value:
            raise BadRequest("Missing required field 'denominator'")
        try:
            long(value["numerator"])
        except:
            raise BadRequest("The field 'numerator' must be an integer")
        try:
            long(value["denominator"])
        except:
            raise BadRequest("The field 'denominator' must be an integer")
        
        if(value["denominator"] <= 0):
            raise BadRequest("The field 'denominator' must be greater than 0")
        elif(value["numerator"] < 0):
            raise BadRequest("The field 'numerator' cannot be negative")
