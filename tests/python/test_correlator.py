from esmond.poll import IfDescrCorrelator, JnxFirewallCorrelator, \
                            JnxCOSCorrelator, SentryCorrelator, \
                            ALUSAPCorrelator

class MockSession(object):
    def walk(self, oid):
        if oid == 'ifDescr':
            return (('ifDescr.115', 'ae0'),
                    ('ifDescr.116', 'ge-1/0/0'),
                    ('ifDescr.117', ''))
        if oid == 'ifAlias':
            return (('ifAlias.115', 'ae0'),
                    ('ifAlias.116', 'ge-1/0/0'),
                    ('ifAlias.117', ''))
        elif oid == 'ifHCInOctets':
            return (('ifHCInOctets.115', '0', 'ifHCInOctets/ae0'),
                    ('ifHCInOctets.116', '732401229666','ifHCInOctets/ge-1_0_0'),
                    ('ifHCInOctets.117', '732401229666', None))
        elif oid == 'jnxCosIfqQedBytes':
            return (('jnxCosIfqQedBytes.116."best-effort"', '2091263919975',
                        "ge-1_0_0/jnxCosIfqQedBytes/best-effort"),
                    ('jnxCosIfqQedBytes.116."network-control"', '325426106',
                        "ge-1_0_0/jnxCosIfqQedBytes/network-control"),
                    ('jnxCosIfqQedBytes.116."scavenger-service"', '17688108277',
                        "ge-1_0_0/jnxCosIfqQedBytes/scavenger-service"),
                    ('jnxCosIfqQedBytes.116."expedited-forwarding"', '1026807',
                        "ge-1_0_0/jnxCosIfqQedBytes/expedited-forwarding"),
                    ('jnxCosIfqQedBytes.117."best-effort"', '2091263919975',
                        None),
                    ('jnxCosIfqQedBytes.117."network-control"', '325426106',
                        None),
                    ('jnxCosIfqQedBytes.117."scavenger-service"', '17688108277',
                        None),
                    ('jnxCosIfqQedBytes.117."expedited-forwarding"', '1026807',
                        None))
        elif oid == 'jnxFWCounterByteCount':
            return (('jnxFWCounterByteCount."fnal-test"."fnal".counter',
                     '0', 'counter/fnal-test/fnal'),
                    ('jnxFWCounterByteCount."fnal-test"."discard".counter',
                     '0', 'counter/fnal-test/discard'),
                    ('jnxFWCounterByteCount."test-from-eqx"."from-eqx".counter',
                     '0', 'counter/test-from-eqx/from-eqx'))
        elif oid == 'Sentry3-MIB::outletID':
            return (
                    ('Sentry3-MIB::outletID.1.1.1','AA1'),
                    ('Sentry3-MIB::outletID.1.1.2','AA2'),
                    )
        elif oid == 'Sentry3-MIB::outletLoadValue':
            return (
                    ('Sentry3-MIB::outletLoadValue.1.1.1','0',
                        'Sentry3-MIB::outletLoadValue/AA1'),
                    ('Sentry3-MIB::outletLoadValue.1.1.2','0',
                        'Sentry3-MIB::outletLoadValue/AA2'),
                    )
        elif oid == 'Sentry3-MIB::tempHumidSensorID':
            return (
                    ('Sentry3-MIB::tempHumidSensorID.1.1','A1'),
                    ('Sentry3-MIB::tempHumidSensorID.1.2','A2'),
                    )
        elif oid == 'Sentry3-MIB::tempHumidSensorTempValue':
            return (
                    ('Sentry3-MIB::tempHumidSensorTempValue.1.1','780',
                        'Sentry3-MIB::tempHumidSensorTempValue/A1'),
                    ('Sentry3-MIB::tempHumidSensorTempValue.1.2','735',
                        'Sentry3-MIB::tempHumidSensorTempValue/A2'),
                    )
        elif oid == 'Sentry3-MIB::tempHumidSensorHumidValue':
            return (
                    ('Sentry3-MIB::tempHumidSensorHumidValue.1.1','38',
                        'Sentry3-MIB::tempHumidSensorHumidValue/A1'),
                    ('Sentry3-MIB::tempHumidSensorHumidValue.1.2','47',
                        'Sentry3-MIB::tempHumidSensorHumidValue/A2'),
                    )
        elif oid == 'sapBaseStatsEgressQchipForwardedOutProfOctets':
            return (
                     ('sapBaseStatsEgressQchipForwardedOutProfOctets.834.102793216.834',
                         0L,
                         'sapBaseStatsEgressQchipForwardedOutProfOctets/834-3_1_0-834'),
                     )


class MockOID(object):
    def __repr__(self):
        return "MockOID('%s')" % self.name

    def __init__(self, name):
        self.name = name

def check_correlator(correlator, oid):
    s = MockSession()
    c = correlator()
    c.setup([])
    for (var,val,check) in s.walk(oid.name):
        assert check == c.lookup(oid, var)

def test_correlators():
    for (correlator, oid) in (
            (IfDescrCorrelator, MockOID('ifHCInOctets')),
            (JnxFirewallCorrelator, MockOID('jnxFWCounterByteCount')),
            (JnxCOSCorrelator, MockOID('jnxCosIfqQedBytes')),
            (SentryCorrelator, MockOID('Sentry3-MIB::outletLoadValue')),
            (SentryCorrelator, MockOID('Sentry3-MIB::tempHumidSensorTempValue')),
            (SentryCorrelator, MockOID('Sentry3-MIB::tempHumidSensorHumidValue')),
            (ALUSAPCorrelator, MockOID('sapBaseStatsEgressQchipForwardedOutProfOctets')),
            ):
        yield check_correlator, correlator, oid

#def test_jnx_cos_correlator():
#    s = MockSession()
#    c = JnxCOSCorrelator(s)
#    c.setup()
#    for (var,val,check) in s.walk('jnxCosIfqQedBytes'):
#        assert check == c.lookup('jnxCosIfqQedBytes', var)

