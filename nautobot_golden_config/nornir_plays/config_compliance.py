"""Nornir job for generating the compliance data."""
# pylint: disable=relative-beyond-top-level
import difflib
import logging
import os
from itertools import zip_longest

from datetime import datetime

from netutils.config.compliance import parser_map, section_config, _open_file_config
from nornir import InitNornir
from nornir.core.plugins.inventory import InventoryPluginRegister
from nornir.core.task import Result, Task

from nornir_nautobot.exceptions import NornirNautobotException
from nornir_nautobot.utils.logger import NornirLogger

from nautobot_plugin_nornir.plugins.inventory.nautobot_orm import NautobotORMInventory
from nautobot_plugin_nornir.constants import NORNIR_SETTINGS

from nautobot_golden_config.models import ComplianceRule, ConfigCompliance, GoldenConfigSetting, GoldenConfig
from nautobot_golden_config.utilities.helper import (
    get_job_filter,
    get_repository_working_dir,
    verify_global_settings,
    check_jinja_template,
)
from nautobot_golden_config.nornir_plays.processor import ProcessGoldenConfig
from nautobot_golden_config.utilities.utils import get_platform


InventoryPluginRegister.register("nautobot-inventory", NautobotORMInventory)
LOGGER = logging.getLogger(__name__)


def get_rules():
    """A serializer of sorts to return rule mappings as a dictionary."""
    # TODO: Review if creating a proper serializer is the way to go.
    rules = {}
    for obj in ComplianceRule.objects.filter(config_type="cli"):
        platform = str(obj.platform.slug)
        if not rules.get(platform):
            rules[platform] = []
        rules[platform].append({"ordered": obj.config_ordered, "obj": obj, "section": obj.match_config.splitlines()})
    return rules


def diff_files(backup_file, intended_file):
    """Utility function to provide `Unix Diff` between two files."""
    bkup = open(backup_file).readlines()
    intended = open(intended_file).readlines()

    for line in difflib.unified_diff(bkup, intended, lineterm=""):
        yield line


def run_compliance(  # pylint: disable=too-many-arguments,too-many-locals
    task: Task,
    logger,
    global_settings,
    backup_repos,
    intended_repos,
    rules,
) -> Result:
    """Prepare data for compliance task.

    Args:
        task (Task): Nornir task individual object

    Returns:
        result (Result): Result from Nornir task
    """
    obj = task.host.data["obj"]

    compliance_obj = GoldenConfig.objects.filter(device=obj).first()
    if not compliance_obj:
        compliance_obj = GoldenConfig.objects.create(device=obj)
    compliance_obj.compliance_last_attempt_date = task.host.defaults.data["now"]
    compliance_obj.save()

    rescue = {}
    for intended_repo, backup_repo in zip_longest(intended_repos, backup_repos):
        # Zip longest appends None if no value found in loop through two lists.
        # Edge cases where two repos & one intended or vice-versa.
        if not intended_repo:
            intended_repo = rescue["intended_repo"]
        if not backup_repo:
            backup_repo = rescue["backup_repo"]

        intended_directory = get_repository_working_dir(intended_repo, "intended", obj, logger, global_settings)
        intended_path_template_obj = check_jinja_template(obj, logger, global_settings.intended_path_template)
        intended_file = os.path.join(intended_directory, intended_path_template_obj)
        if not os.path.exists(intended_file):
            logger.log_failure(obj, f"Unable to locate intended file for device at {intended_file}")
            raise NornirNautobotException()

        backup_directory = get_repository_working_dir(backup_repo, "backup", obj, logger, global_settings)
        backup_template = check_jinja_template(obj, logger, global_settings.backup_path_template)
        backup_file = os.path.join(backup_directory, backup_template)
        if not os.path.exists(backup_file):
            logger.log_failure(obj, f"Unable to locate backup file for device at {backup_file}")
            raise NornirNautobotException()

        platform = obj.platform.slug
        if not rules.get(platform):
            logger.log_failure(obj, f"There is no defined `Configuration Rule` for platform slug `{platform}`.")
            raise NornirNautobotException()

        if get_platform(platform) not in parser_map.keys():
            logger.log_failure(
                obj, f"There is currently no parser support for platform slug `{get_platform(platform)}`."
            )
            raise NornirNautobotException()

        backup_cfg = _open_file_config(backup_file)
        intended_cfg = _open_file_config(intended_file)

        # TODO: Make this atomic with compliance_obj step.
        for rule in rules[obj.platform.slug]:
            # using update_or_create() method to conveniently update actual obj or create new one.
            ConfigCompliance.objects.update_or_create(
                device=obj,
                rule=rule["obj"],
                defaults={
                    "actual": section_config(rule, backup_cfg, get_platform(platform)),
                    "intended": section_config(rule, intended_cfg, get_platform(platform)),
                    "missing": "",
                    "extra": "",
                },
            )

        compliance_obj.compliance_last_success_date = task.host.defaults.data["now"]
        compliance_obj.compliance_config = "\n".join(diff_files(backup_file, intended_file))
        compliance_obj.save()
        logger.log_success(obj, "Successfully tested compliance job.")

        # Add values to dict to track and rescue in case.
        rescue["intended_repo"] = intended_repo
        rescue["backup_repo"] = backup_repo

        return Result(host=task.host)


def config_compliance(job_result, data, backup_repos, intended_repos):
    """Nornir play to generate configurations."""
    now = datetime.now()
    rules = get_rules()
    logger = NornirLogger(__name__, job_result, data.get("debug"))
    global_settings = GoldenConfigSetting.objects.first()
    verify_global_settings(logger, global_settings, ["backup_path_template", "intended_path_template"])
    try:
        with InitNornir(
            runner=NORNIR_SETTINGS.get("runner"),
            logging={"enabled": False},
            inventory={
                "plugin": "nautobot-inventory",
                "options": {
                    "credentials_class": NORNIR_SETTINGS.get("credentials"),
                    "params": NORNIR_SETTINGS.get("inventory_params"),
                    "queryset": get_job_filter(data),
                    "defaults": {"now": now},
                },
            },
        ) as nornir_obj:

            nr_with_processors = nornir_obj.with_processors([ProcessGoldenConfig(logger)])

            nr_with_processors.run(
                task=run_compliance,
                name="RENDER COMPLIANCE TASK GROUP",
                logger=logger,
                global_settings=global_settings,
                backup_repos=backup_repos,
                intended_repos=intended_repos,
                rules=rules,
            )

    except Exception as err:
        logger.log_failure(None, err)
        raise

    logger.log_debug("Completed compliance job for devices.")
