#
# Makefile for esmond
#
# (Doesn't really build anything, it's just here for the clean.)
#

default:
	@echo "Nothing to do here."


TO_CLEAN += \
	bin \
	configure_esmond \
	esmond.egg-info \
	include \
	lib \
	lib64 \
	pip-selfcheck.json \
	staticfiles \
	tsdb-data \
	vagrant-data \
	*.rpm

FILE_MODE=644
TO_CHMOD += \
	util/gen_django_secret_key.py \
	util/migrate_tastypie_keys.py \
	util/ps_remove_data.conf \
	util/ps_remove_data.py

clean:
	chmod $(FILE_MODE) $(TO_CHMOD)
	rm -rf $(TO_CLEAN) *~
