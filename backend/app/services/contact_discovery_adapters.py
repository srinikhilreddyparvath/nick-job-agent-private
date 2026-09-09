import ipaddress
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from app.core.config import Settings, get_settings
from app.models.contact import ContactCandidate, ContactEvidence, RelationshipStatus


PAGE_TERMS = ("team", "people", "research", "researchers", "science", "scientists", "engineering", "engineers", "technical", "authors", "blog", "labs", "staff", "feed")
CARD_TERMS = ("person", "people", "member", "author", "profile", "bio", "researcher", "scientist", "team-card", "staff-card", "employee")
DOMAIN_TERMS = ("search", "ranking", "retrieval", "relevance", "recommendation", "recommender", "personalization", "ads", "advertising", "alignment", "benchmarking", "evaluation", "model behavior", "llm", "language model", "computer vision", "infrastructure", "machine learning", "artificial intelligence", "data science")
TECHNICAL_TITLE_TERMS = ("engineer", "scientist", "research", "developer", "technical", "data", "machine learning", "ml ", "ai ", "recruiter", "talent")


def safe_public_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")) or "linkedin.com" in host:
        return False
    try:
        address = ipaddress.ip_address(host)
        return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved)
    except ValueError:
        return True


def _domains(text: str) -> list[str]:
    lowered = text.casefold()
    return [term for term in DOMAIN_TERMS if term in lowered]


def _looks_like_name(value: str | None) -> bool:
    if not value or len(value) > 100:
        return False
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]+", value)
    return 2 <= len(words) <= 6


@dataclass
class ContactAdapterResult:
    candidates: list[ContactCandidate] = field(default_factory=list)
    pages_checked: int = 0
    browser_pages_checked: int = 0
    sources_checked: int = 0
    errors: list[dict] = field(default_factory=list)


class PublicPeopleParser(HTMLParser):
    """Extracts public professional identity, role, and topic evidence from rendered or static HTML."""

    def __init__(self, url: str, company: str):
        super().__init__()
        self.url, self.company = url, company
        self.stack, self.people, self.links, self.scripts = [], [], [], []
        self.meta_authors: list[str] = []
        self.page_title = ""
        self._script: list[str] | None = None
        self._script_kind: str | None = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = f"{attr.get('class', '')} {attr.get('itemprop', '')} {attr.get('data-testid', '')}"
        frame = {"tag": tag, "class": classes, "text": [], "fields": [], "links": [], "attrs": attr}
        self.stack.append(frame)
        href = attr.get("href")
        if href:
            link = urljoin(self.url, href)
            self.links.append(link)
            frame["links"].append(link)
        if tag == "title":
            self._in_title = True
        if tag == "meta" and attr.get("name", "").casefold() == "author" and attr.get("content"):
            self.meta_authors.extend(part.strip() for part in re.split(r",|\band\b", attr["content"]) if part.strip())
        if tag == "script" and ("json" in attr.get("type", "") or attr.get("id") == "__NEXT_DATA__"):
            self._script, self._script_kind = [], attr.get("type") or attr.get("id")
        if tag in {"meta", "link", "img", "br", "hr", "input", "source"}:
            self.stack.pop()

    def handle_data(self, data):
        text = " ".join(data.split())
        if self._script is not None:
            self._script.append(data)
        if self._in_title and text:
            self.page_title += f" {text}"
        if text:
            for frame in self.stack:
                frame["text"].append(text)
            if self.stack:
                self.stack[-1]["fields"].append((self.stack[-1]["tag"], self.stack[-1]["class"], text))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._script is not None:
            self.scripts.append((self._script_kind or "json", "".join(self._script)))
            self._script, self._script_kind = None, None
        if not self.stack:
            return
        frame = self.stack.pop()
        if self.stack:
            self.stack[-1]["fields"].extend(frame["fields"])
            self.stack[-1]["links"].extend(frame["links"])
        marker = f"{frame['tag']} {frame['class']}".casefold()
        if frame["tag"] in {"article", "li", "div", "section"} and any(term in marker for term in CARD_TERMS):
            self._card(frame)

    def _card(self, frame):
        fields = frame["fields"]
        name = next((text for _tag, cls, text in fields if "name" in cls.casefold() or "author" in cls.casefold()), None)
        if not name and "author" not in frame["class"].casefold():
            name = next((text for tag, _cls, text in fields if tag in {"h2", "h3", "h4"}), None)
        title = next((text for _tag, cls, text in fields if any(term in cls.casefold() for term in ("title", "role", "position", "jobtitle"))), None)
        if not title:
            title = next((text for tag, _cls, text in fields if tag in {"p", "span"} and any(term in text.casefold() for term in TECHNICAL_TITLE_TERMS)), None)
        text = " ".join(frame["text"])
        domains = _domains(text)
        if not title and "author" in frame["class"].casefold() and domains:
            title = "Research or engineering author"
        if not _looks_like_name(name) or not title or name == title or len(title) > 180:
            return
        profile = next((link for link in frame["links"] if safe_public_url(link)), self.url)
        self.people.append(self._candidate(name, title, profile, domains, RelationshipStatus.verified, .82))

    def _candidate(self, name, title, profile, domains, status, confidence):
        team = next((term for term in domains if term in {"search", "ranking", "retrieval", "recommendation", "personalization", "ads", "alignment", "evaluation", "infrastructure"}), None)
        path = urlparse(self.url).path.casefold()
        source_type = "COMPANY_ENGINEERING_BLOG" if any(term in path for term in ("blog", "engineering")) else "COMPANY_RESEARCH_PAGE" if any(term in path for term in ("research", "science", "lab", "publication")) else "COMPANY_TEAM_PAGE"
        recruiting = any(term in title.casefold() for term in ("recruiter", "talent acquisition", "talent partner", "sourcer"))
        statement = f"A public company-authored page identifies this person as {title} and supplies the displayed professional context."
        return ContactCandidate(name=name, current_title=title, company=self.company, public_profile_url=profile, source_type=source_type, source_url=self.url, team=team, domains=domains, recruiting_relevance=recruiting and bool(domains), relationship_status=status, relationship_confidence=confidence, evidence=[ContactEvidence(source_url=self.url, source_type=source_type, statement=statement)])

    def structured_people(self):
        found = []

        def walk(value, path=""):
            if isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}/{index}")
            elif isinstance(value, dict):
                kind = value.get("@type")
                is_person = kind in {"Person", "Employee"} or isinstance(kind, list) and bool({"Person", "Employee"} & set(kind))
                contextual = any(term in path.casefold() for term in ("people", "person", "author", "team", "staff", "researcher", "employee"))
                name = value.get("name") or value.get("fullName")
                title = value.get("jobTitle") or value.get("currentTitle") or value.get("role")
                if name and title and (is_person or contextual):
                    works = value.get("worksFor") or value.get("affiliation") or {}
                    employer = works.get("name") if isinstance(works, dict) else works if isinstance(works, str) else None
                    if not employer or self.company.casefold() in employer.casefold():
                        context = " ".join(str(value.get(key, "")) for key in ("jobTitle", "currentTitle", "role", "description", "headline", "researchInterests"))
                        profile = urljoin(self.url, value.get("url") or value.get("profileUrl") or self.url)
                        if _looks_like_name(name) and safe_public_url(profile):
                            found.append(self._candidate(name, title, profile, _domains(context), RelationshipStatus.verified if is_person else RelationshipStatus.likely_relevant, .86 if is_person else .72))
                for key, item in value.items():
                    walk(item, f"{path}/{key}")

        for _kind, script in self.scripts:
            try:
                walk(json.loads(script))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        page_domains = _domains(f"{self.page_title} {urlparse(self.url).path}")
        if page_domains and any(term in urlparse(self.url).path.casefold() for term in ("research", "publication", "paper", "science")):
            for author in self.meta_authors:
                if _looks_like_name(author):
                    found.append(self._candidate(author, "Research author", self.url, page_domains, RelationshipStatus.likely_relevant, .62))
        return found


class PlaywrightPublicPageRenderer:
    """Renders only prevalidated public company URLs; no login or anti-bot bypass."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def render(self, urls: list[str]) -> tuple[list[tuple[str, str]], list[dict]]:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

        rendered, errors = [], []
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context(service_workers="block", accept_downloads=False)
            context.route("**/*", lambda route: route.abort() if route.request.resource_type in {"image", "media", "font"} else route.continue_())
            page = context.new_page()
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=int(self.settings.contact_discovery_browser_timeout_seconds * 1000))
                    page.wait_for_timeout(750)
                    if safe_public_url(page.url):
                        rendered.append((page.url, page.content()))
                except PlaywrightTimeoutError:
                    errors.append({"source": "playwright_public_page", "category": "TimeoutError"})
                except Exception as exc:
                    errors.append({"source": "playwright_public_page", "category": type(exc).__name__})
            context.close()
            browser.close()
        return rendered, errors


class PublicGitHubEvidenceAdapter:
    """Adds GitHub topic evidence only for people already identified by a company source."""

    name = "public_github_supporting_evidence"

    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.contact_discovery_timeout_seconds, headers={"User-Agent": settings.connector_user_agent}, follow_redirects=False)

    def enrich(self, candidates: list[ContactCandidate]) -> ContactAdapterResult:
        result = ContactAdapterResult()
        for candidate in candidates[: self.settings.contact_discovery_max_contacts]:
            profile = str(candidate.public_profile_url)
            if urlparse(profile).hostname not in {"github.com", "www.github.com"}:
                continue
            result.pages_checked += 1
            result.sources_checked = 1
            try:
                response = self.client.get(profile)
                if response.status_code >= 400 or "html" not in response.headers.get("content-type", ""):
                    continue
                topics = _domains(response.text)
                if not topics:
                    continue
                candidate.domains = sorted(set(candidate.domains + topics))
                candidate.evidence.append(ContactEvidence(source_url=profile, source_type="PUBLIC_GITHUB_SUPPORT", statement="A public GitHub profile linked by the company-authored source shows work in relevant technical topics; it is supporting evidence, not proof of employment."))
            except (httpx.HTTPError, TimeoutError) as exc:
                result.errors.append({"source": self.name, "category": type(exc).__name__})
        result.candidates = candidates
        return result


class CompanyPublicPagesAdapter:
    name = "company_public_pages"

    def __init__(self, settings: Settings | None = None, client=None, renderer=None, github_adapter=None):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=self.settings.contact_discovery_timeout_seconds, headers={"User-Agent": self.settings.connector_user_agent}, follow_redirects=False)
        self.renderer = renderer
        self.github_adapter = github_adapter or PublicGitHubEvidenceAdapter(self.settings, self.client)

    @staticmethod
    def _parse(url: str, company: str, html: str) -> tuple[list[ContactCandidate], list[str]]:
        parser = PublicPeopleParser(url, company)
        parser.feed(html)
        return parser.people + parser.structured_people(), parser.links

    @staticmethod
    def _parse_feed(url: str, company: str, payload: str) -> list[ContactCandidate]:
        """Treats a named author on a company technical feed as likely relevant, never as employment proof."""
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError:
            return []
        candidates = []
        for entry in list(root.iter())[:500]:
            if entry.tag.rsplit("}", 1)[-1].casefold() not in {"item", "entry"}:
                continue
            values: dict[str, list[str]] = {}
            for child in entry.iter():
                key = child.tag.rsplit("}", 1)[-1].casefold()
                text = " ".join("".join(child.itertext()).split())
                if text:
                    values.setdefault(key, []).append(text)
            author = next(iter(values.get("creator", []) + values.get("author", []) + values.get("name", [])), None)
            context = " ".join(values.get("title", []) + values.get("description", []) + values.get("summary", []) + values.get("category", []))
            domains = _domains(context)
            if not _looks_like_name(author) or not domains:
                continue
            link = next(iter(values.get("link", [])), url)
            if not safe_public_url(link):
                link = url
            team = next((term for term in domains if term in {"search", "ranking", "retrieval", "recommendation", "personalization", "ads", "alignment", "evaluation", "infrastructure"}), None)
            candidates.append(ContactCandidate(name=author, current_title="Technical blog author", company=company, public_profile_url=link, source_type="COMPANY_ENGINEERING_BLOG", source_url=url, team=team, domains=domains, relationship_status=RelationshipStatus.likely_relevant, relationship_confidence=.64, evidence=[ContactEvidence(source_url=url, source_type="COMPANY_ENGINEERING_BLOG", statement="A public company technical feed identifies this author with work in the displayed technical topic; employment and hiring responsibility are not inferred.")]))
        return candidates

    def discover(self, company: str, seeds: list[str]) -> ContactAdapterResult:
        result, queue, seen, rendered_candidates = ContactAdapterResult(), [], set(), []
        company_hosts = set()
        for seed in seeds:
            if safe_public_url(seed):
                parsed = urlparse(seed)
                company_hosts.add(parsed.netloc.casefold())
                origin = f"{parsed.scheme}://{parsed.netloc}/"
                queue.extend([seed, origin] + [urljoin(origin, path) for path in PAGE_TERMS])
        result.sources_checked = len(company_hosts)
        browser_candidates: list[str] = []
        while queue and result.pages_checked < self.settings.contact_discovery_max_pages_per_job:
            url = queue.pop(0)
            if url in seen or not safe_public_url(url) or urlparse(url).netloc.casefold() not in company_hosts:
                continue
            seen.add(url)
            result.pages_checked += 1
            try:
                response = self.client.get(url)
                if response.status_code >= 400 or not safe_public_url(str(response.url)):
                    continue
                content_type = response.headers.get("content-type", "").casefold()
                if len(response.content) > 3_000_000:
                    continue
                if any(term in content_type for term in ("xml", "rss", "atom")) or response.text.lstrip().startswith(("<?xml", "<rss", "<feed")):
                    candidates, links = self._parse_feed(str(response.url), company, response.text), []
                elif "html" in content_type:
                    candidates, links = self._parse(str(response.url), company, response.text)
                else:
                    continue
                result.candidates.extend(candidates)
                if not candidates and any(term in urlparse(url).path.casefold() for term in PAGE_TERMS):
                    browser_candidates.append(url)
                origin_host = urlparse(str(response.url)).netloc.casefold()
                discovered_links = []
                for link in links:
                    parsed = urlparse(link)
                    if parsed.netloc.casefold() == origin_host and any(term in parsed.path.casefold() for term in PAGE_TERMS) and link not in seen:
                        discovered_links.append(link)
                def link_priority(link):
                    path = urlparse(link).path.casefold()
                    return (0 if any(term in path for term in ("/team/", "/people/", "/authors/", "/researchers/", "/staff/")) else 1, len(path))
                # Company-linked people/team pages outrank guessed paths and article archives.
                queue = sorted(dict.fromkeys(discovered_links), key=link_priority) + queue
            except (httpx.HTTPError, TimeoutError) as exc:
                result.errors.append({"source": self.name, "category": type(exc).__name__})

        if not result.candidates and self.settings.contact_discovery_browser_fallback_enabled and browser_candidates:
            renderer = self.renderer or PlaywrightPublicPageRenderer(self.settings)
            urls = list(dict.fromkeys(browser_candidates))[: self.settings.contact_discovery_browser_max_pages]
            try:
                rendered, errors = renderer.render(urls)
                result.errors.extend(errors)
                result.browser_pages_checked += len(urls)
                for final_url, html in rendered:
                    candidates, _links = self._parse(final_url, company, html)
                    rendered_candidates.extend(candidates)
            except Exception as exc:
                result.errors.append({"source": "playwright_public_page", "category": type(exc).__name__})
        result.candidates.extend(rendered_candidates)

        if result.candidates:
            github = self.github_adapter.enrich(result.candidates)
            result.candidates = github.candidates
            result.pages_checked += github.pages_checked
            result.sources_checked += github.sources_checked
            result.errors.extend(github.errors)
        return result
