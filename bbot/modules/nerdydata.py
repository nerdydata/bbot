from bbot.modules.base import BaseModule
from bbot.core.config.models import BaseModuleConfig, Field


class nerdydata(BaseModule):
    watched_events = ["DNS_NAME"]
    produced_events = ["TECHNOLOGY", "EMAIL_ADDRESS"]
    flags = ["safe", "passive", "email-enum"]
    meta = {
        "description": "Query the NerdyData API for technologies and email addresses used by a domain",
        "created_date": "2026-10-14",
        "author": "@nerdydata",
        "auth_required": True,
    }

    class Config(BaseModuleConfig):
        api_key: str | list[str] = Field("", description="NerdyData API key", sensitive=True, mandatory=True)
        emails: bool = Field(True, description="Also look up the domain profile for email addresses")

    base_url = "https://api.nerdydata.com"
    # free endpoint that still validates the API key
    ping_url = f"{base_url}/suggestions/categories"

    # NerdyData indexes websites by their registrable domain, so only one lookup per domain is needed
    per_domain_only = True

    # returned by the API (HTTP 400) when a domain isn't in the NerdyData index
    domain_not_found_message = "Domain not found"

    async def setup(self):
        self.emails = self.config.get("emails", True)
        return await self.require_api_key()

    def prepare_api_request(self, url, kwargs):
        kwargs["headers"]["api_key"] = self.api_key
        return url, kwargs

    def _api_response_is_success(self, r):
        # an unindexed domain is not an API failure, so don't retry it or count it towards the error state
        if getattr(r, "status_code", 0) == 400:
            try:
                return r.json().get("message", "") == self.domain_not_found_message
            except Exception:
                return False
        return super()._api_response_is_success(r)

    async def filter_event(self, event):
        _, domain = self.helpers.split_domain(event.data)
        if not domain:
            return False, "Unable to determine registrable domain"
        return True

    async def handle_event(self, event):
        _, domain = self.helpers.split_domain(event.data)
        await self.handle_technologies(event, domain)
        if self.emails:
            await self.handle_emails(event, domain)

    async def handle_technologies(self, event, domain):
        url = f"{self.base_url}/domains/{self.helpers.quote(domain)}/technologies"
        json = await self.request_json(url, domain)
        for result in json.get("domains", []) or []:
            error = result.get("error", "")
            if error:
                self.debug(f'No technologies for "{domain}": {error}')
                continue
            for technology in result.get("technologies", []) or []:
                name = technology.get("name", "")
                if not name:
                    continue
                category = technology.get("category", "")
                category_str = f" ({category})" if category else ""
                await self.emit_event(
                    {"host": domain, "technology": name},
                    "TECHNOLOGY",
                    parent=event,
                    context=f'{{module}} queried the NerdyData API for "{domain}" and found {{event.type}}: {name}{category_str}',
                )

    async def handle_emails(self, event, domain):
        url = f"{self.base_url}/domains/{self.helpers.quote(domain)}"
        json = await self.request_json(url, domain)
        # emails are returned as a semicolon-separated string
        emails = json.get("emails", "") or ""
        for email in emails.split(";"):
            email = email.strip()
            if not email:
                continue
            await self.emit_event(
                email,
                "EMAIL_ADDRESS",
                parent=event,
                context=f'{{module}} queried the NerdyData API for "{domain}" and found {{event.type}}: {{event.data}}',
            )

    async def request_json(self, url, domain):
        r = await self.api_request(url)
        if r is None:
            self.debug(f'No response from NerdyData for "{domain}"')
            return {}
        try:
            json = r.json()
        except Exception as e:
            self.debug(f'Error parsing NerdyData response for "{domain}" (status code {r.status_code}): {e}')
            return {}
        if not isinstance(json, dict):
            return {}
        if not r.is_success:
            self.debug(f'No results for "{domain}": {json.get("message", "")}')
            return {}
        return json
