from bbot.modules.base import BaseModule
from bbot.core.config.models import BaseModuleConfig, Field


class nerdydata(BaseModule):
    watched_events = ["DNS_NAME"]
    produced_events = ["TECHNOLOGY"]
    flags = ["safe", "passive"]
    meta = {
        "description": "Query the NerdyData API for technologies used by a domain",
        "created_date": "2026-10-14",
        "author": "@nerdydata",
        "auth_required": True,
    }

    class Config(BaseModuleConfig):
        api_key: str | list[str] = Field("", description="NerdyData API key", sensitive=True, mandatory=True)

    base_url = "https://api.nerdydata.com"
    # free endpoint that still validates the API key
    ping_url = f"{base_url}/suggestions/categories"

    # NerdyData indexes websites by their registrable domain, so only one lookup per domain is needed
    per_domain_only = True

    async def setup(self):
        return await self.require_api_key()

    def prepare_api_request(self, url, kwargs):
        kwargs["headers"]["api_key"] = self.api_key
        return url, kwargs

    async def filter_event(self, event):
        _, domain = self.helpers.split_domain(event.data)
        if not domain:
            return False, "Unable to determine registrable domain"
        return True

    async def handle_event(self, event):
        _, domain = self.helpers.split_domain(event.data)
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
