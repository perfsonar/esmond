
all: thrift

thrift:
	./esxsnmp.thrift
	sed -i.bak -e 's/^class \([^(]*\):/class \1(object):/' gen-py/esxsnmp/ttypes.py
	rm gen-py/esxsnmp/ttypes.py.bak
	cp gen-py/esxsnmp/* python/esxsnmp/rpc
