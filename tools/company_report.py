"""Agent-to-board reporting helper, authorized by the active worker lease."""
import argparse
import json
from pathlib import Path
from company_client import BridgeClient


def main():
    parser=argparse.ArgumentParser(description='Gửi báo cáo nhiệm vụ Kilo về bảng Công ty AI.')
    parser.add_argument('mission');parser.add_argument('task');parser.add_argument('status',nargs='?',choices=['started','submitted','blocked','failed'])
    parser.add_argument('--summary',default='');parser.add_argument('--verdict',default='',choices=['','pass','fail','blocked'])
    parser.add_argument('--evidence',action='append',default=[])
    parser.add_argument('--agent');parser.add_argument('--title');parser.add_argument('--depends',nargs='*',default=[])
    args=parser.parse_args();client=BridgeClient(Path(__file__).resolve().parents[1]);runtime=client.runtime(args.mission)
    data={'lease':runtime['lease'],'task':args.task,'status':args.status,'summary':args.summary,'verdict':args.verdict,'evidence':args.evidence}
    if args.task=='add':data.update(operation='add',agent=args.agent,title=args.title,description=args.summary,depends=args.depends)
    elif not args.status:parser.error('Nêu trạng thái started/submitted/blocked/failed.')
    response=client.post(args.mission+'/task',data)
    print(json.dumps(response,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as error:raise SystemExit(str(error))
