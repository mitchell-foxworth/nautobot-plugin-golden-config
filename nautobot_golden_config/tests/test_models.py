"""Unit tests for nautobot_golden_config models."""

from json import loads as json_loads
from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from nautobot.dcim.models import Platform
from nautobot.extras.models import GitRepository
from nautobot_golden_config.tests.conftest import create_git_repos

from nautobot_golden_config.models import (
    ConfigCompliance,
    GoldenConfigSetting,
    ConfigRemove,
    ConfigReplace,
)

from .conftest import create_device, create_feature_rule_json, create_config_compliance


class ConfigComplianceModelTestCase(TestCase):
    """Test CRUD operations for ConfigCompliance Model."""

    def setUp(self):
        """Set up base objects."""
        self.device = create_device()
        self.compliance_rule_json = create_feature_rule_json(self.device)

    def test_create_config_compliance_success_json(self):
        """Successful."""
        actual = {"foo": {"bar-1": "baz"}}
        intended = {"foo": {"bar-2": "baz"}}
        cc_obj = create_config_compliance(
            self.device, actual=actual, intended=intended, compliance_rule=self.compliance_rule_json
        )

        self.assertFalse(cc_obj.compliance)
        self.assertEqual(cc_obj.actual, {"foo": {"bar-1": "baz"}})
        self.assertEqual(cc_obj.intended, {"foo": {"bar-2": "baz"}})
        self.assertEqual(cc_obj.missing, ["root['foo']['bar-2']"])
        self.assertEqual(cc_obj.extra, ["root['foo']['bar-1']"])

    def test_create_config_compliance_unique_failure(self):
        """Raises error when attempting to create duplicate."""
        ConfigCompliance.objects.create(
            device=self.device,
            rule=self.compliance_rule_json,
            actual={"foo": {"bar-1": "baz"}},
            intended={"foo": {"bar-2": "baz"}},
            missing={},
            extra={},
        )
        with self.assertRaises(IntegrityError):
            ConfigCompliance.objects.create(
                device=self.device,
                rule=self.compliance_rule_json,
                compliance=False,
                actual={"foo": {"bar-1": "baz"}},
                intended={"foo": {"bar-2": "baz"}},
                missing={},
                extra={},
            )

    def test_create_config_compliance_success_compliant(self):
        """Successful."""
        cc_obj = ConfigCompliance.objects.create(
            device=self.device,
            rule=self.compliance_rule_json,
            actual={"foo": {"bar-1": "baz"}},
            intended={"foo": {"bar-1": "baz"}},
        )

        self.assertTrue(cc_obj.compliance)
        self.assertEqual(cc_obj.missing, "")
        self.assertEqual(cc_obj.extra, "")


class GoldenConfigTestCase(TestCase):
    """Test GoldenConfig Model."""


class ComplianceRuleTestCase(TestCase):
    """Test ComplianceRule Model."""


class GoldenConfigSettingModelTestCase(TestCase):
    """Test GoldenConfigSetting Model."""

    def setUp(self):
        """Get the golden config settings with the only allowed id."""
        self.global_settings = GoldenConfigSetting.objects.first()

    def test_absolute_url_success(self):
        """Verify that get_absolute_url() returns the expected URL."""
        url_string = self.global_settings.get_absolute_url()
        self.assertEqual(url_string, "/plugins/golden-config/setting/")

    def test_bad_graphql_query(self):
        """Invalid graphql query."""
        self.global_settings.sot_agg_query = 'devices(name:"ams-edge-01")'
        with self.assertRaises(ValidationError):
            self.global_settings.clean()

    def test_bad_scope(self):
        """Verify that a bad value in the scope returns the expected error."""
        self.global_settings.scope = json_loads('{"has_primary_ip": true, "role": ["Apple"]}')
        with self.assertRaises(ValidationError) as error:
            self.global_settings.clean()
        self.assertEqual(
            error.exception.messages[0],
            "role: Select a valid choice. Apple is not one of the available choices.",
        )

    def test_good_graphql_query_invalid_starts_with(self):
        """Valid graphql query, however invalid in the usage with golden config plugin."""
        self.global_settings.sot_agg_query = '{devices(name:"ams-edge-01"){id}}'
        with self.assertRaises(ValidationError) as error:
            self.global_settings.clean()
        self.assertEqual(error.exception.message, "The GraphQL query must start with exactly `query ($device_id: ID!)`")

    def test_good_graphql_query_validate_starts_with(self):
        """Ensure clean() method returns None when valid query is sent through."""
        self.global_settings.sot_agg_query = "query ($device_id: ID!) {device(id: $device_id) {id}}"
        self.assertEqual(self.global_settings.clean(), None)

    def test_good_scope(self):
        """Verify that the scope passes validation as expected."""
        self.global_settings.scope = json_loads('{"has_primary_ip": true}')
        self.assertEqual(self.global_settings.clean(), None)


class GoldenConfigSettingGitModelTestCase(TestCase):
    """Test GoldenConfigSetting Model."""

    def setUp(self) -> None:
        """Setup test data."""
        create_git_repos()
        # Since we enforce a singleton pattern on this model, nuke the auto-created object.
        GoldenConfigSetting.objects.all().delete()

        # Create fresh new object, populate accordingly.

        self.golden_config = GoldenConfigSetting.objects.create(  # pylint: disable=attribute-defined-outside-init
            backup_match_rule="backup-{{ obj.site.region.parent.slug }}",
            backup_path_template="{{ obj.site.region.parent.slug }}/{{obj.name}}.cfg",
            intended_match_rule="intended-{{ obj.site.region.parent.slug }}",
            intended_path_template="{{ obj.site.slug }}/{{ obj.name }}.cfg",
            backup_test_connectivity=True,
            jinja_repository=GitRepository.objects.get(name="test-jinja-repo-1"),
            jinja_path_template="{{ obj.platform.slug }}/main.j2",
        )
        self.golden_config.backup_repository.set(
            [
                GitRepository.objects.get(name="test-backup-repo-1"),
                GitRepository.objects.get(name="test-backup-repo-2"),
            ]
        )
        self.golden_config.intended_repository.set(
            [
                GitRepository.objects.get(name="test-intended-repo-1"),
                GitRepository.objects.get(name="test-intended-repo-2"),
            ]
        )
        self.golden_config.save()

    def test_model_success(self):
        """Create a new instance of the GoldenConfigSettings model."""

        self.assertEqual(self.golden_config.backup_match_rule, "backup-{{ obj.site.region.parent.slug }}")
        self.assertEqual(self.golden_config.backup_path_template, "{{ obj.site.region.parent.slug }}/{{obj.name}}.cfg")
        self.assertEqual(self.golden_config.intended_match_rule, "intended-{{ obj.site.region.parent.slug }}")
        self.assertEqual(self.golden_config.intended_path_template, "{{ obj.site.slug }}/{{ obj.name }}.cfg")
        self.assertTrue(self.golden_config.backup_test_connectivity)
        self.assertEqual(self.golden_config.jinja_repository, GitRepository.objects.get(name="test-jinja-repo-1"))
        self.assertEqual(self.golden_config.jinja_path_template, "{{ obj.platform.slug }}/main.j2")
        self.assertEqual(
            self.golden_config.backup_repository.first(), GitRepository.objects.get(name="test-backup-repo-1")
        )
        self.assertEqual(
            self.golden_config.backup_repository.last(), GitRepository.objects.get(name="test-backup-repo-2")
        )
        self.assertEqual(
            self.golden_config.intended_repository.first(), GitRepository.objects.get(name="test-intended-repo-1")
        )
        self.assertEqual(
            self.golden_config.intended_repository.last(), GitRepository.objects.get(name="test-intended-repo-2")
        )

    def test_clean_gc_model_backup_repo(self):
        """Ensure we raise `ValidationError` on `GoldenConfigSetting` model.

        Leave just 1 backup repository, but with a matching repo rule.
        """
        self.golden_config.backup_repository.first().delete()
        with self.assertRaises(ValidationError) as error:
            self.golden_config.validated_save()
        self.assertEqual(
            error.exception.messages[0],
            "If you configure only one backup repository, there is no need to specify the backup repository matching rule template.",
        )

    def test_clean_gc_model_backup_repo_missing_template(self):
        """Ensure we raise `ValidationError` on `GoldenConfigSetting` model.

        2 backup repositories, but with no matching rule.
        """
        self.golden_config.backup_repository.set(
            [
                GitRepository.objects.get(name="test-backup-repo-1"),
                GitRepository.objects.get(name="test-backup-repo-2"),
            ]
        )
        self.golden_config.backup_match_rule = None
        self.assertEqual(self.golden_config.backup_repository.all().count(), 2)
        with self.assertRaises(ValidationError) as error:
            self.golden_config.clean()
        self.assertEqual(
            error.exception.messages[0],
            "If you specify more than one backup repository, you must provide a backup repository matching rule template.",
        )

    def test_clean_gc_model_intended_repo(self):
        """Ensure we raise `ValidationError` on `GoldenConfigSetting` model.

        Leave just 1 intended repository, but with a matching repo rule.
        """
        self.golden_config.intended_repository.first().delete()
        with self.assertRaises(ValidationError) as error:
            self.golden_config.validated_save()
        self.assertEqual(
            error.exception.messages[0],
            "If you configure only one intended repository, there is no need to specify the intended repository matching rule template.",
        )

    def test_clean_gc_model_intended_repo_missing_template(self):
        """Ensure we raise `ValidationError` on `GoldenConfigSetting` model.

        2 intended repositories, but with no matching rule.
        """
        self.golden_config.backup_repository.set(
            [
                GitRepository.objects.get(name="test-intended-repo-1"),
                GitRepository.objects.get(name="test-intended-repo-2"),
            ]
        )
        self.golden_config.intended_match_rule = None
        self.assertEqual(self.golden_config.intended_repository.all().count(), 2)
        with self.assertRaises(ValidationError) as error:
            self.golden_config.clean()
        self.assertEqual(
            error.exception.messages[0],
            "If you specify more than one intended repository, you must provide a intended repository matching rule template.",
        )

    def test_removing_git_repos(self):
        """Ensure we can remove the Git Repository obejcts from GoldenConfigSetting."""
        GitRepository.objects.all().delete()
        self.assertEqual(self.golden_config.intended_repository.count(), 0)
        self.assertEqual(self.golden_config.backup_repository.count(), 0)
        self.assertEqual(GoldenConfigSetting.objects.all().count(), 1)

    def test_clean_up(self):
        """Delete all objects created of GitRepository type."""
        GoldenConfigSetting.objects.all().delete()
        # Put back a general GoldenConfigSetting object.
        global_settings = GoldenConfigSetting.objects.create()
        global_settings.save()
        self.assertEqual(GoldenConfigSetting.objects.all().count(), 1)


class ConfigRemoveModelTestCase(TestCase):
    """Test ConfigRemove Model."""

    def setUp(self):
        """Setup Object."""
        self.platform = Platform.objects.create(slug="cisco_ios")
        self.line_removal = ConfigRemove.objects.create(
            name="foo", platform=self.platform, description="foo bar", regex="^Back.*"
        )

    def test_add_line_removal_entry(self):
        """Test Add Object."""
        self.assertEqual(self.line_removal.name, "foo")
        self.assertEqual(self.line_removal.description, "foo bar")
        self.assertEqual(self.line_removal.regex, "^Back.*")

    def test_edit_line_removal_entry(self):
        """Test Edit Object."""
        new_name = "Line Remove"
        new_desc = "Testing Remove Running Config Line"
        new_regex = "^Running.*"
        self.line_removal.name = new_name
        self.line_removal.description = new_desc
        self.line_removal.regex = new_regex
        self.line_removal.save()

        self.assertEqual(self.line_removal.name, new_name)
        self.assertEqual(self.line_removal.description, new_desc)
        self.assertEqual(self.line_removal.regex, new_regex)


class ConfigReplaceModelTestCase(TestCase):
    """Test ConfigReplace Model."""

    def setUp(self):
        """Setup Object."""
        self.platform = Platform.objects.create(slug="cisco_ios")
        self.line_replace = ConfigReplace.objects.create(
            name="foo",
            platform=self.platform,
            description="foo bar",
            regex=r"username(\S+)",
            replace="<redacted>",
        )

    def test_add_line_replace_entry(self):
        """Test Add Object."""
        self.assertEqual(self.line_replace.name, "foo")
        self.assertEqual(self.line_replace.description, "foo bar")
        self.assertEqual(self.line_replace.regex, r"username(\S+)")
        self.assertEqual(self.line_replace.replace, "<redacted>")

    def test_edit_line_replace_entry(self):
        """Test Edit Object."""
        new_name = "Line Replacement"
        new_desc = "Testing Replacing Config Line"
        new_regex = r"password(\S+)"
        self.line_replace.name = new_name
        self.line_replace.description = new_desc
        self.line_replace.regex = new_regex
        self.line_replace.save()

        self.assertEqual(self.line_replace.name, new_name)
        self.assertEqual(self.line_replace.description, new_desc)
        self.assertEqual(self.line_replace.regex, new_regex)
        self.assertEqual(self.line_replace.replace, "<redacted>")
