--
-- SQL Schema for ESnet SNMP system essnmp
--

CREATE TABLE Device (
    id       SERIAL PRIMARY KEY,
    name     varchar(256),
    begin_time  timestamp,
    end_time    timestamp
);

CREATE TABLE OIDType (
    id       SERIAL PRIMARY KEY,
    name     varchar(256)
);

CREATE TABLE OID (
    id       SERIAL PRIMARY KEY,
    name     varchar(1024),
    storage  char(1), -- 'T': TSDB, 'S': SQL
    OIDtypeId int REFERENCES OIDType
);

CREATE TABLE OIDSet (
    id       SERIAL PRIMARY KEY,
    name     varchar(256),
    frequency int
);

CREATE TABLE OIDSetMember (
    id       SERIAL PRIMARY KEY,
    OIDId    int REFERENCES OID,
    OIDSetId int REFERENCES OIDSet
);

CREATE TABLE OIDSetMap (
    id       SERIAL PRIMARY KEY,
    routerId int REFERENCES Device,
    OIDSetId int REFERENCES OIDSet
);

INSERT INTO Device (name,begin_time,end_time) VALUES ('chic-cr1', '-infinity', 'infinity');

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
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (8, 'ifSpeided', 'S', 4);
INSERT INTO OID (id,name,storage,oidtypeid) VALUES (9, 'ifHighSpeidided', 'S', 4);
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

--
-- OIDStorageMap 
--

CREATE TABLE Var (
    id        SERIAL PRIMARY KEY,
    OIDId     int REFERENCES OID,
    DeviceId  int REFERENCES Device,
    ifIndex   int
);

--- Model of MOCs topology database:

-- CREATE TABLE TopologySnapshot (
--     id           SERIAL PRIMARY KEY,
--     observerId   int REFERENCES Device,
--     begin_time   timestamp,
--     end_time     timestamp
-- );
-- 
-- 
-- CREATE TABLE IPTable (
--     id          SERIAL PRIMARY KEY,
--     snapshotId  int REFERENCES TopologySnapshot,
--     ifIndex     int REFERENCES ,
--     ifAddr      inet
-- );
-- 
-- CREATE TABLE VLANTable (
--     id          SERIAL PRIMARY KEY,
--     snapshotId  int REFERENCES TopologySnapshot,
--     ifIndex     int,
--     VLANId      int
-- );
-- 
-- CREATE TABLE IfTable (
--     id          SERIAL PRIMARY KEY,
--     snapshotId  int REFERENCES TopologySnapshot,
--     ifIndex     int,
--     speed       int,
--     ifType      varchar(64), -- could contrain this but might not be worth it
--     name        varchar(256),
--     alias       varchar(256)  -- description
-- );
-- 
-- CREATE TABLE IfIPAddrTable (
--     id           SERIAL PRIMARY KEY,
--     ifTableId    int REFERENCES IfTable,
--     ip_name      varchar(128),
--     netmask      inet,
--     ospfCost     int,
--     ospfStatus   int,
--     ospfNeighbor inet
-- );
-- 
-- CREATE TABLE BGPTable (
--     id          SERIAL PRIMARY KEY,
--     snapshotId  int REFERENCES TopologySnapshot,
-- 
--     peer        inet,
--     established int,
--     remote_asn  int,
--     peer_iface  int
-- );
