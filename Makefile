#
# Makefile for building Esmond with Vagrant
#

default:
	@echo Nothing to do here.


build:
	vagrant destroy -f
	vagrant up
TO_CLEAN += "esmond-*.rpm"


clean:
	vagrant destroy -f
	rm -rf $(TO_CLEAN) *~
