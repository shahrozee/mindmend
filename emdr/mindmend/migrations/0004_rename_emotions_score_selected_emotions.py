# Generated by Django 5.0.6 on 2024-07-14 21:25

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mindmend', '0003_remove_score_created_at_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='score',
            old_name='emotions',
            new_name='selected_emotions',
        ),
    ]
