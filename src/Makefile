
all: thrift

thrift:
	thrift --gen py:new_style --gen perl -r ./esxsnmp.thrift
	cp gen-py/esxsnmp/* python/esxsnmp/rpc
	sed s/TBinaryProtocol.TBinaryProtocol/TBinaryProtocol.TBinaryProtocolAccelerated/ gen-py/esxsnmp/ESDB-remote > python/esxsnmp/rpc/ESDB-remote
