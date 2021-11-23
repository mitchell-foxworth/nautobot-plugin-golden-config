"""Helper functions."""
# pylint: disable=raise-missing-from
from jinja2 import Template, StrictUndefined, UndefinedError
from jinja2.exceptions import TemplateError, TemplateSyntaxError

from nornir_nautobot.exceptions import NornirNautobotException
from nornir_nautobot.utils.logger import NornirLogger

from nautobot.dcim.filters import DeviceFilterSet
from nautobot.dcim.models import Device
from nautobot.extras.models.datasources import GitRepository

from django import forms

from nautobot_golden_config import models


FIELDS = {
    "platform",
    "tenant_group",
    "tenant",
    "region",
    "site",
    "role",
    "rack",
    "rack_group",
    "manufacturer",
    "device_type",
}


def get_job_filter(data=None):
    """Helper function to return a the filterable list of OS's based on platform.slug and a specific custom value."""
    if not data:
        data = {}
    query = {}
    for field in FIELDS:
        if data.get(field):
            query[f"{field}_id"] = data[field].values_list("pk", flat=True)
    # Handle case where object is from single device run all.
    if data.get("device") and isinstance(data["device"], Device):
        query.update({"id": [str(data["device"].pk)]})
    elif data.get("device"):
        query.update({"id": data["device"].values_list("pk", flat=True)})

    base_qs = models.GoldenConfigSetting.objects.first().get_queryset()
    if DeviceFilterSet(data=query, queryset=base_qs).qs.filter(platform__isnull=True).count() > 0:
        raise NornirNautobotException(
            f"The following device(s) {', '.join([device.name for device in DeviceFilterSet(data=query, queryset=base_qs).qs.filter(platform__isnull=True)])} have no platform defined. Platform is required."
        )

    return DeviceFilterSet(data=query, queryset=base_qs).qs


def null_to_empty(val):
    """Convert to empty string if the value is currently null."""
    if not val:
        return ""
    return val


def verify_global_settings(logger, global_settings, attrs):
    """Helper function to verify required attributes are set before a Nornir play start."""
    for item in attrs:
        if not getattr(global_settings, item):
            logger.log_failure(None, f"Missing the required global setting: `{item}`.")
            raise NornirNautobotException()


def check_jinja_template(obj, logger, template):
    """Helper function to catch Jinja based issues and raise with proper NornirException."""
    try:
        template_rendered = Template(template, undefined=StrictUndefined).render(obj=obj)
        return template_rendered
    except UndefinedError as error:
        logger.log_failure(obj, f"Jinja `{template}` has an error of `{error}`.")
        raise NornirNautobotException()
    except TemplateSyntaxError as error:
        logger.log_failure(obj, f"Jinja `{template}` has an error of `{error}`.")
        raise NornirNautobotException()
    except TemplateError as error:
        logger.log_failure(obj, f"Jinja `{template}` has an error of `{error}`.")
        raise NornirNautobotException()


def get_root_folder(
    repo: GitRepository, repo_type: str, obj: Device, logger: NornirLogger, global_settings: models.GoldenConfigSetting
) -> str:
    """Generate root folder path for multiple repository support with template str matching.

    Args:
        repo (GitRepository): Repository object.
        repo_type (str): `intended` or `backup` repository
        obj (Device): Devie object.
        logger (NornirLogger): Logger object
        global_settings (models.GoldenConfigSetting): Golden Config global settings.

    Returns:
        str: backup root folder
    """
    if repo_type == "intended":
        repo_template = global_settings.intended_repository_template
    elif repo_type == "backup":
        repo_template = global_settings.backup_repository_template
    # elif jinja template multiple support?

    if repo_template:
        repo_template = check_jinja_template(obj, logger, repo_template)
        # Figure out how to get this from settings or something?
        # repo.path returns(example) = "/opt/nautobot/git/repo-name/"
        # Can we do something with this ^
        backup_root_folder = f"/opt/nautobot/git/{repo_template}"
    else:
        backup_root_folder = repo.path

    return backup_root_folder


def clean_config_settings(repo_type: str, repo_count: int, repo_template: str):
    """Custom clean for `GoldenConfigSettingFeatureForm`.

    Args:
        repo_type (str): `intended` or `backup`.
        repo_count (int): Total number of repos.
        repo_template (str): Template str provided by user to match repos.

    Raises:
        ValidationError: Custom Validation on form.
    """
    if repo_count > 1:
        if not repo_template:
            raise forms.ValidationError(
                f"If more than one {repo_type} repository specified, you must provide an {repo_type} repository template."
            )
    elif repo_count == 1 and repo_template:
        raise forms.ValidationError(
            f"If only one {repo_type} repository specified, there is no need to specify an {repo_type} repository template match."
        )
