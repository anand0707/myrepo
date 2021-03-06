# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2015-11-02 15:38
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('buildsvc', '0011_auto_20151026_1946'),
    ]

    operations = [
        migrations.AddField(
            model_name='buildrecord',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='externaldependency',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='githubrepository',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='packagesource',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='repository',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='series',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
    ]
