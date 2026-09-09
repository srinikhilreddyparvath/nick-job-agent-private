import httpx
import json

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models.contact import ContactCandidate,ContactEvidence,RelationshipStatus
from app.models.job import Job
from app.services.contact_discovery_adapters import CompanyPublicPagesAdapter, ContactAdapterResult, PublicGitHubEvidenceAdapter, PublicPeopleParser, safe_public_url
from app.services.contact_intelligence_service import ContactIntelligenceService
from app.services.job_service import JobService


def candidate(name,title,*,team=None,domains=None,recruiter=False,small=False,owner=False,status=RelationshipStatus.likely_relevant):
    return ContactCandidate(name=name,current_title=title,company="Northstar Labs",public_profile_url=f"https://people.example/{name.lower().replace(' ','-')}",source_type="COMPANY_ENGINEERING_BLOG",source_url="https://northstar.example/engineering/search",team=team,domains=domains or [],recruiting_relevance=recruiter,company_is_small=small,direct_function_ownership=owner,relationship_status=status,relationship_confidence=.8,evidence=[ContactEvidence(source_url="https://northstar.example/engineering/search",source_type="COMPANY_ENGINEERING_BLOG",statement="Public author biography connects this person to search ranking.")])


def create_job(db):
    return JobService().create(db,Job(external_id="contact-job",source="fixture",company="Northstar Labs",title="Research Engineer, Search Ranking",location="Metro City",description="Build retrieval and search ranking systems.",apply_url="https://northstar.example/apply",source_url="https://northstar.example/jobs/search"))


def test_same_role_and_team_rank_above_adjacent_and_recruiter():
    db=SessionLocal();job=create_job(db);service=ContactIntelligenceService()
    result=service.replace(db,job.id,[candidate("Peer Person","Senior Research Engineer, Search Ranking",team="Search Ranking",domains=["search","ranking"]),candidate("Adjacent Person","ML Engineer",domains=["search"]),candidate("Recruiter Person","Technical Recruiter",recruiter=True,domains=["search"])])
    assert [x.name for x in result.items]==["Peer Person","Adjacent Person","Recruiter Person"]
    assert result.items[0].role_similarity>result.items[1].role_similarity
    db.close()


def test_ceo_and_unrelated_employee_are_excluded_by_default():
    db=SessionLocal();job=create_job(db);service=ContactIntelligenceService()
    result=service.replace(db,job.id,[candidate("Executive Person","CEO",domains=["search"]),candidate("Unrelated Person","Accountant",domains=["finance"])])
    assert result.items==[] and result.message
    db.close()


def test_small_company_technical_founder_requires_direct_evidence():
    db=SessionLocal();job=create_job(db);service=ContactIntelligenceService()
    result=service.replace(db,job.id,[candidate("Technical Founder","Founder and Search Engineer",domains=["search","ranking"],small=True,owner=True,status=RelationshipStatus.verified)])
    assert len(result.items)==1 and result.items[0].relationship_status=="VERIFIED"
    db.close()


def test_contact_discovery_does_not_mutate_opportunity_score_and_outreach_is_not_sent(monkeypatch):
    db=SessionLocal();job=create_job(db);schema=JobService().to_schema(job);before=schema.opportunity_score.overall_score
    result=ContactIntelligenceService().replace(db,job.id,[candidate("Peer Person","Research Engineer, Search Ranking",team="Search Ranking",domains=["search","ranking"])])
    monkeypatch.setattr("app.services.contact_intelligence_service.EvidenceService.all",lambda self:[])
    preview=ContactIntelligenceService().outreach(db,job.id,result.items[0].contact_id)
    assert preview.sent is False and "refer" not in preview.message.casefold()
    assert JobService().to_schema(JobService().get(db,job.id)).opportunity_score.overall_score==before
    db.close()


def test_contact_api_empty_state(client):
    db=SessionLocal();job=create_job(db);db.close()
    response=client.get(f"/jobs/{job.id}/contacts")
    assert response.status_code==200 and response.json()["items"]==[] and "No sufficiently relevant" in response.json()["message"]


TEAM_HTML="""<html><body>
<article class="team-card"><h3 class="name">Peer Person</h3><p class="title">Senior Research Engineer, Search Ranking</p><p>Search ranking and retrieval</p></article>
<article class="team-card"><h3 class="name">Executive Person</h3><p class="title">CEO</p><p>Company leadership</p></article>
<article class="team-card"><h3 class="name">Unrelated Person</h3><p class="title">Finance Manager</p><p>Accounting operations</p></article>
<article class="team-card"><h3 class="name">Recruiter Person</h3><p class="title">Technical Recruiter, Machine Learning</p><p>Search and ML recruiting</p></article>
</body></html>"""
BLOG_HTML="""<article class="author-profile"><h3 class="name">Peer Person</h3><p class="role">Staff Research Engineer, Search Ranking</p><p>Scaling retrieval and relevance systems</p></article>"""
RESEARCH_HTML="""<article class="researcher"><h3 class="name">Research Person</h3><p class="position">Applied Scientist, Retrieval</p><p>Search ranking evaluation</p></article>"""


def fixture_client(*,timeout=False):
    def handler(request):
        if timeout:raise httpx.ReadTimeout("bounded fixture timeout",request=request)
        path=request.url.path
        body=BLOG_HTML if "engineering" in path else RESEARCH_HTML if "research" in path else TEAM_HTML if "team" in path or path=="/" else "<html></html>"
        return httpx.Response(200,text=body,headers={"content-type":"text/html"},request=request)
    return httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False)


def test_public_page_adapters_rank_peers_merge_sources_and_exclude_leadership():
    db=SessionLocal();job=create_job(db);settings=get_settings().model_copy(update={"contact_discovery_max_pages_per_job":10,"contact_discovery_max_contacts":5})
    adapter=CompanyPublicPagesAdapter(settings,fixture_client())
    raw=adapter.discover("Northstar Labs",["https://northstar.example/"])
    result=ContactIntelligenceService(settings,[adapter]).replace(db,job.id,raw.candidates)
    assert raw.pages_checked<=10
    assert [item.name for item in result.items][:2]==["Peer Person","Research Person"]
    assert "Executive Person" not in [item.name for item in result.items]
    assert "Unrelated Person" not in [item.name for item in result.items]
    assert sum(item.name=="Peer Person" for item in result.items)==1
    peer=result.items[0]
    assert len(peer.evidence)>=2 and peer.role_similarity>result.items[-1].role_similarity
    assert result.items[-1].name=="Recruiter Person"
    db.close()


def test_public_fetch_is_bounded_safe_and_timeout_does_not_affect_job():
    assert not safe_public_url("http://127.0.0.1/private")
    assert not safe_public_url("https://www.linkedin.com/in/example")
    db=SessionLocal();job=create_job(db);before=JobService().to_schema(job).opportunity_score.overall_score
    settings=get_settings().model_copy(update={"contact_discovery_max_pages_per_job":3})
    result=CompanyPublicPagesAdapter(settings,fixture_client(timeout=True)).discover("Northstar Labs",["https://northstar.example/"])
    assert result.pages_checked==3 and result.candidates==[] and len(result.errors)==3
    assert JobService().to_schema(JobService().get(db,job.id)).opportunity_score.overall_score==before
    db.close()


class FixtureAdapter:
    name="fixture_public_pages"
    def __init__(self):self.calls=0
    def discover(self,company,seeds):
        self.calls+=1
        return ContactAdapterResult(candidates=[candidate("Peer Person","Senior Research Engineer, Search Ranking",team="Search Ranking",domains=["search","ranking"])],pages_checked=2,sources_checked=1)


def test_orchestrator_persists_and_reuses_fresh_cached_results():
    db=SessionLocal();job=create_job(db);adapter=FixtureAdapter();service=ContactIntelligenceService(adapters=[adapter])
    first=service.discover(db,job.id);second=service.discover(db,job.id);refreshed=service.discover(db,job.id,force=True)
    assert len(first.items)==1 and first.pages_checked==2 and first.cached is False
    assert second.cached is True and refreshed.cached is False and adapter.calls==2
    db.close()


def test_contact_discovery_endpoint_invokes_orchestrator(client,monkeypatch):
    db=SessionLocal();job=create_job(db);db.close()
    monkeypatch.setattr("app.api.contacts.service.discover",lambda db,job_id,force=False: ContactIntelligenceService(adapters=[]).list(db,job_id))
    response=client.post(f"/jobs/{job.id}/contacts/discover")
    assert response.status_code==200 and response.json()["items"]==[]


class FixtureRenderer:
    def __init__(self,html,*,fails=False):self.html=html;self.fails=fails;self.calls=[]
    def render(self,urls):
        self.calls.append(urls)
        if self.fails:raise TimeoutError("fixture browser timeout")
        return [(urls[0],self.html)],[]


def empty_static_client():
    def handler(request):return httpx.Response(200,text="<html><body><div id='app'></div></body></html>",headers={"content-type":"text/html"},request=request)
    return httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False)


def test_browser_fallback_runs_only_after_static_parse_has_no_people():
    settings=get_settings().model_copy(update={"contact_discovery_max_pages_per_job":5,"contact_discovery_browser_max_pages":2,"contact_discovery_browser_fallback_enabled":True})
    renderer=FixtureRenderer(TEAM_HTML)
    adapter=CompanyPublicPagesAdapter(settings,empty_static_client(),renderer=renderer)
    result=adapter.discover("Northstar Labs",["https://northstar.example/"])
    assert len(renderer.calls)==1 and len(renderer.calls[0])<=2
    assert result.browser_pages_checked==len(renderer.calls[0]) and any(item.name=="Peer Person" for item in result.candidates)
    static_renderer=FixtureRenderer(TEAM_HTML)
    static_adapter=CompanyPublicPagesAdapter(settings,fixture_client(),renderer=static_renderer)
    assert static_adapter.discover("Northstar Labs",["https://northstar.example/"]).candidates
    assert static_renderer.calls==[]


def test_browser_timeout_is_isolated_and_returns_truthful_empty_result():
    settings=get_settings().model_copy(update={"contact_discovery_max_pages_per_job":3,"contact_discovery_browser_max_pages":1,"contact_discovery_browser_fallback_enabled":True})
    result=CompanyPublicPagesAdapter(settings,empty_static_client(),renderer=FixtureRenderer("",fails=True)).discover("Northstar Labs",["https://northstar.example/"])
    assert result.candidates==[] and any(item["category"]=="TimeoutError" for item in result.errors)


def test_next_data_jsonld_and_research_author_metadata_are_parsed():
    embedded={"props":{"pageProps":{"team":{"people":[{"name":"Structured Person","currentTitle":"Staff Research Engineer, Evaluation","affiliation":{"name":"Northstar Labs"},"description":"model behavior and benchmarking","url":"/people/structured"}]}}}}
    html=f'<title>Model Evaluation Research</title><script id="__NEXT_DATA__" type="application/json">{json.dumps(embedded)}</script>'
    parser=PublicPeopleParser("https://northstar.example/research", "Northstar Labs");parser.feed(html);people=parser.structured_people()
    assert len(people)==1 and "evaluation" in people[0].domains and people[0].relationship_status=="LIKELY_RELEVANT"
    author=PublicPeopleParser("https://northstar.example/research/model-evaluation-paper", "Northstar Labs")
    author.feed('<title>Model Evaluation and Alignment</title><meta name="author" content="Research Author">')
    author_people=author.structured_people()
    assert len(author_people)==1 and author_people[0].current_title=="Research author"


def test_github_is_supporting_evidence_only_and_never_creates_identity():
    def handler(request):return httpx.Response(200,text="ranking retrieval evaluation",headers={"content-type":"text/html"},request=request)
    client=httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False)
    settings=get_settings();adapter=PublicGitHubEvidenceAdapter(settings,client)
    assert adapter.enrich([]).candidates==[]
    linked=candidate("Public Peer","Research Engineer",domains=[]);linked.public_profile_url="https://github.com/public-peer"
    result=adapter.enrich([linked])
    assert len(result.candidates)==1 and "ranking" in result.candidates[0].domains
    assert result.candidates[0].evidence[-1].source_type=="PUBLIC_GITHUB_SUPPORT"


def test_company_technical_feed_extracts_likely_relevant_authors_without_employment_claim():
    feed="""<?xml version="1.0"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>Scaling recommendation ranking evaluation</title><dc:creator>Fictional Author</dc:creator><link>https://northstar.example/engineering/ranking</link><description>Retrieval and personalization systems</description></item></channel></rss>"""
    people=CompanyPublicPagesAdapter._parse_feed("https://northstar.example/engineering/feed","Northstar Labs",feed)
    assert len(people)==1 and people[0].relationship_status=="LIKELY_RELEVANT"
    assert {"ranking","recommendation","evaluation"}.issubset(set(people[0].domains))
    assert "employment" in people[0].evidence[0].statement.casefold() and "not inferred" in people[0].evidence[0].statement.casefold()
