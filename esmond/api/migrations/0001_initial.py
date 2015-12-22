# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
import netfields.fields
from django.utils.timezone import utc
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0006_require_contenttypes_0002'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ALUSAPRef',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=128)),
                ('sapDescription', models.CharField(max_length=512, db_column=b'sapdescription')),
                ('sapIngressQosPolicyId', models.IntegerField(db_column=b'sapingressqospolicyid')),
                ('sapEgressQosPolicyId', models.IntegerField(db_column=b'sapegressqospolicyid')),
                ('begin_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(default=datetime.datetime(9999, 12, 29, 23, 59, 59, 999999, tzinfo=utc))),
            ],
            options={
                'ordering': ['device__name', 'name'],
                'db_table': 'alusapref',
            },
        ),
        migrations.CreateModel(
            name='Device',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
                ('begin_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(default=datetime.datetime(9999, 12, 29, 23, 59, 59, 999999, tzinfo=utc))),
                ('community', models.CharField(max_length=128)),
                ('active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['name'],
                'db_table': 'device',
            },
        ),
        migrations.CreateModel(
            name='DeviceOIDSetMap',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('device', models.ForeignKey(to='api.Device', db_column=b'deviceid')),
            ],
            options={
                'ordering': ['device', 'oid_set'],
                'db_table': 'deviceoidsetmap',
            },
        ),
        migrations.CreateModel(
            name='DeviceTag',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=255)),
            ],
            options={
                'db_table': 'devicetag',
            },
        ),
        migrations.CreateModel(
            name='DeviceTagMap',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('device', models.ForeignKey(to='api.Device', db_column=b'deviceid')),
                ('device_tag', models.ForeignKey(to='api.DeviceTag', db_column=b'devicetagid')),
            ],
            options={
                'db_table': 'devicetagmap',
            },
        ),
        migrations.CreateModel(
            name='GapInventory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
                ('processed', models.BooleanField(default=False)),
                ('issues', models.CharField(max_length=128, null=True, blank=True)),
            ],
            options={
                'ordering': ['row__row_key'],
                'db_table': 'gap_inventory',
            },
        ),
        migrations.CreateModel(
            name='IfRef',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('ifIndex', models.IntegerField(db_column=b'ifindex')),
                ('ifDescr', models.CharField(max_length=512, db_column=b'ifdescr')),
                ('ifName', models.CharField(max_length=512, db_column=b'ifname')),
                ('ifAlias', models.CharField(max_length=512, null=True, db_column=b'ifalias', blank=True)),
                ('ipAddr', models.IPAddressField(null=True, db_column=b'ipaddr', blank=True)),
                ('ifSpeed', models.BigIntegerField(null=True, db_column=b'ifspeed', blank=True)),
                ('ifHighSpeed', models.BigIntegerField(null=True, db_column=b'ifhighspeed', blank=True)),
                ('ifMtu', models.IntegerField(null=True, db_column=b'ifmtu', blank=True)),
                ('ifType', models.IntegerField(null=True, db_column=b'iftype', blank=True)),
                ('ifOperStatus', models.IntegerField(null=True, db_column=b'ifoperstatus', blank=True)),
                ('ifAdminStatus', models.IntegerField(null=True, db_column=b'ifadminstatus', blank=True)),
                ('begin_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(default=datetime.datetime(9999, 12, 29, 23, 59, 59, 999999, tzinfo=utc))),
                ('ifPhysAddress', models.CharField(max_length=32, null=True, db_column=b'ifphysaddress', blank=True)),
                ('device', models.ForeignKey(to='api.Device', db_column=b'deviceid')),
            ],
            options={
                'ordering': ['device__name', 'ifName'],
                'db_table': 'ifref',
                'permissions': (('can_see_hidden_ifref', 'Can see IfRefs with ifAlias containing :hide:'),),
            },
        ),
        migrations.CreateModel(
            name='Inventory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('row_key', models.CharField(max_length=128)),
                ('frequency', models.IntegerField()),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
                ('last_scan_point', models.DateTimeField(null=True, blank=True)),
                ('scan_complete', models.BooleanField(default=False)),
                ('data_found', models.BooleanField(default=False)),
                ('column_family', models.CharField(default=b'BR', max_length=2, choices=[(b'RD', b'raw_data'), (b'BR', b'base_rates'), (b'RA', b'rate_aggregations'), (b'SA', b'stat_aggregations')])),
                ('issues', models.CharField(max_length=128, null=True, blank=True)),
            ],
            options={
                'ordering': ['row_key'],
                'db_table': 'inventory',
            },
        ),
        migrations.CreateModel(
            name='LSPOpStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=128)),
                ('srcAddr', models.IPAddressField()),
                ('dstAddr', models.IPAddressField()),
                ('state', models.IntegerField()),
                ('begin_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(default=datetime.datetime(9999, 12, 29, 23, 59, 59, 999999, tzinfo=utc))),
                ('device', models.ForeignKey(to='api.Device', db_column=b'deviceid')),
            ],
            options={
                'ordering': ['device__name', 'name'],
                'db_table': 'lspopstatus',
            },
        ),
        migrations.CreateModel(
            name='OID',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
                ('aggregate', models.BooleanField(default=False)),
                ('endpoint_alias', models.CharField(help_text=b'Optional endpoint alias (in, out, discard/out, etc)', max_length=256, null=True, blank=True)),
            ],
            options={
                'ordering': ['name'],
                'db_table': 'oid',
            },
        ),
        migrations.CreateModel(
            name='OIDSet',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(help_text=b'Name for OIDSet.', max_length=256)),
                ('frequency', models.IntegerField(help_text=b'Polling frequency in seconds.')),
                ('poller_args', models.CharField(help_text=b'Arguments for the Poller', max_length=256, null=True, blank=True)),
            ],
            options={
                'ordering': ['name'],
                'db_table': 'oidset',
            },
        ),
        migrations.CreateModel(
            name='OIDSetMember',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('oid', models.ForeignKey(to='api.OID', db_column=b'oidid')),
                ('oid_set', models.ForeignKey(to='api.OIDSet', db_column=b'oidsetid')),
            ],
            options={
                'ordering': ['oid_set', 'oid'],
                'db_table': 'oidsetmember',
            },
        ),
        migrations.CreateModel(
            name='OIDType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
            ],
            options={
                'ordering': ['name'],
                'db_table': 'oidtype',
            },
        ),
        migrations.CreateModel(
            name='OutletRef',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('outletID', models.CharField(max_length=128)),
                ('outletName', models.CharField(max_length=128)),
                ('outletStatus', models.IntegerField()),
                ('outletControlState', models.IntegerField(null=True, blank=True)),
                ('begin_time', models.DateTimeField()),
                ('end_time', models.DateTimeField(default=datetime.datetime(9999, 12, 29, 23, 59, 59, 999999, tzinfo=utc))),
                ('device', models.ForeignKey(to='api.Device', db_column=b'deviceid')),
            ],
            options={
                'ordering': ['device__name', 'outletID'],
                'db_table': 'outletref',
            },
        ),
        migrations.CreateModel(
            name='Poller',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
            ],
            options={
                'ordering': ['name'],
                'db_table': 'poller',
            },
        ),
        migrations.CreateModel(
            name='PSEventTypes',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('event_type', models.CharField(max_length=128, db_index=True)),
                ('summary_type', models.CharField(max_length=128)),
                ('summary_window', models.BigIntegerField()),
                ('time_updated', models.DateTimeField(null=True)),
            ],
            options={
                'ordering': ['metadata', 'event_type', 'summary_type', 'summary_window'],
                'db_table': 'ps_event_types',
            },
        ),
        migrations.CreateModel(
            name='PSMetadata',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('metadata_key', models.SlugField(unique=True, max_length=128)),
                ('subject_type', models.CharField(max_length=128)),
                ('checksum', models.CharField(unique=True, max_length=128, db_index=True)),
            ],
            options={
                'ordering': ['metadata_key'],
                'db_table': 'ps_metadata',
            },
        ),
        migrations.CreateModel(
            name='PSMetadataParameters',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('parameter_key', models.CharField(max_length=128, db_index=True)),
                ('parameter_value', models.TextField()),
                ('metadata', models.ForeignKey(related_name='psmetadataparameters', to='api.PSMetadata')),
            ],
            options={
                'db_table': 'ps_metadata_parameters',
            },
        ),
        migrations.CreateModel(
            name='PSNetworkElementSubject',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('tool_name', models.CharField(max_length=128)),
                ('source', models.GenericIPAddressField(db_index=True)),
                ('measurement_agent', models.GenericIPAddressField()),
                ('input_source', models.CharField(max_length=128)),
                ('metadata', models.OneToOneField(to='api.PSMetadata')),
            ],
            options={
                'ordering': ['source', 'tool_name'],
                'db_table': 'ps_networkelement_subject',
            },
        ),
        migrations.CreateModel(
            name='PSPointToPointSubject',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('tool_name', models.CharField(max_length=128)),
                ('source', models.GenericIPAddressField(db_index=True)),
                ('destination', models.GenericIPAddressField(db_index=True)),
                ('measurement_agent', models.GenericIPAddressField()),
                ('input_source', models.CharField(max_length=128)),
                ('input_destination', models.CharField(max_length=128)),
                ('metadata', models.OneToOneField(to='api.PSMetadata')),
            ],
            options={
                'ordering': ['source', 'destination'],
                'db_table': 'ps_p2p_subject',
            },
        ),
        migrations.CreateModel(
            name='UserIpAddress',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('ip', netfields.fields.CidrAddressField(unique=True, max_length=43, db_index=True)),
                ('user', models.ForeignKey(related_name='user', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'useripaddress',
                'verbose_name': 'User IP Address',
                'verbose_name_plural': 'User IP Addresses',
            },
        ),
        migrations.CreateModel(
            name='APIPermission',
            fields=[
            ],
            options={
                'proxy': True,
                'permissions': (('esmond_api.view_timeseries', 'View timseries data'), ('esmond_api.add_timeseries', 'Add timseries data'), ('esmond_api.delete_timeseries', 'Delete timseries data'), ('esmond_api.change_timeseries', 'Change timseries data')),
            },
            bases=('auth.permission',),
        ),
        migrations.AddField(
            model_name='pseventtypes',
            name='metadata',
            field=models.ForeignKey(related_name='pseventtypes', to='api.PSMetadata'),
        ),
        migrations.AddField(
            model_name='oidset',
            name='oids',
            field=models.ManyToManyField(help_text=b'List of OIDs in the OIDSet', to='api.OID', through='api.OIDSetMember'),
        ),
        migrations.AddField(
            model_name='oidset',
            name='poller',
            field=models.ForeignKey(db_column=b'pollerid', to='api.Poller', help_text=b'Which poller to use for this OIDSet'),
        ),
        migrations.AddField(
            model_name='oid',
            name='oid_type',
            field=models.ForeignKey(to='api.OIDType', db_column=b'oidtypeid'),
        ),
        migrations.AlterUniqueTogether(
            name='inventory',
            unique_together=set([('row_key', 'start_time', 'end_time')]),
        ),
        migrations.AddField(
            model_name='gapinventory',
            name='row',
            field=models.ForeignKey(to='api.Inventory', db_column=b'keyid'),
        ),
        migrations.AddField(
            model_name='deviceoidsetmap',
            name='oid_set',
            field=models.ForeignKey(to='api.OIDSet', db_column=b'oidsetid'),
        ),
        migrations.AddField(
            model_name='device',
            name='devicetag',
            field=models.ManyToManyField(to='api.DeviceTag', through='api.DeviceTagMap'),
        ),
        migrations.AddField(
            model_name='device',
            name='oidsets',
            field=models.ManyToManyField(to='api.OIDSet', through='api.DeviceOIDSetMap'),
        ),
        migrations.AddField(
            model_name='alusapref',
            name='device',
            field=models.ForeignKey(to='api.Device', db_column=b'deviceid'),
        ),
    ]
