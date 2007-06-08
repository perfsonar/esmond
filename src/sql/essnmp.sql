--
-- SQL Schema for ESnet SNMP system essnmp
--

CREATE TABLE Device (
    id       SERIAL PRIMARY KEY,
    name     varchar(256),
    begin_time  timestamp,
    end_time    timestamp,
    community   varchar(128)
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

CREATE TABLE DeviceOIDSetMap (
    id       SERIAL PRIMARY KEY,
    deviceId int REFERENCES Device ON UPDATE CASCADE ON DELETE CASCADE,
    OIDSetId int REFERENCES OIDSet ON UPDATE CASCADE ON DELETE CASCADE
);

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
