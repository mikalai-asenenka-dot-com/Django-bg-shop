# Generated by Django 3.2 on 2021-05-14 22:46

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('boardgames', '0022_alter_boardgame_add_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='boardgame',
            name='add_date',
            field=models.DateField(default=datetime.datetime(2021, 5, 14, 22, 46, 2, 231902, tzinfo=utc), verbose_name='Дата добавления'),
        ),
    ]