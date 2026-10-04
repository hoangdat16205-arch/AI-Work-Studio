"""Owner-only terminal command: no public auto-admin registration."""
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio_accounts import Accounts
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];load_dotenv(root/'.env')
    parser=argparse.ArgumentParser(description='Quản trị tài khoản từ terminal của chủ website.')
    parser.add_argument('--make-admin',required=True,metavar='EMAIL');args=parser.parse_args()
    try:
        user=Accounts(Path(os.getenv('STUDIO_DATA_ROOT') or str(root))).make_admin(args.make_admin);print('Đã cấp quyền quản trị cho '+user['email']+'. Tải lại trang web.')
    except ValueError as error:raise SystemExit(str(error))
