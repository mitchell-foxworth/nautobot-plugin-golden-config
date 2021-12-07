# Generated by Django 3.1.13 on 2021-12-07 19:19

from django.db import migrations, models


def convert_many_repos(apps, schema_editor):
    """
    Add the temp `backup_repositories` and `intended_repositories` objects
    back to the new updated attribute with many-to-many relationships.
    """
    GoldenConfigSetting = apps.get_model("nautobot_golden_config", "GoldenConfigSetting")

    settings_obj = GoldenConfigSetting.objects.first()
    if settings_obj.backup_repositories.all():
        [settings_obj.backup_repository.add(backup_repo) for backup_repo in settings_obj.backup_repositories.all()]
    if settings_obj.intended_repositories.all():
        [
            settings_obj.intended_repository.add(intended_repo)
            for intended_repo in settings_obj.intended_repositories.all()
        ]


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0013_default_fallback_value_computedfield"),
        ("nautobot_golden_config", "0006_multi_repo_support_temp_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="goldenconfigsetting",
            name="backup_repository_template",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="goldenconfigsetting",
            name="intended_repository_template",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RemoveField(
            model_name="goldenconfigsetting",
            name="backup_repository",
        ),
        migrations.AddField(
            model_name="goldenconfigsetting",
            name="backup_repository",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"provided_contents__contains": "nautobot_golden_config.backupconfigs"},
                related_name="backup_repository",
                to="extras.GitRepository",
            ),
        ),
        migrations.RemoveField(
            model_name="goldenconfigsetting",
            name="intended_repository",
        ),
        migrations.AddField(
            model_name="goldenconfigsetting",
            name="intended_repository",
            field=models.ManyToManyField(
                blank=True,
                limit_choices_to={"provided_contents__contains": "nautobot_golden_config.intendedconfigs"},
                related_name="intended_repository",
                to="extras.GitRepository",
            ),
        ),
        migrations.RunPython(convert_many_repos),
    ]
