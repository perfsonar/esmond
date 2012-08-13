--
-- SQL Schema for ESnet SNMP system essnmp
--

CREATE TABLE Device (
    id          SERIAL PRIMARY KEY,
    name        varchar(256),
    begin_time  timestamp,
    end_time    timestamp,
    community   varchar(128),
    active      boolean
);

CREATE TABLE DeviceTag (
    id       SERIAL PRIMARY KEY,
    name     varchar(256),
    UNIQUE(name)
);

CREATE TABLE DeviceTagMap (
    id       SERIAL PRIMARY KEY,
    deviceId int REFERENCES Device ON UPDATE CASCADE ON DELETE CASCADE,
    deviceTagId int REFERENCES DeviceTag on UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE OIDType (
    id       SERIAL PRIMARY KEY,
    name     varchar(256)
);

CREATE TABLE OIDCorrelator (
    id       SERIAL PRIMARY KEY,
    name     varchar(256)
);

CREATE TABLE OID (
    id       SERIAL PRIMARY KEY,
    name     varchar(1024),
    aggregate boolean default false,
    OIDtypeId int REFERENCES OIDType,
    OIDCorrelatorId int REFERENCES OIDCorrelator
);

CREATE TABLE Poller (
    id       SERIAL PRIMARY KEY,
    name     varchar(256)
);

CREATE TABLE OIDSet (
    id         SERIAL PRIMARY KEY,
    name       varchar(256),
    frequency  int,
    pollerid   int REFERENCES Poller,
    poller_args varchar(256)
);

CREATE TABLE OIDSetMember (
    id       SERIAL PRIMARY KEY,
    OIDId    int REFERENCES OID,
    OIDSetId int REFERENCES OIDSet
);

CREATE TABLE DeviceOIDSetMap (
    id               SERIAL PRIMARY KEY,
    deviceId         int REFERENCES Device ON UPDATE CASCADE ON DELETE CASCADE,
    OIDSetId         int REFERENCES OIDSet ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IfRef (
    id            SERIAL PRIMARY KEY,
    deviceid      int,

    ifIndex       int,
    ifDescr       varchar(512),
    ifAlias       varchar(512),
    ipAddr        inet,
    ifSpeed       int8,  -- pg doesn't have unsigned ints
    ifHighSpeed   int8,  -- pg doesn't have unsigned ints
    ifMtu         int,
    ifType        int,
    ifPhysAddress macaddr,
    ifOperStatus  char(1),
    ifAdminStatus char(1),

    begin_time  timestamp,
    end_time    timestamp,

    FOREIGN KEY (deviceid) references device(id) ON DELETE RESTRICT
);

CREATE TABLE ALUSAPRef (
    id            SERIAL PRIMARY KEY,
    deviceid      int,

    name           varchar(128),
    sapDescription varchar(512),
    sapIngressQosPolicyId int,
    sapEgressQosPolicyId int,

    begin_time  timestamp,
    end_time    timestamp,

    FOREIGN KEY (deviceid) references device(id) ON DELETE RESTRICT
);

CREATE TABLE LSPOpStatus (
    id          SERIAL PRIMARY KEY,

    deviceid    int,
    name        varchar(128),
    srcAddr     inet,
    dstAddr     inet,
    state       int,

    begin_time  timestamp,
    end_time    timestamp,

    FOREIGN KEY (deviceid) references device(id) ON DELETE RESTRICT
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
