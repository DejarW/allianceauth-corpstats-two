from unittest import mock

from django.test import TestCase
from django.utils.timezone import now
from allianceauth.tests.auth_utils import AuthUtils
from .models import CorpStats, CorpMember
from allianceauth.eveonline.models import EveCorporationInfo, EveAllianceInfo, EveCharacter
from esi.models import Token
from esi.errors import TokenError
from bravado.exception import HTTPForbidden
from django.contrib.auth.models import User, Permission
from allianceauth.authentication.models import CharacterOwnership


class CorpStatsManagerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AuthUtils.create_user('test')
        AuthUtils.add_main_character(cls.user, 'test character', '1', corp_id='2', corp_name='test_corp', corp_ticker='TEST', alliance_id='3', alliance_name='test alliance')
        cls.user.profile.refresh_from_db()
        cls.alliance = EveAllianceInfo.objects.create(alliance_id='3', alliance_name='test alliance', alliance_ticker='TEST', executor_corp_id='2')
        cls.corp = EveCorporationInfo.objects.create(corporation_id='2', corporation_name='test corp', corporation_ticker='TEST', alliance_id=3, member_count=1)
        cls.token = Token.objects.create(user=cls.user, access_token='a', character_id='1', character_name='test character', character_owner_hash='z')
        cls.corpstats = CorpStats.objects.create(corp=cls.corp, token=cls.token)
        cls.view_corp_permission = Permission.objects.get_by_natural_key('view_corp_corpstats', 'corputils', 'corpstats')
        cls.view_alliance_permission = Permission.objects.get_by_natural_key('view_alliance_corpstats', 'corputils', 'corpstats')
        cls.view_state_permission = Permission.objects.get_by_natural_key('view_state_corpstats', 'corputils', 'corpstats')
        cls.state = AuthUtils.create_state('test state', 500, member_alliances=cls.alliance)
        AuthUtils.assign_state(cls.user, cls.state, disconnect_signals=True)

    def setUp(self):
        self.user.refresh_from_db()
        self.user.user_permissions.clear()

    def test_visible_superuser(self):
        self.user.is_superuser = True
        cs = CorpStats.objects.visible_to(self.user)
        self.assertIn(self.corpstats, cs)

    def test_visible_corporation(self):
        self.user.user_permissions.add(self.view_corp_permission)
        cs = CorpStats.objects.visible_to(self.user)
        self.assertIn(self.corpstats, cs)

    def test_visible_alliance(self):
        self.user.user_permissions.add(self.view_alliance_permission)
        cs = CorpStats.objects.visible_to(self.user)
        self.assertIn(self.corpstats, cs)

    def test_visible_state_corp_member(self):
        self.state.member_corporations.add(self.corp)
        self.user.user_permissions.add(self.view_state_permission)
        cs = CorpStats.objects.visible_to(self.user)
        self.assertIn(self.corpstats, cs)

    def test_visible_state_alliance_member(self):
        self.state.member_alliances.add(self.alliance)
        self.user.user_permissions.add(self.view_state_permission)
        cs = CorpStats.objects.visible_to(self.user)
        self.assertIn(self.corpstats, cs)

    def test_visible_alliances(self):
        user = User.objects.get(pk=self.user.pk)
        user.user_permissions.add(self.view_corp_permission)
        alliances = CorpStats.objects.alliances_visible_to(user)
        self.assertEquals(len(alliances), 0)

        user.user_permissions.add(self.view_alliance_permission)
        user = User.objects.get(pk=self.user.pk)  # permissions cache is only cleared when retrieved fresh from db
        alliances = CorpStats.objects.alliances_visible_to(user)
        self.assertIn('3', alliances)

        user.user_permissions.clear()
        user = User.objects.get(pk=self.user.pk)
        alliances = CorpStats.objects.alliances_visible_to(user)
        self.assertEquals(len(alliances), 0)

        user.user_permissions.add(self.view_state_permission)
        user = User.objects.get(pk=self.user.pk)
        alliances = CorpStats.objects.alliances_visible_to(user)
        self.assertIn('3', alliances)


class CorpStatsUpdateTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AuthUtils.create_user('test')
        AuthUtils.add_main_character(cls.user, 'test character', '1', corp_id='2', corp_name='test_corp', corp_ticker='TEST', alliance_id='3', alliance_name='TEST')
        cls.user.profile.refresh_from_db()
        cls.token = Token.objects.create(user=cls.user, access_token='a', character_id='1', character_name='test character', character_owner_hash='z')
        cls.corp = EveCorporationInfo.objects.create(corporation_id='2', corporation_name='test corp', corporation_ticker='TEST', member_count=1)
        cls.character = EveCharacter.objects.create(character_name='another test character', character_id='2',
                                                    corporation_id='2', corporation_name='test corp',
                                                    corporation_ticker='TEST')

    def setUp(self):
        self.corpstats = CorpStats.objects.get_or_create(token=self.token, corp=self.corp)[0]

    @mock.patch('esi.clients.SwaggerClient')
    def test_update_member_relations(self, SwaggerClient):
        AuthUtils.disconnect_signals()

        SwaggerClient.from_spec.return_value.Character.get_characters_character_id.return_value.result.return_value = {
            'corporation_id': 2}
        SwaggerClient.from_spec.return_value.Corporation.get_corporations_corporation_id_membertracking.return_value.result.return_value = [
            {'character_id': 1, 'ship_type_id': 2, 'location_id': 3, 'logon_date': now(), 'logoff_date': now(),
             'start_date': now()},
            {'character_id': 2, 'ship_type_id': 2, 'location_id': 3, 'logon_date': now(), 'logoff_date': now(),
             'start_date': now()}]
        SwaggerClient.from_spec.return_value.Character.get_characters_names.return_value.result.return_value = [
            {'character_id': 1, 'character_name': 'test character'}]
        SwaggerClient.from_spec.return_value.Universe.get_universe_types_type_id.return_value.result.return_value = {
            'name': 'test ship'}
        SwaggerClient.from_spec.return_value.Universe.post_universe_names.return_value.result.return_value = [
            {'name': 'test system'}]

        co = CharacterOwnership.objects.create(character=self.character, user=self.user, owner_hash='a')

        self.corpstats.update()
        main = self.corpstats.members.get(character_id='1')
        alt = self.corpstats.members.get(character_id='2')

        self.assertTrue(main.registered and alt.registered)
        self.assertTrue(main.is_main)
        self.assertTrue(main.alts.filter(character_id=alt.character_id).exists())
        self.assertTrue(main.alts.count() == 1)
        self.assertEquals(main.main_character, self.user.profile.main_character)
        self.assertFalse(alt.is_main)

        co.delete()
        self.corpstats.update()
        main = self.corpstats.members.get(character_id='1')
        alt = self.corpstats.members.get(character_id='2')

        self.assertTrue(main.registered)
        self.assertTrue(main.is_main)
        self.assertFalse(alt.registered)
        self.assertTrue(main.alts.count() == 0)
        self.assertEquals(main.main_character, self.user.profile.main_character)
        self.assertFalse(alt.is_main)

        AuthUtils.connect_signals()

    @mock.patch('esi.clients.SwaggerClient')
    def test_update_add_member(self, SwaggerClient):
        SwaggerClient.from_spec.return_value.Character.get_characters_character_id.return_value.result.return_value = {'corporation_id': 2}
        SwaggerClient.from_spec.return_value.Corporation.get_corporations_corporation_id_membertracking.return_value.result.return_value = [
            {'character_id': 1, 'ship_type_id': 2, 'location_id': 3, 'logon_date': now(), 'logoff_date': now(), 'start_date': now()}]
        SwaggerClient.from_spec.return_value.Character.get_characters_names.return_value.result.return_value = [{'character_id': 1, 'character_name': 'test character'}]
        SwaggerClient.from_spec.return_value.Universe.get_universe_types_type_id.return_value.result.return_value = {'name': 'test ship'}
        SwaggerClient.from_spec.return_value.Universe.post_universe_names.return_value.result.return_value = [{'name': 'test system'}]

        self.corpstats.update()
        self.assertTrue(CorpMember.objects.filter(character_id='1', character_name='test character', corpstats=self.corpstats).exists())

    @mock.patch('esi.clients.SwaggerClient')
    def test_update_remove_member(self, SwaggerClient):
        CorpMember.objects.create(character_id='2', character_name='old test character', corpstats=self.corpstats, location_id=1, location_name='test', ship_type_id=1, ship_type_name='test', logoff_date=now(), logon_date=now(), start_date=now())
        SwaggerClient.from_spec.return_value.Character.get_characters_character_id.return_value.result.return_value = {'corporation_id': 2}
        SwaggerClient.from_spec.return_value.Corporation.get_corporations_corporation_id_membertracking.return_value.result.return_value = [{'character_id': 1, 'ship_type_id': 2, 'location_id': 3, 'logon_date': now(), 'logoff_date': now(), 'start_date': now()}]
        SwaggerClient.from_spec.return_value.Character.get_characters_names.return_value.result.return_value = [{'character_id': 1, 'character_name': 'test character'}]
        SwaggerClient.from_spec.return_value.Universe.get_universe_types_type_id.return_value.result.return_value = {'name': 'test ship'}
        SwaggerClient.from_spec.return_value.Universe.post_universe_names.return_value.result.return_value = [{'name': 'test system'}]
        self.corpstats.update()
        self.assertFalse(CorpMember.objects.filter(character_id='2', corpstats=self.corpstats).exists())

    @mock.patch('allianceauth.corputils.models.notify')
    @mock.patch('esi.clients.SwaggerClient')
    def test_update_deleted_token(self, SwaggerClient, notify):
        SwaggerClient.from_spec.return_value.Character.get_characters_character_id.return_value.result.return_value = {'corporation_id': 2}
        SwaggerClient.from_spec.return_value.Corporation.get_corporations_corporation_id_membertracking.return_value.result.side_effect = TokenError()
        self.corpstats.update()
        self.assertFalse(CorpStats.objects.filter(corp=self.corp).exists())
        self.assertTrue(notify.called)

    @mock.patch('allianceauth.corputils.models.notify')
    @mock.patch('esi.clients.SwaggerClient')
    def test_update_http_forbidden(self, SwaggerClient, notify):
        SwaggerClient.from_spec.return_value.Character.get_characters_character_id.return_value.result.return_value = {'corporation_id': 2}
        SwaggerClient.from_spec.return_value.Corporation.get_corporations_corporation_id_membertracking.return_value.result.side_effect = HTTPForbidden(mock.Mock())
        self.corpstats.update()
        self.assertFalse(CorpStats.objects.filter(corp=self.corp).exists())
        self.assertTrue(notify.called)

    @mock.patch('allianceauth.corputils.models.notify')
    @mock.patch('esi.clients.SwaggerClient')
    def test_update_token_character_corp_changed(self, SwaggerClient, notify):
        SwaggerClient.from_spec.return_value.Character.get_characters_character_id.return_value.result.return_value = {'corporation_id': 3}
        self.corpstats.update()
        self.assertFalse(CorpStats.objects.filter(corp=self.corp).exists())
        self.assertTrue(notify.called)


class CorpStatsPropertiesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AuthUtils.create_user('test')
        AuthUtils.add_main_character(cls.user, 'test character', '1', corp_id='2', corp_name='test_corp', corp_ticker='TEST', alliance_id='3', alliance_name='TEST')
        cls.user.profile.refresh_from_db()
        cls.token = Token.objects.create(user=cls.user, access_token='a', character_id='1', character_name='test character', character_owner_hash='z')
        cls.corp = EveCorporationInfo.objects.create(corporation_id='2', corporation_name='test corp', corporation_ticker='TEST', member_count=1, alliance_id='3')
        cls.corpstats = CorpStats.objects.create(token=cls.token, corp=cls.corp)
        cls.character = EveCharacter.objects.create(character_name='another test character', character_id='4', corporation_id='2', corporation_name='test corp', corporation_ticker='TEST')
        AuthUtils.disconnect_signals()
        CharacterOwnership.objects.create(character=cls.character, user=cls.user, owner_hash='a')
        AuthUtils.connect_signals()

    def test_member_count(self):
        member = CorpMember.objects.create(character_id='2', character_name='old test character', corpstats=self.corpstats,
                                  location_id=1, location_name='test', ship_type_id=1, ship_type_name='test',
                                  logoff_date=now(), logon_date=now(), start_date=now())
        self.assertEqual(self.corpstats.member_count, 1)
        member.delete()
        self.assertEqual(self.corpstats.member_count, 0)

    def test_user_count(self):
        member = CorpMember.objects.create(character_id='4', character_name='another test character', corpstats=self.corpstats,
                                  location_id=1, location_name='test', ship_type_id=1, ship_type_name='test',
                                  logoff_date=now(), logon_date=now(), start_date=now(), main_character=self.character)
        self.assertEqual(self.corpstats.user_count, 1)
        member.main_character = None
        member.save()
        self.corpstats.refresh_from_db()
        self.assertEqual(self.corpstats.user_count, 0)

    def test_registered_members(self):
        member = CorpMember.objects.create(character_id='4', character_name='another test character', corpstats=self.corpstats,
                                  location_id=1, location_name='test', ship_type_id=1, ship_type_name='test',
                                  logoff_date=now(), logon_date=now(), start_date=now(), main_character=self.character, registered=True)
        self.assertIn(member, self.corpstats.registered_members)
        self.assertEquals(self.corpstats.registered_member_count, 1)
        self.assertNotIn(member, self.corpstats.unregistered_members)
        self.assertEquals(self.corpstats.unregistered_member_count, 0)

        member.registered = False
        member.save()
        self.corpstats.refresh_from_db()

        self.assertNotIn(member, self.corpstats.registered_members)
        self.assertEquals(self.corpstats.registered_member_count, 0)
        self.assertIn(member, self.corpstats.unregistered_members)
        self.assertEquals(self.corpstats.unregistered_member_count, 1)

    def test_mains(self):
        # test when is a main
        member = CorpMember.objects.create(character_id='4', character_name='another test character', corpstats=self.corpstats,
                                  location_id=1, location_name='test', ship_type_id=1, ship_type_name='test',
                                  logoff_date=now(), logon_date=now(), start_date=now(), main_character=self.character, is_main=True)
        self.assertIn(member, self.corpstats.mains)
        self.assertEqual(self.corpstats.main_count, 1)

        # test when is not a main
        member.is_main = False
        member.save()
        self.corpstats.refresh_from_db()

        self.assertNotIn(member, self.corpstats.mains)
        self.assertEqual(self.corpstats.main_count, 0)

    def test_logos(self):
        self.assertEqual(self.corpstats.corp_logo(size=128), 'https://image.eveonline.com/Corporation/2_128.png')
        self.assertEqual(self.corpstats.alliance_logo(size=128), 'https://image.eveonline.com/Alliance/3_128.png')


class CorpMemberTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = AuthUtils.create_user('test')
        AuthUtils.add_main_character(cls.user, 'test character', '1', corp_id='2', corp_name='test_corp', corp_ticker='TEST', alliance_id='3', alliance_name='TEST')
        cls.user.profile.refresh_from_db()
        cls.token = Token.objects.create(user=cls.user, access_token='a', character_id='1', character_name='test character', character_owner_hash='a')
        cls.corp = EveCorporationInfo.objects.create(corporation_id='2', corporation_name='test corp', corporation_ticker='TEST', member_count=1)
        cls.corpstats = CorpStats.objects.create(token=cls.token, corp=cls.corp)
        cls.member = CorpMember.objects.create(corpstats=cls.corpstats, character_id='2', character_name='other test character', location_id=1, location_name='test', ship_type_id=1, ship_type_name='test', logoff_date=now(), logon_date=now(), start_date=now())

    def test_portrait_url(self):
        self.assertEquals(self.member.portrait_url(size=32), 'https://image.eveonline.com/Character/2_32.jpg')
        self.assertEquals(self.member.portrait_url(size=32), self.member.portrait_url_32)
