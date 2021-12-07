# Generated by Django 3.1.13 on 2021-12-07 06:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0013_default_fallback_value_computedfield"),
        ("nautobot_golden_config", "0005_json_compliance_rule"),
    ]

    operations = [
        migrations.AddField(
            model_name="goldenconfigsetting",
            name="backup_repositories",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"provided_contents__contains": "nautobot_golden_config.backupconfigs"},
                related_name="backup_repositories",
                to="extras.GitRepository",
            ),
        ),
        migrations.AddField(
            model_name="goldenconfigsetting",
            name="intended_repositories",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"provided_contents__contains": "nautobot_golden_config.intendedconfigs"},
                related_name="intended_repositories",
                to="extras.GitRepository",
            ),
        ),
    ]
