INSERT INTO OIDType (id, name) VALUES (1, 'Counter32');
INSERT INTO OIDType (id, name) VALUES (2, 'Counter64');
INSERT INTO OIDType (id, name) VALUES (3, 'DisplayString');
INSERT INTO OIDType (id, name) VALUES (4, 'Gauge32');
INSERT INTO OIDType (id, name) VALUES (5, 'TimeTicks');
INSERT INTO OIDType (id, name) VALUES (6, 'IpAddress');
SELECT pg_catalog.setval('oidtype_id_seq', 7, true);


INSERT INTO OID (id,name,oidtypeid) VALUES (1, 'sysUpTime', 5);
INSERT INTO OID (id,name,oidtypeid) VALUES (2, 'ifInOctets', 1);
INSERT INTO OID (id,name,oidtypeid) VALUES (3, 'ifOutOctets', 1);
INSERT INTO OID (id,name,oidtypeid) VALUES (4, 'ifHCInOctets', 2);
INSERT INTO OID (id,name,oidtypeid) VALUES (5, 'ifHCOutOctets', 2);
INSERT INTO OID (id,name,oidtypeid) VALUES (6, 'ifDescr', 3);
INSERT INTO OID (id,name,oidtypeid) VALUES (7, 'ifAlias', 3);
INSERT INTO OID (id,name,oidtypeid) VALUES (8, 'ifSpeed', 4);
INSERT INTO OID (id,name,oidtypeid) VALUES (9, 'ifHighSpeed', 4);
INSERT INTO OID (id,name,oidtypeid) VALUES (10, 'ipAdEntIfIndex', 6);
SELECT pg_catalog.setval('oid_id_seq', 11, true);

INSERT INTO Poller (id,name) VALUES (1, 'CorrelatedPoller');
INSERT INTO Poller (id,name) VALUES (2, 'UncorrelatedPoller');
SELECT pg_catalog.setval('poller_id_seq', 2, true);

INSERT INTO OIDSet (id,name,frequency, pollerid, poller_args)
       VALUES (1, 'FastPoll', 30, 1,
        'chunk_mapper=tsdb.YYYYMMDDChunkMapper correlator=IfDescrCorrelator');
INSERT INTO OIDSet (id,name,frequency, pollerid, poller_args)
       VALUES (2, 'FastPollHC', 30, 1,
        'chunk_mapper=tsdb.YYYYMMDDChunkMapper correlator=IfDescrCorrelator');
INSERT INTO OIDSet (id,name,frequency, pollerid) VALUES (3, 'IfRefPoll', 1200, 2);
SELECT pg_catalog.setval('oidset_id_seq', 4, true);


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

-- add your devices using inserts like below,
--   be sure to set your community and device name
--
-- INSERT INTO device (name, begin_time, end_time, community, active)
--     VALUES ('test-router', 'NOW', 'infinity', 'public', true);
--
-- then add OIDsets to be polled for each device:
-- 
-- INSERT INTO deviceoidsetmap (deviceid, oidsetid) VALUES (X, Y);
-- where X is the id for the device and Y is the id for the OIDSet
