# Generated by Django 5.0 on 2023-12-13 02:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='workinghour',
            name='break_end_time',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workinghour',
            name='break_start_time',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
