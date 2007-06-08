
INSERT INTO Device (name,begin_time,end_time,community) VALUES ('dev-m20-cr1',
    '-infinity', 'infinity', 'wd42');
INSERT INTO Device (name,begin_time,end_time,community) VALUES ('dev-m20-cr2',
    '-infinity', 'infinity', 'wd42');

INSERT INTO OIDType (id, name) VALUES (1, 'Counter32');
INSERT INTO OIDType (id, name) VALUES (2, 'Counter64');
INSERT INTO OIDType (id, name) VALUES (3, 'DisplayString');
INSERT INTO OIDType (id, name) VALUES (4, 'Gauge32');
INSERT INTO OIDType (id, name) VALUES (5, 'TimeTicks');
INSERT INTO OIDType (id, name) VALUES (6, 'IpAddress');

INSERT INTO OID (id,name,storage,oidtypeid) VALUES (1, 'sysUpTime', 'T', 5);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (2, 'ifInOctets', 'T', 1);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (3, 'ifOutOctets', 'T', 1);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (4, 'ifHCInOctets', 'T', 2);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (5, 'ifHCOutOctets', 'T', 2);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (6, 'ifDescr', 'S', 3);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (7, 'ifAlias', 'S', 3);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (8, 'ifSpeed', 'S', 4);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (9, 'ifHighSpeed', 'S', 4);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (10, 'ipAdEntIfIndex', 'S', 6);

INSERT INTO OIDSet (id,name,frequency) VALUES (1, 'FastPoll', 20);
INSERT INTO OIDSet (id,name,frequency) VALUES (2, 'FastPollHC', 20);
INSERT INTO OIDSet (id,name,frequency) VALUES (3, 'IfRefPoll', 1200);

INSERT INTO OIDSetMember (OIDId, OIDSetId) VALUES (1, 1);
INSERT INTO OIDSetMember (OIDId, OIDSetId) VALUES (2, 1);
INSERT INTO OIDSetMember (OIDId, OIDSetId) VALUES (3, 1);

INSERT INTO OIDSetMember (OIDId, OIDSetId) VALUES (1, 2);
INSERT INTO OIDSetMember (OIDId, OIDSetId) VALUES (4, 2);
INSERT INTO OIDSetMember (OIDId, OIDSetId) VALUES (5, 2);

INSERT INTO OIDSetMember (OIDId, OIDSetID) VALUES (6, 3);
INSERT INTO OIDSetMember (OIDId, OIDSetID) VALUES (7, 3);
INSERT INTO OIDSetMember (OIDId, OIDSetID) VALUES (8, 3);
INSERT INTO OIDSetMember (OIDId, OIDSetID) VALUES (9, 3);
INSERT INTO OIDSetMember (OIDId, OIDSetID) VALUES (10, 3);

INSERT INTO DeviceOIDSetMap (DeviceID, OIDSetID) VALUES (1,2);
INSERT INTO DeviceOIDSetMap (DeviceID, OIDSetID) VALUES (1,3);

INSERT INTO DeviceOIDSetMap (DeviceID, OIDSetID) VALUES (2,2);
INSERT INTO DeviceOIDSetMap (DeviceID, OIDSetID) VALUES (2,3);
