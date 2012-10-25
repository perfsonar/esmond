ESxSNMP Graphite Integration
============================

This project contains a module that contains a specialized settings.py for
Graphite as well as the glue to connect to ESxSNMP.

We use a copy of graphite-web with our mods to allow configuring "finders" in
the config file.  These live on github.  There are two branches on github
relevant to this deployment.  One is for patches we intend to share upstream
and the other is for ESnet only changes.

Changes for upstream go into: 
https://github.com/esnet/graphite-web

And ESnet local changes go into:
https://github.com/esnet/graphite-web/tree/esnet_tweaks

Our settings are kept in the module esxsnmp_graphite.settings.

On the webserver that will run Graphite choose GRAPHITE_ROOT and do the
following::

   $ cd $GRAPHITE_ROOT
   # copy the contents of the util/graphite directory into place
   $ cp -r $ESXSNMP_SRC/util/graphite/* .
   $ virtualenv .
   # create directories needed by Graphite
   $ mkdir -p storage/log/webapp conf
   # the next step avoids a weird dependency problem
   $ pip install hg+https://code.google.com/p/tsdb/
   $ pip install -r requirements.txt
   $ source bin/activate  # or bin/activate.csh depending on your shell
   $ python manage.py syncdb
   $ python manage.py collectstatic
   $ $EDITOR esxsnmp_graphite/settings.py # set the NEEDS TO BE CHANGED items

Edit your apache config to include this::

   Alias /content/ $GRAPHITE_ROOT/static/
   <Directory $GRAPHITE_ROOT/static/>
   Order deny,allow
   Allow from all
   </Directory>
   
   WSGIScriptAlias / $GRAPHITE_ROOT/wsgi/esxsnmp_graphite.wsgi
   WSGIPassAuthorization On
   
   <Directory $GRAPHITE_ROOT/wsgi/>
   Order deny,allow
   Allow from all
   </Directory>

