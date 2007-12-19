
all: thrift

thrift:
	./essnmp.thrift
	sed -i.bak -e 's/^class \([^(]*\):/class \1(object):/' gen-py/essnmp/ttypes.py
	rm gen-py/essnmp/ttypes.py.bak
	cp gen-py/essnmp/* python/essnmp/thrift
