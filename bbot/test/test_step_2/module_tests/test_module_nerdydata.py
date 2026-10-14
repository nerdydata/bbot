from .base import ModuleTestBase
from bbot.test.mock_blasthttp import MockResponse

PROFILE_URL = "https://api.nerdydata.com/domains/blacklanternsecurity.com"


class TestNerdyData(ModuleTestBase):
    config_overrides = {"modules": {"nerdydata": {"api_key": "asdf"}}}

    async def setup_before_prep(self, module_test):
        module_test.blasthttp_mock.add_response(
            url="https://api.nerdydata.com/suggestions/categories",
            match_headers={"api_key": "asdf"},
            json={"categories": [], "industries": []},
        )
        module_test.blasthttp_mock.add_response(
            url="https://api.nerdydata.com/domains/blacklanternsecurity.com/technologies",
            match_headers={"api_key": "asdf"},
            json={
                "domains": [
                    {
                        "technologies": [
                            {
                                "name": "Google Tag Manager",
                                "uuid": "a4c6c970-d71b-42a6-bd4c-84de4a8f01d2",
                                "category": "Tag Management",
                                "categories_id": 45,
                                "industries_id": 14,
                                "industry": "Web Infrastructure",
                                "url": "/technology-reports/google-tag-manager/a4c6c970-d71b-42a6-bd4c-84de4a8f01d2",
                            },
                            {
                                "name": "Google Global Site Tag",
                                "uuid": "c5462682-3369-4a04-8990-f84a88f704ec",
                                "category": "Tag Management",
                                "categories_id": 45,
                                "industries_id": 14,
                                "industry": "Web Infrastructure",
                                "url": "/technology-reports/google-global-site-tag/c5462682-3369-4a04-8990-f84a88f704ec",
                            },
                        ],
                        "tech_spend": {"min": 0, "max": 0},
                        "domain": "blacklanternsecurity.com",
                    }
                ]
            },
        )
        module_test.blasthttp_mock.add_response(
            url=PROFILE_URL,
            match_headers={"api_key": "asdf"},
            json={
                "domain": "blacklanternsecurity.com",
                "emails": "info@blacklanternsecurity.com;sales@blacklanternsecurity.com",
                "linkedin": "https://linkedin.com/company/black-lantern-security",
                "twitter": "https://x.com/blacklanternllc",
                "tld": "com",
                "url": "https://www.blacklanternsecurity.com/",
            },
        )

    def check(self, module_test, events):
        technologies = {
            e.data["technology"]
            for e in events
            if e.type == "TECHNOLOGY" and e.data["host"] == "blacklanternsecurity.com"
        }
        assert technologies == {"google tag manager", "google global site tag"}, (
            f"Failed to detect technologies: {technologies}"
        )
        emails = {e.data for e in events if e.type == "EMAIL_ADDRESS"}
        assert emails == {"info@blacklanternsecurity.com", "sales@blacklanternsecurity.com"}, (
            f"Failed to detect emails: {emails}"
        )


class TestNerdyDataNoEmails(TestNerdyData):
    module_name = "nerdydata"
    config_overrides = {"modules": {"nerdydata": {"api_key": "asdf", "emails": False}}}

    async def setup_before_prep(self, module_test):
        await super().setup_before_prep(module_test)
        self.profile_requests = 0

        def profile_callback(request):
            self.profile_requests += 1
            return MockResponse(status_code=200, json={"emails": "info@blacklanternsecurity.com"})

        module_test.blasthttp_mock.add_callback(profile_callback, url=PROFILE_URL)

    def check(self, module_test, events):
        assert any(e.type == "TECHNOLOGY" for e in events), "Failed to detect technologies"
        assert not any(e.type == "EMAIL_ADDRESS" for e in events), "Emails should not be looked up when disabled"
        assert self.profile_requests == 0, "Domain profile should not be requested when emails are disabled"


class TestNerdyDataDomainNotFound(ModuleTestBase):
    """A domain missing from the NerdyData index (HTTP 400) must not be treated as an API failure."""

    module_name = "nerdydata"

    config_overrides = {"modules": {"nerdydata": {"api_key": "asdf"}}}

    async def setup_before_prep(self, module_test):
        module_test.blasthttp_mock.add_response(
            url="https://api.nerdydata.com/suggestions/categories",
            match_headers={"api_key": "asdf"},
            json={"categories": [], "industries": []},
        )
        module_test.blasthttp_mock.add_response(
            url="https://api.nerdydata.com/domains/blacklanternsecurity.com/technologies",
            match_headers={"api_key": "asdf"},
            json={
                "domains": [
                    {
                        "technologies": [],
                        "tech_spend": {"min": -1, "max": -1},
                        "error": "Domain not found",
                        "domain": "blacklanternsecurity.com",
                    }
                ]
            },
        )
        self.profile_requests = 0

        def profile_callback(request):
            self.profile_requests += 1
            return MockResponse(status_code=400, json={"message": "Domain not found"})

        module_test.blasthttp_mock.add_callback(profile_callback, url=PROFILE_URL)

    def check(self, module_test, events):
        module = module_test.scan.modules["nerdydata"]
        assert module.errored is False
        assert module._api_request_failures == 0
        assert not any(e.type in ("TECHNOLOGY", "EMAIL_ADDRESS") for e in events)
        assert self.profile_requests == 1, "An unindexed domain should not be retried"
