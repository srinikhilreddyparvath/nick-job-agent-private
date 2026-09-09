"""Local-only Playwright reproduction. Never resets the global job catalog."""
import json
import os
from pathlib import Path
from time import monotonic

from playwright.sync_api import sync_playwright

API=os.getenv('ROLECALL_API_URL','http://localhost:8000')
BASE=os.getenv('ROLECALL_URL','http://localhost:3000')
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=json.loads((ROOT/'tests/fixtures/candidate_isolation.json').read_text())
OUTPUT=ROOT/'tmp/candidate-isolation-reproduction'
OUTPUT.mkdir(parents=True,exist_ok=True)


def get(response):
    assert response.ok, f'HTTP {response.status}'
    return response.json()


with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror', lambda error:errors.append(type(error).__name__))
    before=get(page.request.get(f'{API}/jobs?view=raw&limit=1'))['total']
    shared=get(page.request.get(f'{API}/jobs?view=raw&limit=500&company=Fictional%20Shared%20Research%20Group'))['items'][0]['id']
    previous_evidence=set();previous_profile=None;results=[]
    for label,expected in [('AI',{'RESEARCH_AI'}),('CLINICAL',{'CLINICAL_RESEARCH','PUBLIC_HEALTH','RESEARCH','HEALTHCARE_OPERATIONS'}),('PRODUCT',{'PRODUCT_MANAGEMENT'})]:
        fixture=FIXTURE['candidates'][label]
        roles=fixture['preferences']['preferred_titles'];skills=fixture['preferences']['preferred_domains']
        resume=OUTPUT/f'fictional-{label}.txt'
        resume.write_text('\n'.join([f'Fictional {label} Candidate',roles[0],f'Employer: Fictional {label} Research Group','Dates: 2020-2026','Skills: '+', '.join(skills),'Education: Master of Science', 'Demonstrated '+', '.join(skills)+'.']),encoding='utf-8')
        page.goto(f'{BASE}/onboarding',wait_until='networkidle')
        with page.expect_response(lambda response:response.url.endswith('/onboarding/resume'),timeout=90000) as response:
            page.locator('input[type="file"]').set_input_files(str(resume))
        get(response.value)
        page.get_by_text('Resume ready for review',exact=False).wait_for()
        # New upload cannot inherit the prior targets or run discovery yet.
        inferred=page.get_by_label('Target roles',exact=True).input_value()
        assert roles[0] in inferred
        if previous_profile:
            assert page.request.post(f'{API}/career-intelligence/find-jobs').status==409
        page.get_by_label('Target roles',exact=True).fill(', '.join(roles))
        page.get_by_label('Domains / role families',exact=True).fill(', '.join(skills))
        page.get_by_role('checkbox',name='I reviewed target roles and constraints').check()
        with page.expect_response(lambda response:response.url.endswith('/onboarding/approve')) as approved_response:
            page.get_by_role('button',name='APPROVE PROFILE & PREFERENCES').click()
        approved=get(approved_response.value)
        profile_id=approved['profile']['candidate_profile_id']
        evidence={x['id'] for x in approved['evidence']}
        assert profile_id!=previous_profile and evidence and not evidence & previous_evidence
        unevaluated=get(page.request.get(f'{API}/jobs/{shared}'))
        assert unevaluated['fit_score'] is None and not unevaluated['matched_evidence_ids']
        assert page.request.get(f'{API}/jobs/{shared}/analysis').status==404
        page.get_by_role('link',name='FIND JOBS',exact=True).click()
        page.wait_for_url('**/dashboard')
        with page.expect_response(lambda response:response.url.endswith('/career-intelligence/find-jobs')) as queued_response:
            page.get_by_role('button',name='FIND JOBS',exact=True).click()
        queued=get(queued_response.value)
        print(json.dumps({'candidate':label,'stage':'evaluating_shared_catalog','run_id':queued['id'],'profile_id':profile_id,'profile_version':approved['profile']['profile_version'],'evidence_count':len(evidence)}),flush=True)
        deadline=monotonic()+900
        while True:
            run=get(page.request.get(f"{API}/career-intelligence/runs/{queued['id']}"))
            if run['status'] in ('completed','failed'):break
            assert monotonic()<deadline, 'Worker run deadline exceeded'
            page.wait_for_timeout(3000)
        assert run['status']=='completed', {'status':run['status'],'errors':[x.get('error') for x in run.get('errors',[])]}
        raw=get(page.request.get(f'{API}/jobs?view=raw&limit=500'))
        assert raw['total']==before and run['unique_jobs']==0 and run['sources_scanned']==0
        top=raw['items'][:20]
        correct=sum(job['role_family'] in expected for job in top)
        assert correct==20, {'candidate':label,'top20_correct':correct}
        for job in raw['items']:
            assert set(job['matched_evidence_ids']).issubset(evidence)
            for match in job['opportunity_score']['why_you_match']:assert set(match['evidence_ids']).issubset(evidence)
        unrelated=sum(job['opportunity_score']['overall_score']>90 for job in raw['items'] if job['role_family'] in {'PRODUCT_MANAGEMENT','RESEARCH_AI','SOFTWARE_ENGINEERING','INFORMATION_TECHNOLOGY'}) if label=='CLINICAL' else None
        if label=='CLINICAL':assert unrelated==0
        shared_job=get(page.request.get(f'{API}/jobs/{shared}'))
        # Also exercise same-job semantic analysis and cache separation for each candidate.
        analysis=get(page.request.post(f'{API}/jobs/{shared}/analyze',data={'use_mock':True,'refresh':False},timeout=90000))
        assert analysis.get('report') and not analysis['report']['cache_hit']
        assert set(analysis['report']['evidence_ids']).issubset(evidence)
        shared_job=get(page.request.get(f'{API}/jobs/{shared}'))
        page.reload(wait_until='networkidle')
        labels=page.locator('.family-tabs button').all_text_contents()
        if label=='CLINICAL':assert 'Clinical research' in labels and 'Product management' not in labels and 'Research / AI' not in labels
        assert page.locator('.job-card').count()>0
        page.screenshot(path=str(OUTPUT/f'{label}-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
        page.screenshot(path=str(OUTPUT/f'{label}-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        summary={'candidate':label,'run_id':run['id'],'profile_id':profile_id,'profile_version':approved['profile']['profile_version'],'global_jobs':raw['total'],'new_unique_jobs':run['unique_jobs'],'sources_refetched':run['sources_scanned'],'top10_correct':sum(x['role_family'] in expected for x in top[:10]),'top20_correct':correct,'shared_job_id':shared,'shared_score':shared_job['opportunity_score']['overall_score'],'shared_evidence_count':len(shared_job['matched_evidence_ids']),'semantic_cache_hit':analysis['report']['cache_hit'],'unrelated_above_90':unrelated,'tabs':labels,'status':'PASS'}
        print(json.dumps(summary),flush=True);results.append(summary)
        previous_profile=profile_id;previous_evidence |= evidence
    assert not errors
    (OUTPUT/'report.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps({'public_reproduction':'PASS','candidates':3,'same_catalog_jobs':before,'browser_errors':len(errors),'applications_submitted':0,'outreach_sent':0}),flush=True)
    browser.close()
