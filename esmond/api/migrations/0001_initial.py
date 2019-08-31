# -*- coding: utf-8 -*-


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
    ]
