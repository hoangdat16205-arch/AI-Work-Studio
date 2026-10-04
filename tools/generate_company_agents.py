"""Generate the 24 project agents, using the current official Kilo format."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from company_roster import ROSTER,COMMON_RULES,MANAGER_RULES


def permissions(role):
    profile=role['profile']
    edits={'*':'deny','.ai-company/missions/*/reports/*':'allow'}
    scopes={'frontend':['static/*','*.html'], 'backend':['*.py'],
            'tests':['test_*.py','tests/*'], 'docs':['docs/*'],
            'ops':['requirements.txt','start_windows.bat','.github/workflows/*','docs/*']}
    for scope in scopes.get(profile,[]):edits[scope]='allow'
    if profile=='manager':edits['.ai-company/missions/*/result.json']='allow'
    # Last match wins. Protect execution/configuration after broad code scopes.
    for scope in ['company_roster.py','studio_company.py','studio_accounts.py','studio_billing.py','test_company.py','tools/*','.kilo/*','kilo.jsonc','*.env','*.env.*','*.sqlite3*','.accounts/*','runtime/*']:
        edits[scope]='deny'
    reads={'*':'allow','*.env':'deny','*.env.*':'deny','*.env.example':'allow',
           '.accounts/*':'deny','runtime/*':'deny','.ai-company/bridge-token':'deny','.ai-company/missions/*/runtime.json':'deny','*.sqlite3*':'deny'}
    shell={'*':'ask' if profile in {'frontend','backend','tests','ops'} else 'deny',
           'git status *':'allow','git diff *':'allow','git log *':'allow',
           'python tools/company_report.py *':'allow',
           '.venv/bin/python tools/company_report.py *':'allow',
           '.venv/Scripts/python.exe tools/company_report.py *':'allow'}
    if profile in {'frontend','backend','tests','review'}:
        for prefix in ['python -m unittest *','.venv/bin/python -m unittest *','.venv/Scripts/python.exe -m unittest *','node --check *']:
            shell[prefix]='allow'
    for pattern in ['git push *','git reset *','git clean *','rm *','curl *','wget *','python tools/company_worker.py *']:
        shell[pattern]='deny'
    tasks={'*':'deny'}
    if profile=='manager':tasks.update({r['id']:'allow' for r in ROSTER if r['id']!='ai-manager'})
    return {'*':'deny','read':reads,'edit':edits,'glob':'allow','grep':'allow','list':'allow',
            'bash':shell,'task':tasks,'todowrite':'allow','todoread':'allow',
            'webfetch':'ask','websearch':'ask','external_directory':'deny','doom_loop':'ask'}


def generate(root):
    directory=Path(root)/'.kilo'/'agents';directory.mkdir(parents=True,exist_ok=True)
    for role in ROSTER:
        config={'description':f"{role['name']}: {role['description']}",
                'mode':'primary' if role['profile']=='manager' else 'subagent',
                'color':'#00b982' if role['profile']=='manager' else '#248b88',
                'steps':80 if role['profile']=='manager' else 24,
                'permission':permissions(role)}
        # JSON is a valid YAML document in Markdown frontmatter; no YAML dependency.
        frontmatter=json.dumps(config,ensure_ascii=False,indent=2)
        prompt=f"Bạn là {role['name']}. {role['description']}\nĐầu ra mong đợi: {role['deliverable']}.\n"+COMMON_RULES
        if role['profile']=='manager':prompt+=MANAGER_RULES+'\nNhân sự có thể giao việc:\n'+ '\n'.join(f"- {r['id']}: {r['description']}" for r in ROSTER[1:])
        (directory/(role['id']+'.md')).write_text('---\n'+frontmatter+'\n---\n\n'+prompt,encoding='utf-8')
    config={'$schema':'https://app.kilo.ai/config.json','default_agent':'ai-manager','share':'disabled'}
    path=Path(root)/'kilo.jsonc'
    if not path.exists():path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    print(f'Generated {len(ROSTER)} Kilo agents; existing kilo.jsonc preserved.')


if __name__=='__main__':generate(Path(__file__).resolve().parents[1])
